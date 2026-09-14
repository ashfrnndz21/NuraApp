"""The high-risk drug rule: no label photo, no dose.

Warfarin, insulin, digoxin, methotrexate and the opioids are the kinds a wrong dose hurts
fastest, so a line or a dose for one of them is saved only from a label photo — never from a
voice note, a message or typed words alone (docs/medications-module.md, section 9). The rule is
by class, from the licensed registry's `drug_class`, and the refusal names the class.

Two doors enforce it. The medicines service checks the artefact before it builds the draft, so
the person is told before anything is written. And `label_photo_rule` is registered on the
memory store's `before_fact_write`, so a medication fact for a high-risk class cannot land by
any other path either — the table's floor, not the service's manners.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.context import KeyContext
from app.memory.episodic import require_artifact
from app.memory.models import ArtifactKind

HIGH_RISK_CLASSES: frozenset[str] = frozenset(
    {
        "anticoagulant",  # warfarin
        "insulin",  # every insulin
        "cardiac_glycoside",  # digoxin
        "antimetabolite",  # methotrexate
        "opioid",  # morphine, tramadol, codeine, fentanyl, oxycodone
    }
)
"""The classes a label photo is required for, by the registry's class code."""

MEDICATION = "medication"
"""The fact subject every medicine fact is written under (`app.keys.scopes` puts it under the
medicines scope)."""


def is_high_risk(drug_class: str | None) -> bool:
    return drug_class is not None and drug_class.lower() in HIGH_RISK_CLASSES


class HighRiskNeedsLabelPhoto(Refusal):
    """A medicine of this class is saved from the label photo, never from words alone."""

    def __init__(self, drug_class: str) -> None:
        super().__init__(f"a {drug_class} is saved from a label photo, not from words alone")
        self.drug_class = drug_class


def class_of(value: Any) -> str | None:
    """The drug class a medication fact's value carries, if it is the structured kind."""
    if isinstance(value, Mapping):
        drug_class = value.get("drug_class")
        if isinstance(drug_class, str):
            return drug_class
        if value.get("high_risk") is True:
            return "high_risk"
    return None


async def label_photo_rule(session: AsyncSession, context: KeyContext, draft: FactDraft) -> None:
    """The hook: a medication fact whose class is high-risk must cite a photo artefact.

    Runs after every check the memory store makes and before anything is written. The
    artefact is read under the writer's own context — the store has already required it as
    provenance — and must be a PHOTO: the label, not a voice note or a message.
    """
    if draft.subject != MEDICATION:
        return
    drug_class = class_of(draft.value)
    if not is_high_risk(drug_class) and drug_class != "high_risk":
        return
    assert drug_class is not None
    if draft.artifact_id is None:
        raise HighRiskNeedsLabelPhoto(drug_class)
    artifact = await require_artifact(session, context=context, artifact_id=draft.artifact_id)
    if artifact.kind is not ArtifactKind.PHOTO:
        raise HighRiskNeedsLabelPhoto(drug_class)
