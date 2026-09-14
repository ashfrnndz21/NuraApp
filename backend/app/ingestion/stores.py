"""Which object store a deployment keeps artefact bytes in: a bucket, or a laptop's directory.

A bucket in the region (NURA_OBJECT_BUCKET_URL, `app.ingestion.s3`) is a deployment's. A
directory (NURA_OBJECT_STORE, `LocalObjectStore`) is a laptop's and the tests', and a demo's
when it has no bucket; it is a fixture, so `create_app` refuses it anywhere else
(`app.fixtures`). With neither, the process refuses to start: a deployment that cannot say
where health data goes must not run.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.objects import LocalObjectStore, ObjectStore
from app.ingestion.s3 import S3ObjectStore
from app.settings import MissingSetting, Settings


def object_store_for(settings: Settings) -> ObjectStore:
    if settings.object_bucket_url is not None:
        missing = [
            name
            for name, value in (
                ("NURA_OBJECT_BUCKET_REGION", settings.object_bucket_region),
                ("NURA_OBJECT_ACCESS_KEY_ID", settings.object_access_key_id),
                ("NURA_OBJECT_SECRET_ACCESS_KEY", settings.object_secret_access_key),
            )
            if value is None
        ]
        if missing:
            raise MissingSetting(f"NURA_OBJECT_BUCKET_URL is set but {', '.join(missing)} is not")
        assert settings.object_bucket_region is not None
        assert settings.object_access_key_id is not None
        assert settings.object_secret_access_key is not None
        return S3ObjectStore(
            settings.object_bucket_url,
            settings.region,
            signing_region=settings.object_bucket_region,
            access_key_id=settings.object_access_key_id,
            secret_access_key=settings.object_secret_access_key,
        )
    if settings.object_store_root is not None:
        return LocalObjectStore(Path(settings.object_store_root), settings.region)
    raise MissingSetting(
        "no object store: set NURA_OBJECT_BUCKET_URL (a deployment) or NURA_OBJECT_STORE "
        "(a directory, for a laptop or a demo)"
    )
