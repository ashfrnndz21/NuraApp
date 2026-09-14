"""The accuracy harness for the labelled test set (docs/build-plan.md §8, risk 1).

    cd backend && python3 -m tests.paper_accuracy

Every paper in `tests/fixtures/paper/` that has a labelled answer beside it
(`<label>.expected.json`, what the paper actually says) is run through the pipeline — its
bytes (the redacted file when there is one, the placeholder otherwise), the extractor, and
the checks every field passes before it reaches a card — and every field on the label is
scored against what came back:

    read      the value and unit read are what the paper says
    caught    read wrong, or unreadable, but put in front of a person: dotted below the
              confidence threshold, or asked for as a field Nura could not read
    wrong     read wrong and shown clear: a silent misread, the one that matters
    dropped   on the paper, and not read at all
    invented  read, and not on the paper

Read accuracy is `read` over the labelled fields. Safe accuracy is `read` and `caught` over
the labelled fields plus anything invented: the share of fields that are either right or in
front of a person. The fixture extractor is held to 100% safe accuracy on its own fixtures
(`tests/test_paper_accuracy.py`); its read accuracy is below 100% on purpose — two fields
are misread so that a card has something to correct — and read accuracy is the number to
write down each week once the real extractor answers instead.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.ingestion.extract import ExtractedField, Extractor, FixtureExtractor, Hints
from app.ingestion.models import CONFIDENCE_THRESHOLD
from app.regions import Region
from tests.paper import PAPER, placeholder_of

REAL_FILES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".heic": "image/heic",
    ".webp": "image/webp",
}
"""A redacted original the owner added, by suffix, and the content type it is shown as."""


class Outcome(StrEnum):
    READ = "read"
    CAUGHT = "caught"
    WRONG = "wrong"
    DROPPED = "dropped"
    INVENTED = "invented"


@dataclass(frozen=True, slots=True)
class Scored:
    label: str
    subject: str
    attribute: str
    outcome: Outcome
    truth: Any
    read: Any
    confidence: float | None


@dataclass(slots=True)
class Report:
    papers: int = 0
    kinds_right: int = 0
    scored: list[Scored] = field(default_factory=list)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for one in self.scored if one.outcome is outcome)

    @property
    def labelled(self) -> int:
        return sum(1 for one in self.scored if one.outcome is not Outcome.INVENTED)

    @property
    def read_accuracy(self) -> float:
        return self.count(Outcome.READ) / self.labelled if self.labelled else 1.0

    @property
    def safe_accuracy(self) -> float:
        safe = self.count(Outcome.READ) + self.count(Outcome.CAUGHT)
        return safe / len(self.scored) if self.scored else 1.0

    def by_field(self) -> dict[str, dict[Outcome, int]]:
        found: dict[str, dict[Outcome, int]] = defaultdict(lambda: defaultdict(int))
        for one in self.scored:
            found[f"{one.subject}.{one.attribute}"][one.outcome] += 1
        return found

    def line(self) -> str:
        return (
            f"harness: {self.papers} papers ({self.kinds_right} read as the right kind), "
            f"{self.labelled} labelled fields — {self.count(Outcome.READ)} read right "
            f"({self.read_accuracy:.1%}), {self.count(Outcome.CAUGHT)} caught and put to a "
            f"person, {self.count(Outcome.WRONG)} silently wrong, "
            f"{self.count(Outcome.DROPPED)} dropped, {self.count(Outcome.INVENTED)} invented: "
            f"{self.safe_accuracy:.1%} read right or put in front of a person"
        )

    def render(self) -> str:
        lines = ["per-field accuracy (read right / on the label):"]
        for name, outcomes in sorted(self.by_field().items()):
            total = sum(n for o, n in outcomes.items() if o is not Outcome.INVENTED)
            others = ", ".join(
                f"{n} {o.value}" for o, n in sorted(outcomes.items()) if o is not Outcome.READ
            )
            lines.append(
                f"  {name:<34} {outcomes.get(Outcome.READ, 0)}/{total}"
                + (f"  ({others})" if others else "")
            )
        lines.append(self.line())
        return "\n".join(lines)


def bytes_of(label: str, directory: Path = PAPER) -> tuple[bytes, str]:
    """The redacted original when the owner added one, else the placeholder for the paper."""
    for suffix, content_type in REAL_FILES.items():
        real = directory / f"{label}{suffix}"
        if real.is_file():
            return real.read_bytes(), content_type
    data = placeholder_of(label)
    return data, "application/pdf" if data.startswith(b"%PDF-") else "image/png"


def _score(label: str, truth: Sequence[dict[str, Any]], read: Sequence[ExtractedField]) -> list[Scored]:
    waiting = list(read)
    scored: list[Scored] = []
    for want in truth:
        key = (want["subject"], want["attribute"])
        got = next((one for one in waiting if (one.subject, one.attribute) == key), None)
        if got is None:
            outcome = Outcome.DROPPED
        else:
            waiting.remove(got)
            if not got.unreadable and got.value == want["value"] and got.unit == want.get("unit"):
                outcome = Outcome.READ
            elif got.unreadable or got.confidence < CONFIDENCE_THRESHOLD:
                outcome = Outcome.CAUGHT
            else:
                outcome = Outcome.WRONG
        scored.append(
            Scored(
                label=label,
                subject=key[0],
                attribute=key[1],
                outcome=outcome,
                truth=want["value"],
                read=None if got is None else got.value,
                confidence=None if got is None else got.confidence,
            )
        )
    for extra in waiting:
        scored.append(
            Scored(label, extra.subject, extra.attribute, Outcome.INVENTED, None, extra.value, extra.confidence)
        )
    return scored


async def measure(
    extractor: Extractor,
    directory: Path = PAPER,
    *,
    region: Region = Region.SG,
    language: str = "en",
) -> Report:
    """Run every labelled paper through the extractor and the field checks; score each field."""
    report = Report()
    for path in sorted(directory.glob("*.expected.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        label = str(truth.get("placeholder") or path.name.removesuffix(".expected.json"))
        data, content_type = bytes_of(label, directory)
        extraction = await extractor.extract(data, content_type, Hints(language, region))
        fields = [one.checked() for one in extraction.fields]
        report.papers += 1
        report.kinds_right += int(extraction.document_kind.value == truth["document_kind"])
        report.scored.extend(_score(label, truth["fields"], fields))
    return report


def main() -> int:
    report = asyncio.run(measure(FixtureExtractor(PAPER)))
    print(report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
