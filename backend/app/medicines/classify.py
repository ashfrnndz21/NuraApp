"""Is a name a medicine, a family of medicines, or neither — decided by the licensed
register alone, never by pattern-matching the text on a box.

The owner's own case (#302): "can I add for eg, when I screenshot meds like this [a box
labelled STATIN]... you are essentially registering a med artefact record for me". A box
that prints only the family name is not a product, and nothing here is allowed to guess
which one he means. `classify_name` is the one function a caller runs before a label's own
`generic` field is trusted to identify a product: it asks the register the same two
questions in order — "do you know this as a product?", then "do you know this as a class
you file products under?" — and answers with whichever the register itself says is true.
Nothing here reads the free text for a class word list of its own; the register is the only
source of truth, exactly as it already is for `app.medicines.service._one_product`.
"""

from __future__ import annotations

from enum import StrEnum

from app.drugs.registry import DrugRegistry, LabelFields


class NameKind(StrEnum):
    """What the register makes of a name alone, ignoring strength and form."""

    MEDICINE = "medicine"
    """The register can identify this as a specific product, by generic or by brand."""
    CLASS = "class"
    """Not a product itself, but a class the register files one or more products under —
    the "STATIN" case: ask which member the label meant, offered from the register."""
    UNKNOWN = "unknown"
    """Neither: the register has never heard of this name at all."""


def classify_name(registry: DrugRegistry, name: str | None) -> NameKind:
    """`MEDICINE` when `registry.identify` finds this name as a generic or a brand;
    `CLASS` when it is not a product but `registry.members_of_class` finds products filed
    under it; `UNKNOWN` when the register answers no to both. An empty or missing name is
    `UNKNOWN` without asking the register anything."""
    trimmed = (name or "").strip()
    if not trimmed:
        return NameKind.UNKNOWN
    if registry.identify(LabelFields(generic=trimmed)) or registry.identify(LabelFields(brand=trimmed)):
        return NameKind.MEDICINE
    if registry.members_of_class(trimmed):
        return NameKind.CLASS
    return NameKind.UNKNOWN


__all__ = ["NameKind", "classify_name"]
