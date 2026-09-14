"""The object store: where an artefact's bytes live, pinned to one region.

The database holds a storage key and a digest; the bytes are here and nowhere else. A store
serves exactly one region, so a deployment cannot be handed a store for the other country by
mistake and a key can never point across the causeway. `LocalObjectStore` is the one that
runs on a laptop and in the tests — files under a directory, one subdirectory per region;
a bucket in the region is a later adapter behind the same protocol.

The key is content-addressed under the profile: `photos/<profile_id>/<sha256>`. The same
photo stored twice is the same object, and nothing in the key says what the photo shows.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import ClassVar, Protocol

from app.errors import Refusal
from app.regions import Region

_KEY = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,510}$")


class NotAStorageKey(Refusal):
    """A storage key is a short path of plain characters. This was empty, or something else."""


class NoSuchObject(Refusal):
    """Nothing is stored under that key in this region."""


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def photo_key(profile_id: uuid.UUID, digest: str) -> str:
    """Where a profile's photo goes: under the profile, by its digest."""
    return f"photos/{profile_id}/{digest}"


def check_key(key: str) -> str:
    if not _KEY.match(key) or ".." in key:
        raise NotAStorageKey("a storage key is a short path of plain characters")
    return key


class ObjectStore(Protocol):
    """Bytes in, bytes out, by key, in one region."""

    @property
    def region(self) -> Region: ...

    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...


class LocalObjectStore:
    """Files under `root/<region>/`, for a laptop and the tests.

    The region is part of the path, so two stores over one root cannot see each other's
    objects. Writes land on a temporary name and are renamed into place, so a reader never
    sees half a file.
    """

    FIXTURE: ClassVar[bool] = True
    """A fixture: runs only on a declared dev run or demo (`app.fixtures`)."""

    def __init__(self, root: Path, region: Region) -> None:
        self._root = Path(root) / region.value
        self._region = region

    @property
    def region(self) -> Region:
        return self._region

    @property
    def root(self) -> Path:
        """This region's directory: what a demo's night wipe empties."""
        return self._root

    def path_of(self, key: str) -> Path:
        return self._root / check_key(key)

    async def put(self, key: str, data: bytes) -> None:
        target = self.path_of(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        partial.write_bytes(data)
        partial.replace(target)

    async def get(self, key: str) -> bytes:
        target = self.path_of(key)
        if not target.is_file():
            raise NoSuchObject(f"nothing stored under {key} in {self._region}")
        return target.read_bytes()
