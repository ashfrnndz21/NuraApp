"""D-4a — the same bytes, twice. Before this, every upload wrote a fresh `Artifact` row no
matter its digest (`audit-2026-09-22.md` §3.2: "No `SELECT … WHERE sha256 = …` anywhere") —
the same policy re-photographed, or a page re-sent by mistake, cost a second read, a second
model call, and a second set of "current" facts, silently.

`find_artifact_by_digest` is the check a caller runs before storing a photo or a PDF at all:
found, the bytes are not a new artefact — no store, no extractor, no second review card — the
existing paper's own card is what the person is shown, with a calm line naming when it was
added (`app.channels.api.capture`). Not found, the upload proceeds exactly as before, and the
new `(profile_id, sha256)` unique index (migration `0055`) is the backstop against two
concurrent uploads of the same bytes ever producing two rows.

This module is the exact-bytes half of D-4 only. The semantic half — the same paper,
re-photographed, under a different digest — is `app.ingestion.review._semantic_duplicate_of`,
which asks rather than silently filing (`PendingQuestion.DUPLICATE_PAPER`).
"""

from __future__ import annotations

from app.audit.access import audited, audited_read
from app.audit.models import Action
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.episodic import held_here
from app.memory.models import Artifact, ArtifactKind
from sqlalchemy.ext.asyncio import AsyncSession

PAPER_KINDS = (ArtifactKind.PHOTO, ArtifactKind.PDF)
"""What D-4a dedupes: the two kinds `POST .../photos` and `POST .../imports` write. A device
reading photo (`POST .../readings/photo`) and a voice note share the same `Artifact` table but
are not part of this check — a repeated device photo is not the failure mode the owner hit."""


@audited(Action.READ, Scope.RECORDS, Artifact.__tablename__)
async def find_artifact_by_digest(
    session: AsyncSession, *, context: KeyContext, sha256: str
) -> Artifact | None:
    """The existing paper artefact on this profile with this exact digest, if one is already
    on file — kind-restricted to `PAPER_KINDS`, in this deployment's own region
    (`held_here`), scoped to the profile the ordinary way (`audited_read`). `None` when this
    is genuinely new."""
    digest = sha256.strip().lower()
    found = await audited_read(
        session,
        Artifact,
        context,
        Scope.RECORDS,
        where=(Artifact.sha256 == digest, Artifact.kind.in_(PAPER_KINDS), held_here(context)),
        limit=1,
    )
    return found[0] if found else None


async def find_own_artifact_by_digest(
    session: AsyncSession, *, context: KeyContext, scope: Scope, kind: ArtifactKind, sha256: str
) -> Artifact | None:
    """The general form of `find_artifact_by_digest`, for a writer outside the paper kinds
    whose bytes are just as content-addressed — a question, typed words, a WhatsApp message,
    a device screen. The `(profile_id, sha256)` unique index (migration `0055`) makes a
    second row of the same bytes impossible for any kind, not only a paper's, so a writer
    whose caller can plausibly offer the same bytes twice checks first, the same way
    `find_artifact_by_digest` already does: found, the existing row is reused and nothing is
    written twice; not found, the write proceeds exactly as it always did."""
    digest = sha256.strip().lower()
    found = await audited_read(
        session,
        Artifact,
        context,
        scope,
        where=(Artifact.sha256 == digest, Artifact.kind == kind, held_here(context)),
        limit=1,
    )
    return found[0] if found else None


__all__ = ["PAPER_KINDS", "find_artifact_by_digest", "find_own_artifact_by_digest"]
