"""The object store on a bucket: S3's protocol over httpx, signed with Signature Version 4.

A deployment keeps artefact bytes in a bucket in its own region (docs/trust/pdpa-data-map.md
§5: one bucket per region, in the region). Any S3-compatible store serves: AWS S3 in
ap-southeast-1, or Tigris on Fly. Two calls are all the port asks — put and get by key — so
this speaks them directly with the HTTP client the backend already has, signing each request
with the standard's HMAC chain, rather than adding a cloud SDK as a dependency.

Like `LocalObjectStore`, a store serves exactly one region, and the region is the first part
of every object's name (`SG/photos/<profile>/<sha256>`), so two stores on one bucket cannot
see each other's objects. The credentials are the platform's secrets
(NURA_OBJECT_ACCESS_KEY_ID, NURA_OBJECT_SECRET_ACCESS_KEY); they are never logged.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from app.ingestion.objects import NoSuchObject, check_key
from app.regions import Region

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "s3"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
TIMEOUT_SECONDS = 30.0


class ObjectStoreUnavailable(RuntimeError):
    """The bucket answered with something other than the object or its absence."""


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret_access_key: str, date: str, region: str, service: str) -> bytes:
    """The day's key: the secret, through HMAC with the date, the region, the service."""
    k_date = _hmac(f"AWS4{secret_access_key}".encode(), date)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    return _hmac(k_service, "aws4_request")


def _canonical_query(query: str) -> str:
    pairs = []
    for part in query.split("&") if query else []:
        name, _, value = part.partition("=")
        pairs.append((quote(name, safe="-_.~"), quote(value, safe="-_.~")))
    return "&".join(f"{name}={value}" for name, value in sorted(pairs))


def authorization(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload_sha256: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    service: str,
    amz_date: str,
) -> str:
    """The `Authorization` header for one request. Every header given is signed, so give
    `host` and `x-amz-date` (and, for S3, `x-amz-content-sha256`)."""
    parts = urlsplit(url)
    canonical_headers = {name.lower(): " ".join(value.split()) for name, value in headers.items()}
    signed = ";".join(sorted(canonical_headers))
    canonical_request = "\n".join(
        [
            method,
            parts.path or "/",
            _canonical_query(parts.query),
            "".join(f"{name}:{canonical_headers[name]}\n" for name in sorted(canonical_headers)),
            signed,
            payload_sha256,
        ]
    )
    scope = f"{amz_date[:8]}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [ALGORITHM, amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    key = signing_key(secret_access_key, amz_date[:8], region, service)
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{ALGORITHM} Credential={access_key_id}/{scope}, SignedHeaders={signed}, Signature={signature}"


def _real_now() -> datetime:
    # The signature carries the real time: a bucket refuses a request dated more than a few
    # minutes off. This is protocol, not a timestamp Nura keeps, so it is not `app.clock`.
    return datetime.now(UTC)


class S3ObjectStore:
    """Bytes in, bytes out, by key, in one region's bucket."""

    def __init__(
        self,
        bucket_url: str,
        region: Region,
        *,
        signing_region: str,
        access_key_id: str,
        secret_access_key: str,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] = _real_now,
    ) -> None:
        if not bucket_url.startswith("https://") and not bucket_url.startswith("http://"):
            raise ValueError("NURA_OBJECT_BUCKET_URL is the bucket's https base URL")
        self._base = bucket_url.rstrip("/")
        self._region = region
        self._signing_region = signing_region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        self._now = now

    @property
    def region(self) -> Region:
        return self._region

    def url_of(self, key: str) -> str:
        return f"{self._base}/{self._region.value}/{check_key(key)}"

    def _signed(self, method: str, url: str, payload_sha256: str) -> dict[str, str]:
        amz_date = self._now().strftime("%Y%m%dT%H%M%SZ")
        headers = {
            "host": urlsplit(url).netloc,
            "x-amz-content-sha256": payload_sha256,
            "x-amz-date": amz_date,
        }
        headers["authorization"] = authorization(
            method=method,
            url=url,
            headers=headers,
            payload_sha256=payload_sha256,
            access_key_id=self._access_key_id,
            secret_access_key=self._secret_access_key,
            region=self._signing_region,
            service=SERVICE,
            amz_date=amz_date,
        )
        return headers

    async def put(self, key: str, data: bytes) -> None:
        url = self.url_of(key)
        headers = self._signed("PUT", url, hashlib.sha256(data).hexdigest())
        response = await self._client.put(url, content=data, headers=headers)
        if response.status_code != 200:
            raise ObjectStoreUnavailable(f"the bucket refused a put ({response.status_code})")

    async def get(self, key: str) -> bytes:
        url = self.url_of(key)
        response = await self._client.get(url, headers=self._signed("GET", url, EMPTY_SHA256))
        if response.status_code == 404:
            raise NoSuchObject(f"nothing stored under {key} in {self._region}")
        if response.status_code != 200:
            raise ObjectStoreUnavailable(f"the bucket refused a get ({response.status_code})")
        return response.content
