from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal, Protocol

from PIL import Image, ImageOps
from pydantic import BaseModel, Field


class PaymentEvent(BaseModel):
    payment_id: str = Field(min_length=1, max_length=80)
    account_id: str = Field(min_length=1, max_length=80)
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: Literal["settled", "pending", "reversed"]
    risk_score: int = Field(ge=0, le=100)


class ReceiptResult(BaseModel):
    payment_id: str
    action: Literal["stored", "manual_review", "ignored"]
    notification: Literal["receipt_ready", "risk_review_opened", "no_receipt_action"]
    object_keys: list[str]
    audit_reason: str


class StoragePort(Protocol):
    def presign_put(
        self, bucket: str, key: str, content_type: str, max_bytes: int, idempotency_key: str
    ) -> dict[str, object]:
        raise AssertionError

    def upload_signed(self, url: str, content: bytes, content_type: str) -> None:
        raise AssertionError


@dataclass(frozen=True)
class ReceiptPolicy:
    manual_review_score: int = 70
    thumbnail_size: tuple[int, int] = (320, 320)

    def decide(self, event: PaymentEvent) -> tuple[str, str, str]:
        if event.risk_score >= self.manual_review_score:
            return "manual_review", "risk_review_opened", "risk score met the review threshold"
        if event.status != "settled":
            return "ignored", "no_receipt_action", "payment is not settled"
        return "stored", "receipt_ready", "settled payment passed automatic review"


class ReceiptProcessor:
    def __init__(self, storage: StoragePort, bucket: str, policy: ReceiptPolicy | None = None) -> None:
        self.storage = storage
        self.bucket = bucket
        self.policy = policy or ReceiptPolicy()

    def process(self, event: PaymentEvent, image_bytes: bytes) -> ReceiptResult:
        action, notification, reason = self.policy.decide(event)
        if action != "stored":
            return ReceiptResult(
                payment_id=event.payment_id,
                action=action,
                notification=notification,
                object_keys=[],
                audit_reason=reason,
            )

        original, thumbnail = self._normalize(image_bytes)
        prefix = f"receipts/{event.account_id}/{event.payment_id}"
        objects = [(f"{prefix}/original.jpg", original), (f"{prefix}/thumbnail.jpg", thumbnail)]
        for key, content in objects:
            signed = self.storage.presign_put(
                self.bucket,
                key,
                "image/jpeg",
                len(content),
                f"{event.payment_id}:{key}",
            )
            self.storage.upload_signed(str(signed["url"]), content, "image/jpeg")

        return ReceiptResult(
            payment_id=event.payment_id,
            action="stored",
            notification="receipt_ready",
            object_keys=[key for key, _ in objects],
            audit_reason=reason,
        )

    def _normalize(self, source: bytes) -> tuple[bytes, bytes]:
        with Image.open(BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            original = self._jpeg(image)
            thumb = ImageOps.contain(image, self.policy.thumbnail_size)
            thumbnail = self._jpeg(thumb)
        return original, thumbnail

    @staticmethod
    def _jpeg(image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
        return output.getvalue()
