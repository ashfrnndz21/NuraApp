"""The fixture registry: the port, answered from a JSON file.

The file is `tests/fixtures/drugs/registry.json`: at least 200 products common on a Malaysian
or Singaporean community pharmacy shelf and chronic-disease list, with NPRA- and HSA-shaped
registration numbers — prescription medicines across cardiovascular, diabetes, lipid,
analgesic, gastro and respiratory care, plus the supplements and TCM remedies patients
actually take beside them; interaction pairs among all three kinds; and a monograph of rule
ids per generic. It stands in for a licensed database in the tests and on a dev run, and
nowhere else: a deployment names its registry in its settings, and a licensed feed is a second
adapter behind the same port (`tests/test_drug_registry_conformance.py` is what it must pass).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.drugs.registry import (
    DrugMatch,
    Interaction,
    LabelFields,
    Monograph,
    ProductKind,
    ReviewState,
    Severity,
    UnknownDrug,
)
from app.fixtures import fixture
from app.safety.high_risk import is_high_risk

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "drugs" / "registry.json"
)
"""Where the fixture lives, relative to the backend directory the app is run from."""


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().replace("mg", " mg").split())


def _same_strength(a: str | None, b: str) -> bool:
    return _norm(a) == _norm(b)


@fixture
class FixtureRegistry:
    """The fixture, loaded once. Every answer is read from the file, none is computed from
    the name of the drug."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._products: list[DrugMatch] = [
            DrugMatch(
                registration_no=p["registration_no"],
                brand=p["brand"],
                generic=p["generic"],
                strength=p["strength"],
                form=p["form"],
                drug_class=p["drug_class"],
                high_risk=is_high_risk(p["drug_class"]),
                product_kind=ProductKind(p.get("product_kind", ProductKind.PRESCRIPTION.value)),
                product_name=p.get("product_name", ""),
                licence_status=p.get("licence_status", "registered"),
                active_ingredients=tuple(p.get("active_ingredients", ())),
            )
            for p in data["products"]
        ]
        self._interactions: list[Interaction] = [
            Interaction(
                pair=(i["pair"][0], i["pair"][1]),
                severity=Severity(i["severity"]),
                text_id=i["text_id"],
                source=i.get("source", ""),
                review_state=ReviewState(i.get("review_state", ReviewState.REVIEWED.value)),
            )
            for i in data.get("interactions", [])
        ]
        duplicate = data.get("duplicate_therapy")
        self._duplicate: Interaction | None = (
            None
            if duplicate is None
            else Interaction(("", ""), Severity(duplicate["severity"]), duplicate["text_id"])
        )
        self._monographs: dict[str, Monograph] = {
            generic: Monograph(
                generic=generic,
                plain_name_id=m["plain_name_id"],
                purpose_id=m["purpose_id"],
                food_rule_id=m["food_rule_id"],
                missed_dose_rule_id=m["missed_dose_rule_id"],
                watch_out_ids=tuple(m.get("watch_out_ids", ())),
                avoid_ids=tuple(m.get("avoid_ids", ())),
            )
            for generic, m in data.get("monographs", {}).items()
        }

    @classmethod
    def load(cls, path: Path = FIXTURE_PATH) -> FixtureRegistry:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def generics(self) -> frozenset[str]:
        return frozenset(p.generic for p in self._products)

    def identify(self, label: LabelFields) -> Sequence[DrugMatch]:
        """Registration number first, then brand and strength, then the generic name.

        A registration number that is on the register answers alone. Without one, the brand
        narrows to a product family and the strength picks the product; a generic name does
        the same. Nothing is guessed from a partial name: a brand the register does not hold
        matches nothing, and the caller asks the person.
        """
        if label.registration_no:
            wanted = label.registration_no.strip().upper()
            exact = [p for p in self._products if p.registration_no == wanted]
            if exact:
                return exact
        candidates = list(self._products)
        if label.brand:
            brand = _norm(label.brand)
            candidates = [p for p in candidates if _norm(p.brand) == brand]
        if label.generic:
            generic = _norm(label.generic)
            candidates = [p for p in candidates if _norm(p.generic) == generic]
        if not label.brand and not label.generic:
            return []
        if label.strength:
            by_strength = [p for p in candidates if _same_strength(label.strength, p.strength)]
            if by_strength:
                candidates = by_strength
        if label.form:
            by_form = [p for p in candidates if _norm(p.form) == _norm(label.form)]
            if by_form:
                candidates = by_form
        return candidates

    def interactions(self, generics: Sequence[str]) -> Sequence[Interaction]:
        """The flagged pairs among these generics, worst first, and the same kind twice."""
        present = {g.lower() for g in generics}
        found = [i for i in self._interactions if i.pair[0] in present and i.pair[1] in present]
        if self._duplicate is not None:
            by_class: dict[str, set[str]] = {}
            for product in self._products:
                if product.generic in present:
                    by_class.setdefault(product.drug_class, set()).add(product.generic)
            for members in by_class.values():
                if len(members) > 1:
                    ordered = sorted(members)
                    for first in range(len(ordered)):
                        for second in range(first + 1, len(ordered)):
                            found.append(
                                Interaction(
                                    (ordered[first], ordered[second]),
                                    self._duplicate.severity,
                                    self._duplicate.text_id,
                                )
                            )
        order = {Severity.MAJOR: 0, Severity.MODERATE: 1, Severity.MINOR: 2, Severity.DUPLICATE: 3}
        return sorted(found, key=lambda i: (order[i.severity], i.pair))

    def monograph(self, generic: str) -> Monograph:
        found = self._monographs.get(generic.lower())
        if found is None:
            raise UnknownDrug(f"the register has no monograph for {generic}")
        return found
