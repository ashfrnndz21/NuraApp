"""The label-photo rule for a high-risk drug (docs/medications-module.md §9, E16-04).

    High-risk drugs (warfarin, insulin, digoxin, methotrexate, opioids) require the label
    photo before the dose is saved; a verbal report is not enough.

`HIGH_RISK_CLASSES` is that sentence as a table: the five classes the document names and the
generic names each covers. It is a product rule written down, not pharmacology — identifying
a brand as one of these generics is the licensed drug data client's job (E04), and nothing
here is model output. `refuse_dose_without_label_photo` is the rule as a hook on
`app.memory.semantic.before_fact_write`: a medicine fact that names one of these drugs — by
generic name anywhere in it, or by the `drug_class` the registry put on a medicine line's
value — and does not rest on a PHOTO artefact is refused before it is written, and the
refusal is on the trail like any other. It runs for every writer — the review card, the
medicines module, WhatsApp, a voice note — because it lives under the store, not in a
surface. The medicines module (E04) checks the same rule at its own door first, so the
person is told before a yes is spent; this hook is the floor under it.
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

DOSE_ATTRIBUTES = frozenset({"dose", "amount", "start", "stop", "frequency", "strength"})
"""The attributes the rule guards, whatever the subject: what to take, how much, how often,
starting and stopping — what a label says, and what a voice might say. Keyed on the attribute
and not on the subject, because subjects are free codes: a fact `warfarin.dose` from a
transcript is a dose as much as `medicine.dose` from a card is (E05 review, B4)."""

LINE_ATTRIBUTES = ("line:", "supply:")
"""The attributes the medicines module (E04) writes — `line:<generic>`, `supply:<generic>` —
which carry the dose inside the value, so the rule guards them too."""

MEDICATION = "medication"
"""The subject the medicines module writes every medicine fact under."""

_NAMES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (danger, re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE))
    for danger, names in HIGH_RISK_CLASSES.items()
    for name in sorted(names, key=len, reverse=True)
)


class HighRiskNeedsLabelPhoto(Refusal):
    """A high-risk drug's dose is saved from its label photo, never from words alone. Carries
    the class, so the answer can name it."""

    def __init__(self, drug_class: str, message: str | None = None) -> None:
        super().__init__(message or f"a {drug_class} is saved from its label photo, not from words")
        self.drug_class = drug_class


def is_high_risk(drug_class: str | None) -> bool:
    """Whether a registry class code is one of the five."""
    return drug_class is not None and drug_class.lower() in HIGH_RISK_CLASSES


def class_of(value: Any) -> str | None:
    """The high-risk class a medicine line's value carries, from the registry: its
    `drug_class` when that is one of the five, or `high_risk` marked true with no class."""
    if not isinstance(value, Mapping):
        return None
    drug_class = value.get("drug_class")
    if isinstance(drug_class, str) and is_high_risk(drug_class):
        return drug_class.lower()
    if value.get("high_risk") is True:
        return "high_risk"
    return None


_CODE_JOINS = re.compile(r"[_.\-]+|(?<=[a-z0-9])(?=[A-Z])")


def as_words(text: str) -> str:
    """A code read as words: `warfarin_level`, `warfarin-level`, `warfarin.level` and
    `warfarinLevel` all become "warfarin level", so a whole-word match sees the drug. An
    underscore is a word character to a regex, and a code is exactly where one hides."""
    return _CODE_JOINS.sub(" ", text)


def high_risk_class(name: str | None) -> str | None:
    """Which class a drug name falls in, or None. Matches whole words, so "Insulin Glargine
    (Lantus)" is insulin and "warfarin 5 mg" is an anticoagulant — and a code is read as
    words first, so "warfarin_level" is too."""
    if not name:
        return None
    text = as_words(name)
    for danger, pattern in _NAMES:
        if pattern.search(text):
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
    """A fact that says what to take: any subject with a dose attribute (`DOSE_ATTRIBUTES`),
    or a medicine line or supply of the medicines module, whose value carries the dose. The
    subject is not consulted: whether the drug is high-risk is read from the subject and the
    value together, after this."""
    return draft.attribute in DOSE_ATTRIBUTES or (
        draft.subject in MEDICINE_SUBJECTS and draft.attribute.startswith(LINE_ATTRIBUTES)
    )


async def refuse_dose_without_label_photo(
    session: AsyncSession, context: KeyContext, draft: FactDraft
) -> None:
    """The rule, as `before_fact_write` sees it.

    A dose names its drug — in the subject, inside its value (`{"drug": "warfarin", …}`,
    the shape the review card writes), or by the class the registry put on it
    (`{"drug_class": "anticoagulant", …}`, the shape the medicines module writes). If EITHER
    names a high-risk drug, the draft must rest on an artefact of kind PHOTO. An event alone
    (a message, a voice note), or a PDF or a screenshot, is refused. The artefact row was
    read a moment ago by `_check_provenance` under the writer's own key, so looking at its
    kind here writes no second line.
    """
    if not is_a_dose(draft):
        return
    danger = names_high_risk(draft.subject, draft.value) or class_of(draft.value)
    if danger is None:
        return
    if draft.artifact_id is None:
        raise HighRiskNeedsLabelPhoto(danger)
    artifact = await session.get(Artifact, draft.artifact_id)
    if (
        artifact is None
        or artifact.profile_id != context.profile_id
        or artifact.kind is not ArtifactKind.PHOTO
    ):
        raise HighRiskNeedsLabelPhoto(
            danger,
            f"a {danger} dose is saved from its label photo, not a {artifact and artifact.kind}",
        )


if refuse_dose_without_label_photo not in semantic.before_fact_write:
    semantic.before_fact_write.append(refuse_dose_without_label_photo)
