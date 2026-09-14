"""The label-photo rule for a high-risk drug (docs/medications-module.md §9, E16-04).

    High-risk drugs (warfarin, insulin, digoxin, methotrexate, opioids) require the label
    photo before the dose is saved; a verbal report is not enough.

`HIGH_RISK_CLASSES` is that sentence as a table: the five classes the document names and the
generic names each covers. It is a product rule written down, not pharmacology — identifying
a brand as one of these generics is the licensed drug data client's job (E04), and nothing
here is model output. `refuse_dose_without_label_photo` is the rule as a hook on
`app.memory.semantic.before_fact_write`: a medicine dose fact that names one of these drugs
and does not rest on a PHOTO artefact is refused before it is written, and the refusal is on
the trail like any other. It runs for every writer — the review card, WhatsApp, a voice note
— because it lives under the store, not in a surface.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts import FactDraft
from app.errors import Refusal
from app.keys.context import KeyContext
from app.memory import semantic
from app.memory.models import Artifact, ArtifactKind

HIGH_RISK_CLASSES: Mapping[str, frozenset[str]] = {
    "anticoagulant": frozenset({"warfarin"}),
    "insulin": frozenset(
        {
            "insulin",
            "insulin glargine",
            "insulin aspart",
            "insulin lispro",
            "insulin detemir",
            "insulin degludec",
            "isophane insulin",
        }
    ),
    "cardiac_glycoside": frozenset({"digoxin"}),
    "antimetabolite": frozenset({"methotrexate"}),
    "opioid": frozenset(
        {
            "morphine",
            "oxycodone",
            "codeine",
            "dihydrocodeine",
            "tramadol",
            "fentanyl",
            "buprenorphine",
            "pethidine",
            "hydromorphone",
        }
    ),
}
"""The five classes of docs/medications-module.md §9 and the generic names under each."""

MEDICINE_SUBJECTS = frozenset({"medicine", "medication"})
"""The subjects a medicine fact is written under (`app.keys.scopes.scope_for_subject`)."""

DOSE_ATTRIBUTES = frozenset({"dose"})
"""The attribute the rule guards: what to take and how often, which is what a label says."""

_NAMES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (danger, re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE))
    for danger, names in HIGH_RISK_CLASSES.items()
    for name in sorted(names, key=len, reverse=True)
)


class NotFromALabelPhoto(Refusal):
    """A high-risk drug's dose is saved from its label photo, never from words alone."""


def high_risk_class(name: str | None) -> str | None:
    """Which class a drug name falls in, or None. Matches whole words, so "Insulin Glargine
    (Lantus)" is insulin and "warfarin 5 mg" is an anticoagulant."""
    if not name:
        return None
    for danger, pattern in _NAMES:
        if pattern.search(name):
            return danger
    return None


def _strings_in(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for inner in value.values():
            yield from _strings_in(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from _strings_in(inner)


def names_high_risk(*values: Any) -> str | None:
    """The class of the first high-risk drug named anywhere in these values — a string, or
    the strings inside a JSON structure — or None."""
    for value in values:
        for text in _strings_in(value):
            danger = high_risk_class(text)
            if danger is not None:
                return danger
    return None


def is_a_dose(draft: FactDraft) -> bool:
    return draft.subject in MEDICINE_SUBJECTS and draft.attribute in DOSE_ATTRIBUTES


async def refuse_dose_without_label_photo(
    session: AsyncSession, context: KeyContext, draft: FactDraft
) -> None:
    """The rule, as `before_fact_write` sees it.

    A dose names its drug — in the subject, or inside its value (`{"drug": "warfarin", …}`,
    the shape the review card writes). If that drug is high-risk, the draft must rest on an
    artefact of kind PHOTO. An event alone (a message, a voice note), or a PDF or a
    screenshot, is refused. The artefact row was read a moment ago by `_check_provenance`
    under the writer's own key, so looking at its kind here writes no second line.
    """
    if not is_a_dose(draft):
        return
    danger = names_high_risk(draft.subject, draft.value)
    if danger is None:
        return
    if draft.artifact_id is None:
        raise NotFromALabelPhoto(f"a {danger} dose is saved from its label photo, not from words")
    artifact = await session.get(Artifact, draft.artifact_id)
    if (
        artifact is None
        or artifact.profile_id != context.profile_id
        or artifact.kind is not ArtifactKind.PHOTO
    ):
        raise NotFromALabelPhoto(
            f"a {danger} dose is saved from its label photo, not a {artifact and artifact.kind}"
        )


if refuse_dose_without_label_photo not in semantic.before_fact_write:
    semantic.before_fact_write.append(refuse_dose_without_label_photo)
