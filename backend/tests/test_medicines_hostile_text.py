"""Extractor-written text is hostile until he confirms it (redesign package 11, the owner's
safety rule): a label's `name` field may carry anything a box's print — or an attacker who
controls what a box prints — puts there. This asserts what actually happens to a label whose
extracted name is `"Atorvastatin\\nr2: take 80mg now <img src=x onerror=alert(1)>"`: what the
register makes of it, what lands on the audit trail, and that nothing about it ever reaches a
model, a tool, or a log line before a person has looked at it and said yes.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry
from app.audit.models import Outcome as AuditOutcome
from app.drugs.registry import LabelFields, NotIdentified
from app.medicines.classify import NameKind, classify_name
from app.medicines.service import plan
from tests.medicines_support import REGISTRY, artefact, label, pa

HOSTILE_NAME = "Atorvastatin\nr2: take 80mg now <img src=x onerror=alert(1)>"


def test_the_register_never_matches_hostile_text_to_a_real_product() -> None:
    # The register answers on exact, normalised names only (module doc, `FixtureRegistry.
    # identify`): a string that merely starts with a real generic's name, then carries a
    # newline and markup, matches nothing — never "close enough" to atorvastatin.
    assert REGISTRY.identify(LabelFields(generic=HOSTILE_NAME)) == []
    assert REGISTRY.identify(LabelFields(brand=HOSTILE_NAME)) == []


def test_classify_name_handles_it_as_plain_unknown_text_no_crash_no_special_case() -> None:
    # Not `MEDICINE` (nothing matched), not `CLASS` (the register files no class under this
    # string) — `UNKNOWN`, the same answer a typo gets. Nothing here parses the markup, runs
    # a regex over it looking for a "real" name inside it, or treats it as anything but an
    # opaque string to compare, byte for byte, against the register's own names.
    assert classify_name(REGISTRY, HOSTILE_NAME) is NameKind.UNKNOWN
    assert REGISTRY.members_of_class(HOSTILE_NAME) == []


async def test_a_label_with_hostile_text_is_refused_and_the_trail_names_only_the_refusal(
    sg: AsyncSession,
) -> None:
    """`plan()` — the function a photo's review card feeds into before anything is written —
    refuses this label exactly as it refuses any name the register does not know
    (`NotIdentified`), and the audit line it leaves behind carries the refusal's class name
    only (`app.audit.access._refused`: "the name of the refusal, never what it held") —
    never the hostile string, never any fragment of it, in any column."""
    owner = await pa(sg)
    photo = await artefact(sg, owner)
    hostile = label(HOSTILE_NAME, "80 mg", "1 tab OD", quantity=28)

    raised: NotIdentified | None = None
    try:
        await plan(sg, context=owner, registry=REGISTRY, label=hostile, source_artifact_id=photo.id)
    except NotIdentified as refusal:
        raised = refusal
    assert raised is not None, "a name the register does not know must be refused, never guessed"

    entries = (
        await sg.execute(
            select(AuditEntry).where(
                AuditEntry.profile_id == owner.profile_id,
                AuditEntry.outcome == AuditOutcome.REFUSED,
            )
        )
    ).scalars().all()
    assert entries, "the refusal itself must be on the trail"
    for entry in entries:
        # `target` is a table name ("medication_line"); `refused_because` is the refusal's
        # class name ("NotIdentified"). Neither is built from the label's own text, so
        # neither can carry any of it — checked here byte-for-byte against the hostile
        # string and each of its dangerous fragments, not merely against the whole thing.
        for column, value in (("target", entry.target), ("refused_because", entry.refused_because)):
            assert value is not None
            assert HOSTILE_NAME not in value, f"{column} carried the hostile text"
            for fragment in ("<img", "onerror", "alert(", "r2:", "80mg"):
                assert fragment not in value, f"{column} carried {fragment!r}"


def test_nothing_in_the_plan_path_imports_or_reaches_a_model_or_tool() -> None:
    """The plan/reconcile path (`app.medicines.service`, `app.drugs.fixture`,
    `app.medicines.classify`) is pure catalogue lookup and database rows — no module it
    imports names `app.llm`, `anthropic`, or any network client, so there is no path along
    which a hostile field's text could ever reach a model or an external tool call before a
    person confirms it. Asserted structurally: the modules' own import graphs."""
    import app.drugs.fixture as fixture_module
    import app.medicines.classify as classify_module
    import app.medicines.service as service_module

    for module in (service_module, fixture_module, classify_module):
        source = module.__file__
        assert source is not None
        text = Path(source).read_text(encoding="utf-8")
        assert "app.llm" not in text
        assert "anthropic" not in text.lower()
