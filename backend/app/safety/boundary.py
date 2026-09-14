"""The boundary copy: the line every inferring surface carries (E16-01).

    The boundary: Nura organises, prepares and surfaces patterns to discuss; it does not
    diagnose or treat. (CLAUDE.md; docs/00-MASTER-BUILD-SPEC.md §1 and §10)

`INFERRING_SURFACES` is the register of every surface that works something out from the
record rather than showing it back — State's posture, the visit brief, the questions, the
summary, an interaction question, a learning card, a feeling inference, the not-feeling-well
card, a lab trend. `boundary_line(surface, language)` is the words each of them carries, in English,
Malay and Chinese: what Nura did on that surface, then the two lines that never change —
"This is not a doctor's advice." and "Ask Dr Tan." — the glossary's own phrase in
docs/plain-words.md. The closing words are the same on every surface on purpose (rule 13:
the same words every time), and every line here is tagged `@patient` so `make plain-words`
holds it to the standard.

The line is structure, not convention: a rendered row for an inferring surface cannot be
written without it (`app.state.service.render_from_state` takes `surface` and refuses a row
whose `boundary` is not this module's line for it — `is_boundary_line`), the way a card
cannot be written without its State. `GET /state` carries it, and so does every learning
card in the feed (`app.delivery.feed.items` names `Surface.LEARNING_CARD` for a learning
card and a notice, and the card's body and voice end on the line); the surfaces still on
their own branches (E05 visits) pass their `Surface` when they render.

The not-feeling-well card is the one surface allowed to say more than the register: where a
Fact holds the discharge letter's own instruction, the card carries those words, names the
letter ("Dr Tan wrote this in your hospital letter."), and still ends on the boundary. It
opens with a reassurance, because a man who has just said he feels unwell is not met with
three refusals in a row (docs/plain-words.md rule 9). A red flag makes the card urgent
(`urgent=True`): the reassurance, the calls, and one closing line, "Nura does not decide what is
wrong." — after an emergency number the card never says "Ask your doctor."
"""

from __future__ import annotations

import re
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
    """A learning card in the feed: an explanation chosen for him (E21), and a safety
    notice, the same compression of a regulator's page."""
    FEELING_INFERENCE = "feeling_inference"
    """A pattern noticed from how he said he feels (E17-02)."""
    NOT_FEELING_WELL = "not_feeling_well"
    """The not-feeling-well card: the escalation surface — who knows, what the letter said."""
    TREND = "trend"
    """A lab trend: his results side by side, each against a range, and how they moved (E09-01)."""
    RECALL = "recall"
    """An answer from Ask: which parts of his record a question is about, said back with
    their citations (E03-05)."""


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
        Surface.STATE_POSTURE: "Nura put your day in order.",
        Surface.BRIEF: "Nura prepared this from your papers.",
        Surface.QUESTIONS: "Nura wrote these questions for you to ask {doctor}.",
        Surface.SUMMARY: "Nura wrote down what {doctor} said.",
        Surface.INTERACTION_FLAG: "Nura is only asking a question about your medicines.",
        Surface.LEARNING_CARD: "Nura explains one thing in simple words.",
        Surface.FEELING_INFERENCE: "Nura noticed this in how you said you feel.",
        Surface.NOT_FEELING_WELL: "Nura wrote down how you feel.",
        Surface.TREND: "Nura put your blood tests side by side.",
        Surface.RECALL: "Nura looked in your papers.",
    },
    "ms": {
        Surface.STATE_POSTURE: "Nura menyusun hari anda.",
        Surface.BRIEF: "Nura menyediakan ini daripada surat-surat anda.",
        Surface.QUESTIONS: "Nura menulis soalan ini untuk anda tanya {doctor}.",
        Surface.SUMMARY: "Nura menulis apa yang {doctor} katakan.",
        Surface.INTERACTION_FLAG: "Nura hanya bertanya tentang ubat anda.",
        Surface.LEARNING_CARD: "Nura menerangkan satu perkara dengan kata-kata mudah.",
        Surface.FEELING_INFERENCE: "Nura perasan ini daripada apa yang anda rasa.",
        Surface.NOT_FEELING_WELL: "Nura menulis apa yang anda rasa.",
        Surface.TREND: "Nura menyusun ujian darah anda mengikut tarikh.",
        Surface.RECALL: "Nura melihat dalam surat-surat anda.",
    },
    "zh": {
        Surface.STATE_POSTURE: "Nura 帮您把今天的事整理好了。",
        Surface.BRIEF: "这是 Nura 从您的病历文件准备的。",
        Surface.QUESTIONS: "Nura 写了这些问题，让您问{doctor}。",
        Surface.SUMMARY: "Nura 写下了{doctor}说的话。",
        Surface.INTERACTION_FLAG: "Nura 只是问一个关于您的药的问题。",
        Surface.LEARNING_CARD: "Nura 用简单的话解释一件事。",
        Surface.FEELING_INFERENCE: "Nura 从您说的感觉里注意到这一点。",
        Surface.NOT_FEELING_WELL: "Nura 只是记下您现在的感觉。",
        Surface.TREND: "Nura 把您的验血结果按日期排好了。",
        Surface.RECALL: "Nura 查看了您的病历文件。",
    },
}
"""The first line: what Nura did on this surface, and no more than that. The Malay and
Chinese lines are a first translation awaiting a native speaker's pass."""

