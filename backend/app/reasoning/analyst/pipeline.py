"""The one gate every candidate insight passes through, from either adapter
(`app.reasoning.analyst.rule.RuleAnalyst`, `app.reasoning.analyst.claude_adapter.
ClaudeAnalyst`) before it is shown: plain words, the conclusion-or-advice blocklist, and a
cite (`.claude/rules`, the CLAUDE.md boundary — never a diagnosis, never "stop", "start" or
"change").

A candidate that cites nothing is dropped outright — an insight with no evidence is not one
`app.reasoning.analyst` may show, whichever adapter built it. A candidate whose words fail
`docs/plain-words.md` or carry the blocklist is not simply dropped when it is about a medicine
or a supplement: it would have told him something about his treatment, so it is rerouted as a
real question for the doctor (`ask_the_doctor`, #236) and its own words are never printed —
`reroute` is the caller's own door to that, because only a caller holding a session and a
State may actually file one; the pure check here never touches the database.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.delivery.timeline_strings import verified
from app.reasoning.analyst.port import AskWho, Confidence, Evidence, Insight, InsightKind

_CONCLUSION_WORDS: dict[str, tuple[str, ...]] = {
    "en": ("looks", "seems", "should", "must", "high", "low", "normal", "fine", "worse",
           "better", "risk", "danger", "safe", "diagnos"),
    "ms": ("nampak", "kelihatan", "patut", "sepatutnya", "mesti", "tinggi", "rendah",
           "normal", "elok", "risiko", "bahaya", "selamat", "diagnos"),
    "zh": ("看起来", "似乎", "应该", "必须", "高", "低", "正常", "没事", "更差", "更好",
           "风险", "危险", "安全", "诊断"),
}
"""The conclusion-or-advice words `app.llm.narrate` never lets a rephrase carry, held to the
same list here so the two blocklists cannot silently drift apart."""

_TREATMENT_WORDS: dict[str, tuple[str, ...]] = {
    "en": ("stop", "start", "change", "increase", "decrease", "double", "halve", "switch"),
    "ms": ("berhenti", "mula", "tukar", "naikkan", "kurangkan", "gandakan"),
    "zh": ("停", "开始", "改", "加量", "减量", "换药", "停药"),
}
"""The words the CLAUDE.md boundary never lets any surface say to a medicine: start it, stop
it, change it. A candidate carrying one of these is treatment-changing, never printed."""


def _carries_any(text: str, words: tuple[str, ...], language: str) -> bool:
    if language == "zh":
        return any(word in text for word in words)
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words)


def blocked(text: str, language: str) -> bool:
    """Whether `text` trips the conclusion-or-advice blocklist."""
    return _carries_any(text, _CONCLUSION_WORDS.get(language, ()), language) or _carries_any(
        text, _TREATMENT_WORDS.get(language, ()), language
    )


def treatment_changing(text: str, language: str) -> bool:
    """Whether `text` names a treatment change on its own — the narrower check `finalize`
    uses to decide reroute (a medicine candidate) from drop (any other kind)."""
    return _carries_any(text, _TREATMENT_WORDS.get(language, ()), language)


@dataclass(frozen=True, slots=True)
class Candidate:
    """A would-be insight, before the gate: the same fields as `Insight`, not yet checked."""

    insight_id: str
    kind: InsightKind
    text: str
    ask_who: AskWho
    evidence: tuple[Evidence, ...]
    why_plain: str
    confidence: Confidence


Reroute = Callable[[Candidate], Awaitable["Insight | None"]]
"""What `finalize` calls on a blocked medicine or supplement candidate: files a real
question for the doctor and returns the `Insight` that names it, or `None` when filing itself
could not be done (the caller's own refusal path, never this module's)."""


async def drop_reroute(candidate: Candidate) -> Insight | None:
    """The default reroute: nothing wired to file a real doctor question drops the
    candidate instead of ever printing its blocked words."""
    return None


async def finalize(candidate: Candidate, *, language: str, reroute: Reroute = drop_reroute) -> Insight | None:
    """One candidate, checked, in order:

    1. No evidence, no insight — an insight that cites nothing is not shown, whichever
       adapter built it.
    2. Plain words and the blocklist — the blocklist on the "why" line too. A medicine or
       supplement candidate that fails either is
       rerouted as a question for the doctor and its own words are never printed; any other
       kind that fails is dropped outright — there is no doctor question for a cost line or a
       screening that happened to use a blocked word.
    3. Otherwise, the candidate becomes the insight, unchanged.
    """
    if not candidate.evidence:
        return None
    # The "why" is printed beside the line, and on the Claude path it is the model's own words
    # as much as `text` is — so it meets the same blocklist. (Independent review of #303: a
    # clean text with the why "Ask the doctor to double the dose today." was printed, because
    # only `text` was ever checked.) A blocked why fails the candidate exactly as a blocked
    # text does: a medicine is rerouted to a real doctor question, anything else is dropped.
    why_blocked = bool(candidate.why_plain.strip()) and blocked(candidate.why_plain, language)
    if not verified(candidate.text, language) or blocked(candidate.text, language) or why_blocked:
        if candidate.kind in (InsightKind.MEDICINE, InsightKind.SUPPLEMENT):
            return await reroute(candidate)
        return None
    return Insight(
        insight_id=candidate.insight_id,
        kind=candidate.kind,
        text=candidate.text,
        ask_who=candidate.ask_who,
        evidence=candidate.evidence,
        why_plain=candidate.why_plain,
        confidence=candidate.confidence,
    )


__all__ = [
    "Candidate",
    "Reroute",
    "blocked",
    "drop_reroute",
    "finalize",
    "treatment_changing",
]
