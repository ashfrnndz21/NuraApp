"""The documents behind a basis (E12-09): the lasting power of attorney, the doctor's
letter, the consent form he signed on paper — kept by reference, tagged, and read with
what each one backs.

A document is an artefact: its bytes are in the region's object store and the row names
them by key and digest (`app.memory.models.Artifact`). The `Document` row is the tag the
family screen shows. What a document backs — a consent given on a documented basis, a
stewardship opened on one — is read from the rows that cite the artefact, never copied.

A document the graph was set up on existed before the graph did (`set_up_for_someone`
takes it as `Evidence`, a reference). Uploading it afterwards finds the artefact by its
digest, puts the bytes behind it and tags it: one paper, one artefact, whichever came
first.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.consent.models import Consent, ConsentBasis
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.family.common import a_chief
from app.family.models import Document, DocumentTag
from app.identity.models import Stewardship
from app.ingestion.objects import ObjectStore, check_key, sha256_of
from app.ingestion.photos import MAX_PHOTO_BYTES, PHOTO_CONTENT_TYPES
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, SourceChannel

DOCUMENT_TARGET = Document.__tablename__
PDF_CONTENT_TYPE = "application/pdf"
DOCUMENT_KINDS = frozenset({ArtifactKind.PDF, ArtifactKind.PHOTO})


class NotADocument(Refusal):
    """A document is a PDF or a photo of a page, with bytes in it, and not too big."""


class DocumentTooLarge(NotADocument):
    """A document bigger than one a person keeps on paper: refused as it arrives (#133)."""


TAG_OF_BASIS: dict[ConsentBasis, DocumentTag] = {
    ConsentBasis.LPA: DocumentTag.LPA,
    ConsentBasis.MEDICAL_LETTER: DocumentTag.MEDICAL_LETTER,
}
"""The tag a cited document gets when nobody tagged it: from the basis it was cited as."""


def document_key(profile_id: uuid.UUID, digest: str) -> str:
    """Where a profile's document goes: under the profile, by its digest."""
    return f"documents/{profile_id}/{digest}"


def _kind_of(content_type: str) -> ArtifactKind:
    kind = content_type.strip().lower()
    if kind == PDF_CONTENT_TYPE:
        return ArtifactKind.PDF
    if kind in PHOTO_CONTENT_TYPES:
        return ArtifactKind.PHOTO
    raise NotADocument(f"{content_type} is not a document")


@audited(Action.WRITE, Scope.FAMILY, DOCUMENT_TARGET)
async def add_document(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    data: bytes,
    content_type: str,
    tag: DocumentTag,
    captured_at: datetime,
) -> Document:
    """Keep a document: bytes in the region's store, an artefact naming them, and the tag.

    The artefact is found by digest when the paper is already on the graph as a reference
    (the evidence a stewardship was opened on); otherwise it is stored like a photo is,
    under the record's scope, resting on the agreement to keep the record, in the region.
    """
    a_chief(context)
    kind = _kind_of(content_type)
    if not data:
        raise NotADocument("the document was empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise NotADocument(f"a document is at most {MAX_PHOTO_BYTES} bytes")
    digest = sha256_of(data)
    already = await audited_read(
        session, Artifact, context, Scope.RECORDS, where=(Artifact.sha256 == digest,)
    )
    if already:
        artifact = already[0]
        await store.put(check_key(artifact.storage_key), data)
    else:
        key = document_key(context.profile_id, digest)
        await store.put(key, data)
        artifact = await store_artifact(
            session,
            context=context,
            kind=kind,
            storage_key=key,
            content_type=content_type.strip().lower(),
            sha256=digest,
            captured_at=captured_at,
            source_channel=SourceChannel.APP,
            region=store.region,
        )
    return await audited_write(
        session,
        Document,
        context,
        Scope.FAMILY,
        artifact_id=artifact.id,
        tag=tag,
        added_by_person_id=context.person_id,
        added_at=utcnow(),
    )


@dataclass(frozen=True, slots=True)
class Backing:
    """One thing a document stands behind."""

    kind: str
    """`consent` or `stewardship`."""
    id: uuid.UUID
    basis: ConsentBasis
    purpose: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class DocumentView:
    artifact: Artifact
    tag: DocumentTag | None
    added_by_person_id: uuid.UUID | None
    added_at: datetime | None
    backs: list[Backing]


@audited(Action.READ, Scope.FAMILY, DOCUMENT_TARGET)
async def documents(session: AsyncSession, *, context: KeyContext) -> list[DocumentView]:
    """Every PDF or photo that is tagged as a document or cited as a basis, with what it
    backs. Owner and chief only: the papers behind a basis are the family list's."""
    a_chief(context)
    moment = utcnow()
    tagged = await audited_read(session, Document, context, Scope.FAMILY)
    consents = await audited_read(session, Consent, context, Scope.FAMILY)
    stewardships = await audited_read(session, Stewardship, context, Scope.PROFILE)
    consent_by_id = {consent.id: consent for consent in consents}

    wanted: set[uuid.UUID] = {row.artifact_id for row in tagged}
    wanted |= {c.basis_artifact_id for c in consents if c.basis_artifact_id is not None}
    if not wanted:
        return []
    artifacts = await audited_read(
        session, Artifact, context, Scope.RECORDS, where=(Artifact.id.in_(wanted),)
    )

    views: list[DocumentView] = []
    for artifact in sorted(artifacts, key=lambda a: as_utc(a.captured_at)):
        if artifact.kind not in DOCUMENT_KINDS:
            continue
        backs: list[Backing] = []
        for consent in consents:
            if consent.basis_artifact_id == artifact.id:
                backs.append(
                    Backing(
                        kind="consent",
                        id=consent.id,
                        basis=consent.basis,
                        purpose=consent.purpose.value,
                        active=consent.is_active(moment),
                    )
                )
        for stewardship in stewardships:
            behind = consent_by_id.get(stewardship.consent_id)
            if behind is not None and behind.basis_artifact_id == artifact.id:
                backs.append(
                    Backing(
                        kind="stewardship",
                        id=stewardship.id,
                        basis=stewardship.basis,
                        purpose=None,
                        active=stewardship.is_open(moment),
                    )
                )
        rows = sorted(
            (row for row in tagged if row.artifact_id == artifact.id),
            key=lambda row: as_utc(row.added_at),
        )
        tag = rows[-1].tag if rows else _tag_from(backs)
        views.append(
            DocumentView(
                artifact=artifact,
                tag=tag,
                added_by_person_id=rows[-1].added_by_person_id if rows else None,
                added_at=as_utc(rows[-1].added_at) if rows else None,
                backs=backs,
            )
        )
    return views


def _tag_from(backs: Sequence[Backing]) -> DocumentTag | None:
    for backing in backs:
        if backing.basis in TAG_OF_BASIS:
            return TAG_OF_BASIS[backing.basis]
    return None
