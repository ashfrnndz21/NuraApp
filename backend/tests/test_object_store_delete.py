"""Deleting a profile's stored objects, the same on the laptop's directory and the bucket (#143).

The erasure of a closed account removes every object under `<kind>/<profile_id>/` for each kind
of object Nura keeps (`app.identity.closing.OBJECT_KINDS`). Both adapters of the object store
answer the same conformance here: a delete of a key, a delete of a missing key, one profile's
prefix taken whole and nothing beside it, and a prefix wider than one profile refused before
anything is touched. The bucket is kept in memory (httpx's mock transport), and pages its
listing two keys at a time, so the listing's continuation is walked too.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

import httpx
import pytest

from app.ingestion.objects import LocalObjectStore, NoSuchObject, NotAStorageKey, ObjectStore
from app.ingestion.s3 import S3ObjectStore
from app.regions import Region

PAGE = 2


class Bucket:
    """A bucket in memory: PUT, GET, DELETE, and a ListObjectsV2 that pages by two."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 ")
        key = request.url.path.lstrip("/")
        if request.method == "PUT":
            self.objects[key] = request.content
            return httpx.Response(200)
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        query = parse_qs(request.url.query.decode())
        if query.get("list-type") == ["2"]:
            prefix = query["prefix"][0]
            names = sorted(name for name in self.objects if name.startswith(prefix))
            start = int(query.get("continuation-token", ["0"])[0])
            page = names[start : start + PAGE]
            more = start + PAGE < len(names)
            body = (
                '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>"
                + (f"<NextContinuationToken>{start + PAGE}</NextContinuationToken>" if more else "")
                + "".join(f"<Contents><Key>{escape(name)}</Key></Contents>" for name in page)
                + "</ListBucketResult>"
            )
            return httpx.Response(200, content=body.encode())
        if key in self.objects:
            return httpx.Response(200, content=self.objects[key])
        return httpx.Response(404)


def _bucket_store() -> ObjectStore:
    return S3ObjectStore(
        "https://nura-sg.s3.ap-southeast-1.amazonaws.com/",
        Region.SG,
        signing_region="ap-southeast-1",
        access_key_id="AKIDNURA",
        secret_access_key="not-a-real-secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(Bucket())),
        now=lambda: datetime(2026, 9, 15, 2, 0, tzinfo=UTC),
    )


Make = Callable[[Path], ObjectStore]
ADAPTERS: dict[str, Make] = {
    "directory": lambda root: LocalObjectStore(root, Region.SG),
    "bucket": lambda root: _bucket_store(),
}


async def _gone(store: ObjectStore, key: str) -> bool:
    try:
        await store.get(key)
    except NoSuchObject:
        return True
    return False


@pytest.mark.parametrize("adapter", sorted(ADAPTERS))
async def test_a_key_is_deleted_and_a_missing_one_is_no_error(adapter: str, tmp_path: Path) -> None:
    store = ADAPTERS[adapter](tmp_path)
    pa = uuid.uuid4()
    await store.put(f"photos/{pa}/one", b"a photo")
    await store.delete(f"photos/{pa}/one")
    assert await _gone(store, f"photos/{pa}/one")
    await store.delete(f"photos/{pa}/never-was")


@pytest.mark.parametrize("adapter", sorted(ADAPTERS))
async def test_one_profiles_prefix_goes_whole_and_nothing_beside_it(
    adapter: str, tmp_path: Path
) -> None:
    store = ADAPTERS[adapter](tmp_path)
    pa, kit = uuid.uuid4(), uuid.uuid4()
    for n in range(5):  # more than a page of the bucket's listing
        await store.put(f"photos/{pa}/{n}", b"his")
    await store.put(f"photos/{kit}/0", b"someone else's")
    await store.put(f"voice/{pa}/fixture/abc", b"his card, said")
    assert await store.delete_prefix(f"photos/{pa}/") == 5
    assert all([await _gone(store, f"photos/{pa}/{n}") for n in range(5)])
    assert await store.get(f"photos/{kit}/0") == b"someone else's"
    assert await store.get(f"voice/{pa}/fixture/abc") == b"his card, said"
    assert await store.delete_prefix(f"voice/{pa}/") == 1
    assert await store.delete_prefix(f"photos/{uuid.uuid4()}/") == 0


@pytest.mark.parametrize("adapter", sorted(ADAPTERS))
@pytest.mark.parametrize("wide", ["photos/", "", "photos", "../photos/x/", "photos/not-a-profile/"])
async def test_a_prefix_wider_than_one_profile_is_refused(
    adapter: str, wide: str, tmp_path: Path
) -> None:
    store = ADAPTERS[adapter](tmp_path)
    with pytest.raises(NotAStorageKey):
        await store.delete_prefix(wide)


def test_both_adapters_answer_the_port() -> None:
    for name in ("delete", "delete_prefix"):
        assert callable(getattr(LocalObjectStore, name)) and callable(getattr(S3ObjectStore, name))
