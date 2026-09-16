"""The port: what a drug registry answers, and in what shape.

Three questions. `identify` turns what a label or a pack says into the products the register
knows, best match first: the registration number is the strongest key, brand and strength the
fallback, the generic name the last. `interactions` screens a list of generics and names every
pair the licensed data flags, with a severity and a text id. `monograph` gives the patient-
information rules for one generic as ids — which missed-dose rule, which food rule, which
watch-outs, which things to avoid. Ids, not prose: the model never supplies the pharmacology,
and the registry never supplies the sentence.

A product is not always a prescription medicine (E04-03): `ProductKind` says which of the
three it is, and a supplement or a traditional remedy is screened for interactions the same
way a tablet is — never pretended to be one, never left out of the screen. `Interaction.source`
is what a pharmacist would check the pair against, and `review_state` says whether a pharmacist
already has: an `AWAITING_REVIEW` pair is still flagged, never silently dropped, but rendered
as a question to ask rather than a claim not yet checked (`app.medicines.story`).

`identify` never returns a bare match: every `DrugMatch` carries a `confidence`, scored on how
much of the label's own words actually correspond to that product — an exact registration
number is certain; an exact brand or generic name whose strength and form also line up is
high; a name match whose strength or form does not belong to that product is low (#206). A
match is not a guess dressed up as one: the score says how sure the register is, and
`app.medicines.service` refuses to identify anything below `CONFIDENCE_THRESHOLD`
(`app.ingestion.models`) — the same floor a document field and a WhatsApp voice transcript are
already held to, so a person is never told his tablet is named when Nura is only guessing.

Not every caller of `identify` needs that floor: `app.safety.health_words`, `app.reasoning.
visits.summary` and `app.delivery.feed.compose` ask only "does the register know this name at
all" or read the generic off the best match, for text detection and feed copy — never to
write a dose or a line — so a name match's confidence has nothing below-floor to filter for
them by design. `app.medicines.service._one_product` is the one caller that turns an answer
into a medicine on the record, and it is the one that checks the score.
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


class ProductKind(StrEnum):
    """What kind of product this is. A prescription medicine, a supplement (a vitamin, a
    mineral or a Western-style herbal product), or a traditional remedy (TCM). Screened for
    interactions the same way; never rendered as though it were a prescription medicine."""

    PRESCRIPTION = "prescription"
    SUPPLEMENT = "supplement"
    TCM = "tcm"


class ReviewState(StrEnum):
    """Whether a pharmacist has already checked this interaction pair against its source."""

    REVIEWED = "reviewed"
    AWAITING_REVIEW = "awaiting_review"


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
    """One product the register knows, whether it is one of the high-risk kinds, and how sure
    the register is that this is the product the label meant (#206) — 1.0 for a registration
    number, or a name whose strength and form the label gave both belong to this product;
    lower wherever the label named a strength or a form that does not.

    `product_name` is the register's own listed name for the product, which may differ from
    `brand` (a pack's own front-of-box name); `licence_status` is the register's word for
    whether the product's licence still stands; `active_ingredients` is every ingredient the
    register lists for the product — `(generic,)` for almost everything here, longer only for
    a combination product. New fields, all with defaults, so an adapter answering only what it
    always has answered still conforms.
    """

    registration_no: str
    brand: str
    generic: str
    strength: str
    form: str
    drug_class: str
    high_risk: bool
    product_kind: ProductKind = ProductKind.PRESCRIPTION
    product_name: str = ""
    licence_status: str = "registered"
    active_ingredients: tuple[str, ...] = ()
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.product_name:
            object.__setattr__(self, "product_name", self.brand)
        if not self.active_ingredients:
            object.__setattr__(self, "active_ingredients", (self.generic,))


@dataclass(frozen=True, slots=True)
class Interaction:
    """Two generics the licensed data flags together, how much it matters, and which text.

    `source` is the reference a pharmacist would check the pair against — a citation, not
    prose about the interaction itself. `review_state` is `REVIEWED` by default, so every
    interaction built the way the tests always have built one still conforms; a pair a
    pharmacist has not yet checked carries `AWAITING_REVIEW` and is queued for one
    (`app.language.review`) the first time it is actually flagged for a person.
    """

    pair: tuple[str, str]
    severity: Severity
    text_id: str
    source: str = ""
    review_state: ReviewState = ReviewState.REVIEWED


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
        """The products that match, best first, each carrying its own confidence. Empty when
        nothing does; a caller that needs one definite product still checks the confidence
        against `CONFIDENCE_THRESHOLD` before trusting it (`app.medicines.service`)."""
        ...

    def interactions(self, generics: Sequence[str]) -> Sequence[Interaction]:
        """Every flagged pair among these generics, worst first."""
        ...

    def monograph(self, generic: str) -> Monograph:
        """The rules for this generic, or `UnknownDrug`."""
        ...
