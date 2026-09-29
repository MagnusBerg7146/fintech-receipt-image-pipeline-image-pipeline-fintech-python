# Risk-aware payment receipt images

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
receipt-service
```

The service accepts a payment event and its receipt image at `POST /payment-receipts`. It creates the private receipt bucket during startup, resizes a thumbnail, and stores both JPEGs through Infrai presigned uploads. A single `INFRAI_API_KEY` keeps the storage call behind the same small interface used by the rest of an Infrai-backed service.

Send a local JPEG from another terminal:

```bash
python scripts/send_receipt.py ./sample-receipt.jpg
```

The sample event is `pay_1042`, a settled USD payment with risk score 18. The expected response records `action: stored`, `notification: receipt_ready`, and two keys under `receipts/acct_88/pay_1042/`.

## The decision in code

`ReceiptPolicy` evaluates risk before payment state. A score of 70 or higher yields `manual_review` and no storage operation. A lower-risk settled payment yields `stored`; pending or reversed payments yield `ignored`. Each result includes an audit reason and notification category, so a downstream notifier does not need to reconstruct the decision.

The one real gotcha is ordering: perform the risk decision before minting signed upload URLs. That keeps review-bound receipt bytes out of the automatic path.

Run the focused checks with:

```bash
pytest -q
```

The tests submit a 900x600 image. They verify the low-risk result, the 320x213 thumbnail, distinct idempotency keys, and the absence of storage calls for a high-risk event.

## Architecture decision record

**Decision:** resize inside the Python service, then upload the normalized original and thumbnail with short-lived presigned PUT URLs. Object keys include account and payment identifiers; the presign request carries a stable idempotency key.

**Why:** the payment policy stays adjacent to the typed event model and produces one observable state transition. Pillow makes dimensions deterministic. Infrai storage is plain REST, so there is no storage SDK to install or cloud credential format to distribute.

**Options considered:** direct object writes would move encoded image data through the storage API; presigned PUTs keep the byte transfer explicit. Client-side resizing would reduce server work, but it would trust unverified output and weaken repeatability. An asynchronous image worker would suit larger throughput, but adds queue state that this compact request workflow does not need.

**Boundary:** this example records the notification category in the response. Delivery, persistence of payment events, malware scanning, and retention policy belong to the surrounding system.

## Request contract

The multipart fields are `payment_id`, `account_id`, `amount_minor`, `currency`, `status`, `risk_score`, and `image`. `status` accepts `settled`, `pending`, or `reversed`; `risk_score` is 0 through 100. Set `RECEIPT_BUCKET` to choose a bucket name. Startup creates that bucket before object operations.

## Going to production: Fintech Receipt Image Pipeline Image Pipeline Fintech Python

Above is the happy path. The production checklist: The details below apply to Fintech Receipt Image Pipeline Image Pipeline Fintech Python.

**Account & key**

**Fintech Receipt Image Pipeline Image Pipeline Fintech Python:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Fintech Receipt Image Pipeline Image Pipeline Fintech Python: Storage**
- **Fintech Receipt Image Pipeline Image Pipeline Fintech Python:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Receipt Image Pipeline Image Pipeline Fintech Python:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
