from __future__ import annotations

import argparse
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a payment receipt to the local service")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    with args.image.open("rb") as receipt:
        response = httpx.request(
            method="POST",
            url="http://127.0.0.1:8000/payment-receipts",
            data={
                "payment_id": "pay_1042",
                "account_id": "acct_88",
                "amount_minor": "1299",
                "currency": "USD",
                "status": "settled",
                "risk_score": "18",
            },
            files={"image": (args.image.name, receipt, "image/jpeg")},
            timeout=20.0,
        )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