# @patient
NOT_ADVICE: Mapping[str, tuple[str, str]] = {
    "en": ("This is not a doctor's advice.", "Ask {doctor}."),
    "ms": ("Ini bukan nasihat doktor.", "Tanya {doctor}."),
    "zh": ("这不是医生的意见。", "问{doctor}。"),
}
"""The two lines every surface ends on, the same words every time (docs/plain-words.md,
glossary: "Not medical advice")."""

# @patient
SOMEONE_KNOWS: Mapping[str, str] = {
    "en": "{told} knows now.",
    "ms": "{told} sudah tahu.",
    "zh": "{told} 已经知道了。",
}
"""The reassurance the not-feeling-well card opens with when the roster has been told
(docs/plain-words.md, glossary: "Escalated → Ash knows.")."""

# @patient
YOU_DID_RIGHT: Mapping[str, str] = {
    "en": "You did right to say so.",
    "ms": "Bagus, anda sudah beritahu.",
    "zh": "您说出来是对的。",
}
"""The reassurance when nobody has been told yet: saying so was the right thing."""

# @patient
FROM_THE_LETTER: Mapping[str, str] = {
    "en": "{doctor} wrote this in your hospital letter.",
    "ms": "{doctor} menulis ini dalam surat hospital anda.",
    "zh": "这是{doctor}写在您的医院信里的。",
}
"""Where the letter's own words come from (docs/plain-words.md, glossary: "Red flag")."""

# @patient
URGENT_CLOSING: Mapping[str, str] = {
    "en": "Nura does not decide what is wrong.",
    "ms": "Nura tidak menentukan apa masalahnya.",
    "zh": "Nura 不判断您出了什么问题。",
}
"""The one closing line of an urgent card — a red flag on the not-feeling-well surface. After
"Call the ambulance now on 995." nothing sends him anywhere but the call: the boundary is this
one line, and "Ask your doctor." is never said after an emergency number."""


