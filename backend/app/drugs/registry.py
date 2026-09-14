"""The port: what a drug registry answers, and in what shape.

Three questions. `identify` turns what a label or a pack says into the products the register
knows, best match first: the registration number is the strongest key, brand and strength the
fallback, the generic name the last. `interactions` screens a list of generics and names every
pair the licensed data flags, with a severity and a text id. `monograph` gives the patient-
information rules for one generic as ids — which missed-dose rule, which food rule, which
watch-outs, which things to avoid. Ids, not prose: the model never supplies the pharmacology,
and the registry never supplies the sentence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.errors import Refusal


class Severity(StrEnum):
    """How much an interaction matters, as the licensed data grades it. `DUPLICATE` is two
    medicines of the same kind on one list — a criterion, not an interaction, but it is
    screened at the same moment and shown the same way."""

    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class LabelFields:
    """What a label or a pack said, as the extractor read it. Any field may be missing."""

    registration_no: str | None = None
    brand: str | None = None
    generic: str | None = None
    strength: str | None = None
    form: str | None = None


@dataclass(frozen=True, slots=True)
class DrugMatch:
    """One product the register knows, and whether it is one of the high-risk kinds."""

    registration_no: str
    brand: str
    generic: str
    strength: str
    form: str
    drug_class: str
    high_risk: bool


@dataclass(frozen=True, slots=True)
class Interaction:
    """Two generics the licensed data flags together, how much it matters, and which text."""

    pair: tuple[str, str]
    severity: Severity
    text_id: str


@dataclass(frozen=True, slots=True)
class Monograph:
    """The patient-information rules for one generic, as ids into `app.medicines.strings`."""

    generic: str
    plain_name_id: str
    purpose_id: str
    food_rule_id: str
    missed_dose_rule_id: str
    watch_out_ids: tuple[str, ...] = field(default_factory=tuple)
    avoid_ids: tuple[str, ...] = field(default_factory=tuple)


class UnknownDrug(Refusal):
    """The register does not know this generic, so nothing about it can be said."""


class NotIdentified(Refusal):
    """What the label said matched no product in the register. Nothing is guessed."""


class DrugRegistry(Protocol):
    """Any licensed registry a deployment runs on answers these three."""

    def identify(self, label: LabelFields) -> Sequence[DrugMatch]:
        """The products that match, best first. Empty when nothing does."""
        ...

    def interactions(self, generics: Sequence[str]) -> Sequence[Interaction]:
        """Every flagged pair among these generics, worst first."""
        ...

    def monograph(self, generic: str) -> Monograph:
        """The rules for this generic, or `UnknownDrug`."""
        ...
