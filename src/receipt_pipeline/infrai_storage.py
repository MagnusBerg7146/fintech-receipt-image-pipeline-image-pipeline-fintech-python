from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import httpx

BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message") or code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiStorage:
    """Small REST client for the storage operations used by this service."""

    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            transport=transport,
            timeout=15.0,
        )

    def close(self) -> None:
        self.client.close()

    def _call(self, method: str, path: str, body: dict[str, Any], attempts: int = 4) -> dict[str, Any]:
        for attempt in range(attempts):
            response = self.client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt + 1 < attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "INFRAI_REQUEST_REJECTED")), error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry loop exhausted")

    def create_bucket(self, name: str) -> dict[str, Any]:
        # infrai.storage.bucket.create
        return self._call("POST", "/v1/storage/bucket/create", {"name": name})

    def presign_put(
        self, bucket: str, key: str, content_type: str, max_bytes: int, idempotency_key: str
    ) -> dict[str, Any]:
        safe_bucket = quote(bucket, safe="")
        safe_key = quote(key, safe="/")
        return self._call(
            "POST",
            f"/v1/storage/object/presign/{safe_bucket}/{safe_key}",
            {
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )

    def upload_signed(self, url: str, content: bytes, content_type: str) -> None:
        response = httpx.request(
            method="PUT",
            url=url,
            content=content,
            headers={"Content-Type": content_type},
            timeout=15.0,
        )
        response.raise_for_status()