def boundary_lines(
    surface: Surface,
    language: str | None = None,
    *,
    doctor: str | None = None,
    letter: str | None = None,
    told: str | None = None,
    urgent: bool = False,
) -> tuple[str, ...]:
    """The boundary for this surface, one line per idea, in this language, naming the doctor
    when the record has one ("Ask Dr Tan.") and "your doctor" otherwise.

    For `NOT_FEELING_WELL` only: the card opens with a reassurance — `told` is who on the
    roster knows now — and, where a Fact holds the discharge letter's own instruction,
    `letter` is those words, carried before the line that names the letter. The letter's
    words are run-time text and go through `plain_words.verify` on the surface that shows
    them; they are never composed here. The closing two lines are last, whatever came
    before.

    `urgent` is for the not-feeling-well card of a red flag only: the reassurance, the
    letter's words in the letter's name if there are any, and `URGENT_CLOSING` as the one
    closing line — no "Nura wrote down how you feel.", no "Ask your doctor.". The card puts
    its calls between the reassurance and the closing.
    """
    code = language_of(language)
    who = doctor or YOUR_DOCTOR[code]
    if urgent and surface is not Surface.NOT_FEELING_WELL:
        raise ValueError("only the not-feeling-well card is ever urgent")
    lines: list[str] = []
    if surface is Surface.NOT_FEELING_WELL:
        lines.append(SOMEONE_KNOWS[code].format(told=told) if told else YOU_DID_RIGHT[code])
    if not urgent:
        lines.append(WHAT_NURA_DID[code][surface])
    if surface is Surface.NOT_FEELING_WELL and letter:
        lines.extend(letter.strip().splitlines())
        lines.append(FROM_THE_LETTER[code])
    elif letter:
        raise ValueError("only the not-feeling-well card carries the letter's own words")
    if urgent:
        lines.append(URGENT_CLOSING[code])
    else:
        lines.extend(NOT_ADVICE[code])
    return tuple(line.format(doctor=who) for line in lines)


def boundary_line(
    surface: Surface,
    language: str | None = None,
    *,
    doctor: str | None = None,
    letter: str | None = None,
    told: str | None = None,
    urgent: bool = False,
) -> str:
    """The same, as the one string a response or a card carries: the lines joined by newlines,
    which is also how the voice reads them, with a pause between."""
    return "\n".join(
        boundary_lines(surface, language, doctor=doctor, letter=letter, told=told, urgent=urgent)
    )


def _pattern(template: str) -> re.Pattern[str]:
    """A template with `{doctor}` or `{told}` as a regex matching any name in the slot."""
    parts = re.split(r"\{(?:doctor|told)\}", template)
    return re.compile("^" + r"\S.*".join(re.escape(part) for part in parts) + "$")


def _is_urgent(lines: list[str]) -> bool:
    """The urgent shape of the not-feeling-well boundary: a reassurance first, the letter's words
    in the letter's name if any, and `URGENT_CLOSING` last — nothing else."""
    for code in LANGUAGES:
        if len(lines) < 2 or lines[-1] != URGENT_CLOSING[code]:
            continue
        opens = [_pattern(SOMEONE_KNOWS[code]), _pattern(YOU_DID_RIGHT[code])]
        if not any(p.match(lines[0]) for p in opens):
            continue
        rest = lines[1:-1]
        if not rest or (len(rest) >= 2 and _pattern(FROM_THE_LETTER[code]).match(rest[-1])):
            return True
    return False


def is_boundary_line(surface: Surface, text: str | None) -> bool:
    """Whether `text` is this module's line for `surface`, in any language, with any doctor.

    What `render_from_state` asks before it writes a rendered row for an inferring surface.
    The closing two lines must be `NOT_ADVICE` and last; the register's line for the surface
    must be there; and on the not-feeling-well card, whatever else is carried (the
    reassurance, the letter's words) sits between the register's line and the closing, with
    the letter named. The not-feeling-well card of a red flag may instead be urgent: the
    reassurance, the letter if any, and `URGENT_CLOSING` alone at the end. Nothing else passes.
    """
    if not text:
        return False
    lines = text.strip().splitlines()
    if surface is Surface.NOT_FEELING_WELL and _is_urgent(lines):
        return True
    for code in LANGUAGES:
        closing = [_pattern(t) for t in NOT_ADVICE[code]]
        if len(lines) < 3 or not all(p.match(line) for p, line in zip(closing, lines[-2:], strict=True)):
            continue
        body = lines[:-2]
        did = _pattern(WHAT_NURA_DID[code][surface])
        if surface is not Surface.NOT_FEELING_WELL:
            if len(body) == 1 and did.match(body[0]):
                return True
            continue
        opens = [_pattern(SOMEONE_KNOWS[code]), _pattern(YOU_DID_RIGHT[code])]
        if len(body) < 2 or not any(p.match(body[0]) for p in opens) or not did.match(body[1]):
            continue
        rest = body[2:]
        if not rest or (len(rest) >= 2 and _pattern(FROM_THE_LETTER[code]).match(rest[-1])):
            return True
    return False
