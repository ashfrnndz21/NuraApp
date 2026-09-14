"""The bucket store signs the way the standard says, and keeps a region's bytes under it.

The signing is checked against the two worked examples AWS publishes for Signature Version 4
(the IAM `ListUsers` request and S3's `GET /test.txt`), so it is right by the standard and not
merely by agreement with itself. The store is then run against a bucket kept in memory
(httpx's mock transport): no network, no live service.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from app.ingestion.objects import NoSuchObject
from app.ingestion.s3 import EMPTY_SHA256, S3ObjectStore, authorization, signing_key
from app.regions import Region


def test_the_signing_key_of_the_published_example() -> None:
    key = signing_key("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "20150830", "us-east-1", "iam")
    assert key.hex() == "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9"


def test_the_published_iam_example_signs_to_its_signature() -> None:
    header = authorization(
        method="GET",
        url="https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Host": "iam.amazonaws.com",
            "X-Amz-Date": "20150830T123600Z",
        },
        payload_sha256=EMPTY_SHA256,
        access_key_id="AKIDEXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        service="iam",
        amz_date="20150830T123600Z",
    )
    assert header == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/iam/aws4_request, "
        "SignedHeaders=content-type;host;x-amz-date, "
        "Signature=5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7"
    )


def test_the_published_s3_get_example_signs_to_its_signature() -> None:
    header = authorization(
        method="GET",
        url="https://examplebucket.s3.amazonaws.com/test.txt",
        headers={
            "Host": "examplebucket.s3.amazonaws.com",
            "Range": "bytes=0-9",
            "x-amz-content-sha256": EMPTY_SHA256,
            "x-amz-date": "20130524T000000Z",
        },
        payload_sha256=EMPTY_SHA256,
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        service="s3",
        amz_date="20130524T000000Z",
    )
    assert header.endswith(
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


class Bucket:
    """A bucket in memory that insists every request is signed and says what it carries."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        assert request.headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=AKIDNURA/20260915/ap-southeast-1/s3/aws4_request"
        )
        body = request.content
        assert request.headers["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
        path = request.url.path
        if request.method == "PUT":
            self.objects[path] = body
            return httpx.Response(200)
        if path in self.objects:
            return httpx.Response(200, content=self.objects[path])
        return httpx.Response(404)


def _store(bucket: Bucket, region: Region = Region.SG) -> S3ObjectStore:
    return S3ObjectStore(
        "https://nura-sg.s3.ap-southeast-1.amazonaws.com/",
        region,
        signing_region="ap-southeast-1",
        access_key_id="AKIDNURA",
        secret_access_key="not-a-real-secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(bucket)),
        now=lambda: datetime(2026, 9, 15, 2, 0, tzinfo=UTC),
    )


async def test_bytes_go_in_under_the_region_and_come_back_out() -> None:
    bucket = Bucket()
    store = _store(bucket)
    await store.put("photos/abc/0123", b"\x89PNG placeholder")
    assert set(bucket.objects) == {"/SG/photos/abc/0123"}
    assert await store.get("photos/abc/0123") == b"\x89PNG placeholder"
    assert all(r.url.host == "nura-sg.s3.ap-southeast-1.amazonaws.com" for r in bucket.seen)


async def test_one_regions_store_cannot_read_the_others_bytes() -> None:
    bucket = Bucket()
    await _store(bucket, Region.SG).put("photos/abc/0123", b"sg")
    with pytest.raises(NoSuchObject):
        await _store(bucket, Region.MY).get("photos/abc/0123")


async def test_a_bad_key_never_reaches_the_bucket() -> None:
    bucket = Bucket()
    with pytest.raises(Exception, match="storage key"):
        await _store(bucket).put("../escape", b"x")
    assert bucket.seen == []
