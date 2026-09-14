"""The boundary copy: the line every inferring surface carries (E16-01).

    The boundary: Nura organises, prepares and surfaces patterns to discuss; it does not
    diagnose or treat. (CLAUDE.md; docs/00-MASTER-BUILD-SPEC.md §1 and §10)

`INFERRING_SURFACES` is the register of every surface that works something out from the
record rather than showing it back — State's posture, the visit brief, the questions, the
summary, an interaction question, a learning card, a feeling inference, the not-feeling-well
card. `boundary_line(surface, language)` is the words each of them carries, in English,
Malay and Chinese: what Nura did on that surface, then the two lines that never change —
"This is not a doctor's advice." and "Ask Dr Tan." — the glossary's own phrase in
docs/plain-words.md. The words are the same on every surface on purpose (rule 13: the same
words every time), and every one of them is tagged `@patient` so `make plain-words` holds
them to the standard.

A surface that renders without its line is a defect (docs/trust/samd-boundary-review.md).
The surfaces that exist on main carry it today (State's `GET /state`); the ones still on
their own branches (E05 visits, E21 feed) call `boundary_line` when they land — the line
lives here so that no builder writes their own.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"


class Surface(StrEnum):
    """Every surface that infers. Anything added here needs its words in every language
    below and a row in docs/trust/samd-boundary-review.md; the tests hold both."""

    STATE_POSTURE = "state_posture"
    """The wash and the order of the day: State's posture (E00-04)."""
    BRIEF = "brief"
    """The pre-visit brief (E05)."""
    QUESTIONS = "questions"
    """The questions to ask the doctor, generated from the record (E05-02)."""
    SUMMARY = "summary"
    """The post-visit summary and memo (E05)."""
    INTERACTION_FLAG = "interaction_flag"
    """An interaction between two medicines, rendered as a question (E04)."""
    LEARNING_CARD = "learning_card"
    """A learning card in the feed: an explanation chosen for him (E21)."""
    FEELING_INFERENCE = "feeling_inference"
    """A pattern noticed from how he said he feels (E17-02)."""
    NOT_FEELING_WELL = "not_feeling_well"
    """The not-feeling-well card: who to tell, today or not a worry."""


INFERRING_SURFACES: tuple[Surface, ...] = tuple(Surface)
"""The register. Every entry has words in every language; `tests/test_boundary.py` checks."""


def language_of(asked: str | None) -> str:
    """One of the languages the line is written in, or English when it is not."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}
"""Who to ask when the record has not named the doctor yet."""

# @patient
WHAT_NURA_DID: Mapping[str, Mapping[Surface, str]] = {
    "en": {
        Surface.STATE_POSTURE: "Nura sorts and prepares.",
        Surface.BRIEF: "Nura prepared this from your papers.",
        Surface.QUESTIONS: "Nura wrote these questions for you to ask {doctor}.",
        Surface.SUMMARY: "Nura wrote down what {doctor} said.",
        Surface.INTERACTION_FLAG: "Nura is only asking a question about your medicines.",
        Surface.LEARNING_CARD: "This explains one thing in simple words.",
        Surface.FEELING_INFERENCE: "Nura only noticed a pattern to talk about.",
        Surface.NOT_FEELING_WELL: "Nura does not decide what is wrong.",
    },
    "ms": {
        Surface.STATE_POSTURE: "Nura menyusun dan menyediakan.",
        Surface.BRIEF: "Nura menyediakan ini daripada surat-surat anda.",
        Surface.QUESTIONS: "Nura menulis soalan ini untuk anda tanya {doctor}.",
        Surface.SUMMARY: "Nura menulis apa yang {doctor} katakan.",
        Surface.INTERACTION_FLAG: "Nura hanya bertanya tentang ubat anda.",
        Surface.LEARNING_CARD: "Ini menerangkan satu perkara dengan kata-kata mudah.",
        Surface.FEELING_INFERENCE: "Nura hanya melihat satu corak untuk dibincangkan.",
        Surface.NOT_FEELING_WELL: "Nura tidak memutuskan apa yang tidak kena.",
    },
    "zh": {
        Surface.STATE_POSTURE: "Nura 帮您整理和准备。",
        Surface.BRIEF: "这是 Nura 从您的病历文件准备的。",
        Surface.QUESTIONS: "这些问题是 Nura 写给您问{doctor}的。",
        Surface.SUMMARY: "Nura 写下了{doctor}说的话。",
        Surface.INTERACTION_FLAG: "Nura 只是问一个关于您的药的问题。",
        Surface.LEARNING_CARD: "这只是用简单的话解释一件事。",
        Surface.FEELING_INFERENCE: "Nura 只是发现了一个可以谈的情况。",
        Surface.NOT_FEELING_WELL: "Nura 不判断您有什么问题。",
    },
}
"""The first line: what Nura did on this surface, and no more than that."""

# @patient
NOT_ADVICE: Mapping[str, tuple[str, str]] = {
    "en": ("This is not a doctor's advice.", "Ask {doctor}."),
    "ms": ("Ini bukan nasihat doktor.", "Tanya {doctor}."),
    "zh": ("这不是医生的意见。", "问{doctor}。"),
}
"""The two lines every surface ends on, the same words every time (docs/plain-words.md,
glossary: "Not medical advice")."""


def boundary_lines(
    surface: Surface, language: str | None = None, *, doctor: str | None = None
) -> tuple[str, ...]:
    """The boundary for this surface, one line per idea, in this language, naming the doctor
    when the record has one ("Ask Dr Tan.") and "your doctor" otherwise."""
    code = language_of(language)
    who = doctor or YOUR_DOCTOR[code]
    lines = (WHAT_NURA_DID[code][surface], *NOT_ADVICE[code])
    return tuple(line.format(doctor=who) for line in lines)


def boundary_line(surface: Surface, language: str | None = None, *, doctor: str | None = None) -> str:
    """The same, as the one string a response or a card carries: the lines joined by newlines,
    which is also how the voice reads them, with a pause between."""
    return "\n".join(boundary_lines(surface, language, doctor=doctor))
