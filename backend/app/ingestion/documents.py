"""Importing a PDF: from a hospital portal, an email, or another app's share sheet (E02-03).

A PDF is stored the way a photo is (`app.ingestion.photos`): its bytes go to the object
store of the profile's region under a content-addressed key, and one Artifact of kind PDF
names them by key and digest. The checks come first — the bytes are a PDF, not empty, not
an archive's worth — and so does the agreement to hold the record, so a refusal leaves
nothing behind. Then the extractor reads every page, with the kind the person says it is
as a hint (a lab report, a hospital letter, an insurance letter), and the answer is a review
card whose fields each say which page they were read on. A PDF that is not a health paper
at all — a receipt — is an open card with no fields, and says so.

Where it came from (`DocumentSource`) is the person's word, kept on the card. The artefact
itself came in on the app, whichever of the three it was.

The key is `imports/<profile_id>/<sha256>`, apart from the family's documents
(`app.family.documents`, `documents/…`), which are papers behind a basis and tagged, not read.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.errors import Refusal
from app.ingestion.duplicates import find_own_artifact_by_digest
from app.ingestion.objects import ObjectStore, sha256_of
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import guard_region

PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"
"""The first five bytes of every PDF. A file that says it is one and does not start so is not."""

MAX_PDF_BYTES = 20 * 1024 * 1024
"""Twenty megabytes: a long hospital letter with scans, with room; not an archive."""


class NotAPdf(Refusal):
    """The bytes offered as a PDF were empty, or of another kind, or did not begin as one."""


class PdfTooLarge(Refusal):
    """A health paper as a PDF is not this big."""


def import_key(profile_id: uuid.UUID, digest: str) -> str:
    """Where an imported PDF goes: under the profile, by its digest."""
    return f"imports/{profile_id}/{digest}"


def check_pdf(data: bytes, content_type: str) -> str:
    """The content type, lower-cased, or a refusal: not a PDF, empty, or too big."""
    kind = content_type.strip().lower().split(";", 1)[0].strip()
    if kind != PDF_CONTENT_TYPE:
        raise NotAPdf(f"{content_type} is not a PDF")
    if not data:
        raise NotAPdf("the PDF was empty")
    if len(data) > MAX_PDF_BYTES:
        raise PdfTooLarge(f"a PDF is at most {MAX_PDF_BYTES} bytes")
    if not data.startswith(PDF_MAGIC):
        raise NotAPdf("the bytes do not begin as a PDF does")
    return kind


@audited(Action.WRITE, Scope.RECORDS, Artifact.__tablename__)
async def store_pdf(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    data: bytes,
    content_type: str,
    captured_at: datetime,
) -> Artifact:
    """Keep a PDF: bytes in the region's store under a content-addressed key, and the
    Artifact row that names them by key and digest. Nothing of the pages goes in the row."""
    guard_region(held_in=store.region, asked_from=context.region)
    kind = check_pdf(data, content_type)
    # Before any byte lands: keeping it rests on the agreement to hold the record.
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.RECORDS,
    )
    digest = sha256_of(data)
    # The same PDF again for this profile — a retried import, the onboarding sitting's own
    # PDF path (`app.onboarding.biography`), which does not go through `POST .../imports`'s
    # own D-4a check first — is the same bytes: migration 0055's `(profile_id, sha256)` index
    # makes a second row of them impossible, so this reuses the artefact already on file
    # rather than writing it twice (D-4a's pattern, `app.ingestion.duplicates`).
    existing = await find_own_artifact_by_digest(
        session, context=context, scope=Scope.RECORDS, kind=ArtifactKind.PDF, sha256=digest
    )
    if existing is not None:
        return existing
    key = import_key(context.profile_id, digest)
    await store.put(key, data)
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PDF,
        storage_key=key,
        content_type=kind,
        sha256=digest,
        captured_at=captured_at,
        source_channel=SourceChannel.APP,
        region=store.region,
    )
