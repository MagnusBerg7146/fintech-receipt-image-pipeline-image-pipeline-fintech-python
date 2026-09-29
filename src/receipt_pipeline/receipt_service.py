from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .infrai_storage import InfraiError, InfraiStorage
from .payment_workflow import PaymentEvent, ReceiptProcessor, ReceiptResult

BUCKET = os.environ.get("RECEIPT_BUCKET", "fintech-receipts")
storage: InfraiStorage | None = None
processor: ReceiptProcessor | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global storage, processor
    storage = InfraiStorage()
    storage.create_bucket(BUCKET)
    processor = ReceiptProcessor(storage, BUCKET)
    yield
    storage.close()


app = FastAPI(title="Receipt image pipeline", lifespan=lifespan)


@app.post("/payment-receipts", response_model=ReceiptResult)
async def payment_receipt(
    payment_id: str = Form(),
    account_id: str = Form(),
    amount_minor: int = Form(),
    currency: str = Form(),
    status: str = Form(),
    risk_score: int = Form(),
    image: UploadFile = File(),
) -> ReceiptResult:
    event = PaymentEvent.model_validate(
        {
            "payment_id": payment_id,
            "account_id": account_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "status": status,
            "risk_score": risk_score,
        }
    )
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="receipt image is empty")
    if processor is None:
        raise HTTPException(status_code=503, detail="service is starting")
    try:
        return processor.process(event, content)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=client_status, detail={"code": exc.code, "message": str(exc)}) from exc


def run() -> None:
    import uvicorn

    uvicorn.run("receipt_pipeline.receipt_service:app", host="127.0.0.1", port=8000)
