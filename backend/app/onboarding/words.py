"""His words, filled and checked: every line onboarding serves passes through here.

The templates are `app.onboarding.strings`; this fills their slots and puts each filled line
through `app.safety.plain_words.verify` in its language and its kind before it is served.
A line that fails is not served (`None`) and the caller leaves it out: a read-back line built
from something on a paper that cannot be said plainly is better unsaid than said badly — the
paper and the fact are still there, and the caregiver's view shows them. The fixed lines
cannot fail at run time without failing `make plain-words` and the tests first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.delivery.feed.compose import MONTHS, WEEKDAYS
from app.onboarding.strings import (
    CHECK_AGAIN,
    KEPT_BESIDE,
    PROMPT_ACTION,
    PROMPT_HEADLINE,
    PROMPT_UNLOCK,
    QUESTION,
    QUESTIONS_MORE,
    READ_BACK,
    SCRIPT_HEADLINE,
    SCRIPT_LINES,
    SUMMARY,
    language_for,
)
from app.safety.boundary import YOUR_DOCTOR
from app.safety.plain_words import Kind, verify

log = logging.getLogger("nura.onboarding")


def checked(line: str, language: str, kind: Kind = "line") -> str | None:
    """The line, if it passes docs/plain-words.md in its language and kind; otherwise None,
    and the rules it broke go to the log by number (never the line: it may carry his data)."""
    failures = [found for found in verify(line, language, kind) if found.severity == "fail"]
    if failures:
        log.info(
            "onboarding line not served: language=%s kind=%s rules=%s",
            language,
            kind,
            sorted({found.rule for found in failures}),
        )
        return None
    return line


def plain_date(day: date, language: str) -> str:
    """ "Thursday 7 September 2023": the day and the date, with the year, since a paper's date
    is often not this year (rule 5). The feed's day and month names, so a date reads the same
    on every surface (rule 13)."""
    code = language_for(language)
    weekday = WEEKDAYS[code][day.weekday()]
    if code == "zh":
        return f"{day.year}年{day.month}月{day.day}日{weekday}"
    return f"{weekday} {day.day} {MONTHS[code][day.month - 1]} {day.year}"


def doctor_or_yours(doctor: str | None, language: str) -> str:
    """The doctor's name every time, and "your doctor" only until the record has one."""
    return doctor or YOUR_DOCTOR[language_for(language)]


@dataclass(frozen=True, slots=True)
class Script:
    """One step's words: a headline and a few lines."""

    headline: str
    lines: tuple[str, ...]


def script(step: str, language: str) -> Script:
    code = language_for(language)
    headline = checked(SCRIPT_HEADLINE[code][step], code, "headline") or ""
    lines = tuple(line for line in (checked(one, code) for one in SCRIPT_LINES[code][step]) if line)
    return Script(headline=headline, lines=lines)


def read_back(key: str, language: str, **slots: str) -> str | None:
    code = language_for(language)
    return checked(READ_BACK[code][key].format(**slots), code)


def question(gap: str, language: str, doctor: str | None) -> str | None:
    code = language_for(language)
    return checked(QUESTION[code][gap].format(doctor=doctor_or_yours(doctor, code)), code)


def questions_more(count: int, language: str) -> str | None:
    code = language_for(language)
    return checked(QUESTIONS_MORE[code].format(count=count), code)


def after_a_no(who: str | None, language: str) -> str | None:
    """What happens after a "no": `who` looks at the paper again, or — when he is setting his
    own profile up — his answer is kept beside the paper."""
    code = language_for(language)
    if who is None:
        return checked(KEPT_BESIDE[code], code)
    return checked(CHECK_AGAIN[code].format(who=who), code)


@dataclass(frozen=True, slots=True)
class PromptWords:
    """A day's prompt as he sees it: what is missing, what it lets Nura do, what to do today."""

    headline: str
    line: str
    action: str


def prompt(gap: str, language: str, doctor: str | None) -> PromptWords | None:
    code = language_for(language)
    who = doctor_or_yours(doctor, code)
    headline = checked(PROMPT_HEADLINE[code][gap].format(doctor=who), code, "headline")
    line = checked(PROMPT_UNLOCK[code][gap].format(doctor=who), code)
    action = checked(PROMPT_ACTION[code][gap].format(doctor=who), code, "action")
    if headline is None or line is None or action is None:
        return None
    return PromptWords(headline=headline, line=line, action=action)


def summary(key: str, language: str, count: int | None = None) -> str | None:
    code = language_for(language)
    template = SUMMARY[code][key]
    return checked(template.format(count=count) if count is not None else template, code)
