"""The brand-to-generic resolution accuracy harness (E00-06).

    cd backend && python3 -m tests.drug_resolution_accuracy

The acceptance line is "brand to generic resolution for a sample of 200 MY/SG products above
95%". The sample is the registry's own product list (`tests/fixtures/drugs/registry.json`,
grown to at least 200 real MY/SG community-pharmacy and chronic-disease products across
prescription medicines, supplements and TCM) — every product IS a labelled example: its own
brand and strength, with its own generic as the answer key nobody had to write twice. For each
product, `identify()` is asked with only the brand and the strength a pack actually shows (no
registration number, no generic — the hard case, the one a person typing what is on the box
gives), and the answer is scored right only when every match it returns agrees with the
product's own generic and at least one does.

Read accuracy is resolved-right over the whole sample; a miss is printed with what was asked,
what came back, and what should have. `test_drug_resolution_accuracy.py` holds the fixture to
above 95% and fails loud, with the misses, if it ever is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.drugs.fixture import FIXTURE_PATH, FixtureRegistry
from app.drugs.registry import DrugRegistry, LabelFields


@dataclass(frozen=True, slots=True)
class Miss:
    brand: str
    strength: str
    expected_generic: str
    got: tuple[str, ...]


@dataclass(slots=True)
class Report:
    sampled: int = 0
    right: int = 0
    misses: list[Miss] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.right / self.sampled if self.sampled else 1.0

    def line(self) -> str:
        return (
            f"harness: {self.sampled} MY/SG products, brand+strength -> generic — "
            f"{self.right} resolved right ({self.accuracy:.1%}), {len(self.misses)} missed"
        )

    def render(self) -> str:
        lines = [self.line()]
        for miss in self.misses:
            got = ", ".join(miss.got) or "nothing"
            lines.append(
                f"  MISS  {miss.brand!r} {miss.strength} -> expected {miss.expected_generic!r}, "
                f"got {got}"
            )
        return "\n".join(lines)


def products(path: Path = FIXTURE_PATH) -> list[dict[str, object]]:
    """Every product the fixture holds, as the JSON file has it — the sample and its own
    answer key in one, so growing the registry grows the sample with it."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["products"])


def measure(registry: DrugRegistry, sample: list[dict[str, object]] | None = None) -> Report:
    """Resolve every product's own brand and strength back to its own generic."""
    report = Report()
    for product in sample if sample is not None else products():
        brand = str(product["brand"])
        strength = str(product["strength"])
        expected = str(product["generic"])
        report.sampled += 1
        found = registry.identify(LabelFields(brand=brand, strength=strength))
        generics = tuple(sorted({m.generic for m in found}))
        if generics == (expected,):
            report.right += 1
        else:
            report.misses.append(Miss(brand, strength, expected, generics))
    return report


def main() -> int:
    report = measure(FixtureRegistry.load())
    print(report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
