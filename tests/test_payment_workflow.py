from io import BytesIO

from PIL import Image

from receipt_pipeline.payment_workflow import PaymentEvent, ReceiptProcessor


class RecordingStorage:
    def __init__(self) -> None:
        self.presigned: list[tuple[str, str, int, str]] = []
        self.uploaded: list[tuple[str, bytes]] = []

    def presign_put(self, bucket: str, key: str, content_type: str, max_bytes: int, idempotency_key: str):
        self.presigned.append((bucket, key, max_bytes, idempotency_key))
        return {"url": f"https://upload.test/{key}"}

    def upload_signed(self, url: str, content: bytes, content_type: str) -> None:
        self.uploaded.append((url, content))


def jpeg(width: int = 900, height: int = 600) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, "JPEG")
    return output.getvalue()


def test_settled_low_risk_payment_stores_original_and_thumbnail() -> None:
    storage = RecordingStorage()
    processor = ReceiptProcessor(storage, "receipts")
    event = PaymentEvent(
        payment_id="pay_1042",
        account_id="acct_88",
        amount_minor=1299,
        currency="USD",
        status="settled",
        risk_score=18,
    )

    result = processor.process(event, jpeg())

    assert result.action == "stored"
    assert result.notification == "receipt_ready"
    assert result.audit_reason == "settled payment passed automatic review"
    assert result.object_keys == [
        "receipts/acct_88/pay_1042/original.jpg",
        "receipts/acct_88/pay_1042/thumbnail.jpg",
    ]
    thumbnail = Image.open(BytesIO(storage.uploaded[1][1]))
    assert thumbnail.size == (320, 213)
    assert len({entry[3] for entry in storage.presigned}) == 2


def test_high_risk_payment_opens_review_without_storing_image() -> None:
    storage = RecordingStorage()
    processor = ReceiptProcessor(storage, "receipts")
    event = PaymentEvent(
        payment_id="pay_1043",
        account_id="acct_88",
        amount_minor=250000,
        currency="USD",
        status="settled",
        risk_score=82,
    )

    result = processor.process(event, jpeg())

    assert result.action == "manual_review"
    assert result.notification == "risk_review_opened"
    assert result.object_keys == []
    assert storage.presigned == []
