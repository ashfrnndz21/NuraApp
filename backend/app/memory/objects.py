"""The object store: where an artefact's bytes go before `store_artifact` writes them down.

The port is `ObjectStore`; the rows in `app.memory.models.Artifact` only ever name a key in
it. `LocalObjectStore` is a directory on the machine running a local backend — enough for a
dev run, and one region's process writes only under its own region. `MemoryObjectStore`
holds bytes for the length of a test. A deployment puts the regional bucket behind the same
port and nothing above this module changes.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.regions import Region

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
    "audio/mpeg": "mp3",
}


@dataclass(frozen=True, slots=True)
class Stored:
    storage_key: str
    sha256: str
    size: int


def _key(region: Region, profile_id: uuid.UUID, digest: str, content_type: str) -> str:
    extension = _EXTENSIONS.get(content_type.lower(), "bin")
    return f"{region.value.lower()}/profiles/{profile_id}/{digest}.{extension}"


class ObjectStore(Protocol):
    def put(
        self, *, region: Region, profile_id: uuid.UUID, content: bytes, content_type: str
    ) -> Stored: ...


class MemoryObjectStore:
    """Bytes for the length of a test."""

    def __init__(self) -> None:
        self.held: dict[str, bytes] = {}

    def put(
        self, *, region: Region, profile_id: uuid.UUID, content: bytes, content_type: str
    ) -> Stored:
        digest = hashlib.sha256(content).hexdigest()
        key = _key(region, profile_id, digest, content_type)
        self.held[key] = content
        return Stored(storage_key=key, sha256=digest, size=len(content))


class LocalObjectStore:
    """A directory on the local machine, for `make dev`. Not a deployment's store."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(
        self, *, region: Region, profile_id: uuid.UUID, content: bytes, content_type: str
    ) -> Stored:
        digest = hashlib.sha256(content).hexdigest()
        key = _key(region, profile_id, digest, content_type)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        return Stored(storage_key=key, sha256=digest, size=len(content))
