"""The plain-words verifier: every patient string passes `docs/plain-words.md` or does not ship.

`make plain-words` runs this module over every patient string in the repository and exits 1 on
the first failure. `verify(text, language, kind)` is the same check as a function, for the
memos and cards the backend writes at run time (E05, E21): they go through it before they
reach him, exactly as the strings in the source do.

The tag contract
----------------
A patient string is a string literal in a Python file under the paths listed in the front
matter of `.claude/rules/patient-strings.md` (or in a file passed on the command line) that
sits inside a *tagged statement*. A statement is tagged in one of three ways:

1. A comment line `# @patient` on its own line: it tags the next statement — an assignment,
   an annotated assignment, a `def` (decorators included), a class, or any compound statement.
   Every string literal inside that statement is a patient string; for a `def` that is every
   literal in the body, the docstring aside.
2. A comment `# @patient` at the end of a code line: it tags the statement on that line.
3. A string statement `\"\"\"@patient ...\"\"\"` right after an assignment (the attribute-docstring
   idiom): it tags that assignment. The tag string itself is not a patient string.

Words that were shown once and are kept as the record but shown no more (an old version of a
consent text, which is append-only) carry `# plain-words: <reason>` at the end of the line the
literal starts on. They are counted as exempt, not checked. Nothing that ships is exempt.

The tag may carry a *kind*: `# @patient`, `# @patient line` — whole lines he reads or hears, the
default; `# @patient phrase` — his words for a thing that fill a slot in a line ("your papers",
"in the app"); `# @patient headline` — a heading; `# @patient action` — a card that tells him
what happens next. Anything after the kind word is free text. A mention of `@patient` inside a
longer sentence (a docstring saying "tagged `@patient`") is not a tag: the tag is the first
word of the comment or string.

Inside a tagged statement, literals in code positions are not patient text and are skipped:
dictionary keys, subscripts, comparison operands, the receiver of a method call
(`"\\n".join(...)`), arguments to string, regex and logging methods, annotations, anything in
a `raise` or an `assert`, docstrings, identifier-like tokens (`"en"`, `"out_of_date"`), and
strings with no letters outside their slots (`""`, `"\\n"`, `f"- {part}"`).

A literal's language is `zh` when it holds Chinese characters; otherwise the language code
(`en`, `ms`, `zh`, `ta`) that keys its entry in an enclosing dict, or that stands beside it as
another literal argument of the same call (`ConsentText(..., "ms", "...")`); otherwise `en`.
English-specific rules (sentence grammar, readability, red English words, number words, the
who-does-next check) are skipped for `ms` and `zh`; the glossary's chemical names, numeric
dates and times, abbreviations, units and identifiers are checked in every language.

An f-string or `{slot}` template is checked with representative fillers: a name slot becomes
"Ash", a date slot "Monday 14 September", a number slot "2" (`FILLERS`). A line that begins
with a slot is not asked to begin with a capital letter: the filled value decides that.

The web client's strings (`web/src/strings/*.ts`) are read too: `// @patient [kind]` on the line
above a property or statement tags every string literal in it, and at the end of a line tags
that line; `// plain-words: <reason>` at the end of a line exempts it; the file's name is the
language (`ms.ts` holds Malay). See `strings_in_typescript`.

The strings catalogue for the iOS app (`ios/Nura/**/*.xcstrings`) is read too: an entry whose
comment begins with `patient` or contains `@patient` (optionally followed by a kind word) is a
patient string in every language it is localised in.

What is checked, by the doc's rule number
-----------------------------------------
1  whole sentence: begins with a capital, ends with . ! ? or :, has a verb, and does not stop
   on a verb that needs an object ("A heart doctor explains." fails).
2  one idea per line: one sentence per line, no semicolons.
3  short words, short lines: over ten words is a note, over fifteen a failure; a word of four
   or more syllables he would have to ask about fails (`EVERYDAY_WORDS` are the long words he
   already uses; names are left alone).
4  his words for things: the glossary's red words fail with the plain phrase as the rewrite. A
   chemical name may stand beside its plain name ("the water pill (furosemide)"), never alone.
5  the day and the date: "14/09", "2026-09-14", "10:00", "UTC", "the 29th", a date with no
   weekday and an abbreviated month or weekday all fail.
6  what to do and when: an action card that tells him to do something names the time.
7  who does the next thing: an action card names who — a person, Nura, the doctor, or him.
10 numbers as digits, small and few: "ten" fails ("one" is allowed); more than three numbers
   on a line fail.
11 no red words: "missed", "failed", "overdue", "non-compliant".
12 nothing to decode: "dose", "recheck", "follow-up", "flag", "log"; abbreviations in capitals
   (OK and IC are his words); units he does not use (mg, mmHg, mmol/L).
13 the same words every time: the known variants of his names for things fail ("the log",
   "discharge summary", "the clinic").
No identifier ever reaches him: a UUID, a phone number, an IC number, an email, a hash.
Rules 8 and 9 (the question he would ask, the small reassurance) are the reviewer's.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tokenize
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from typing import Literal

Kind = Literal["line", "phrase", "headline", "action"]
KINDS: tuple[Kind, ...] = ("line", "phrase", "headline", "action")
LANGUAGE_CODES = ("en", "ms", "zh", "ta")
RULES_FILE = Path(".claude/rules/patient-strings.md")

# --- the finding -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing wrong with one line, with the rule it breaks and the rewrite."""

    rule: int
    problem: str
    rewrite: str
    text: str
    """The line as written in the source (the template, not the filled line)."""
    severity: Literal["fail", "note"] = "fail"
    language: str = "en"
    kind: str = "line"
    path: str | None = None
    line: int | None = None
    offset: int = 0
    """Which line of a multi-line text, counting from 0."""

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}: " if self.path else ""
        note = "note " if self.severity == "note" else ""
        return f"{where}{note}rule {self.rule} — {self.problem} → {self.rewrite}"


@dataclass(frozen=True, slots=True)
class PatientString:
    """A string found in the source, with where it is and how to read it."""

    path: Path
    line: int
    text: str
    language: str
    kind: Kind
    exempt: bool = False
    """History that is no longer shown (`# plain-words: <reason>` on its line): found, not checked."""


@dataclass(slots=True)
class Report:
    strings: int = 0
    files: int = 0
    exempt: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "fail"]

    @property
    def notes(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "note"]

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        exempt = f", {self.exempt} exempt as history" if self.exempt else ""
        return (
            f"plain-words: {self.strings} strings in {self.files} files, "
            f"{len(self.failures)} failures, {len(self.notes)} notes{exempt}"
        )


# --- the glossary and the word lists -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Term:
    words: tuple[str, ...]
    """Red words, matched whole and case-insensitively (case-sensitively when all capitals)."""
    say: str
    rule: int = 4
    alongside: tuple[str, ...] = ()
    """Plain words whose presence on the same line makes the red word acceptable: a chemical
    name may stand second to his name for it, never alone."""


GLOSSARY: tuple[Term, ...] = (
    Term(
        ("diuretic", "diuretics", "furosemide", "frusemide"),
        "the water pill",
        alongside=("water pill",),
    ),
    Term(
        ("antihypertensive", "antihypertensives", "amlodipine"),
        "your blood pressure tablet",
        alongside=("blood pressure tablet",),
    ),
    Term(
        ("statin", "statins", "atorvastatin"),
        "the cholesterol tablet",
        alongside=("cholesterol tablet",),
    ),
    Term(("metformin",), "the sugar tablet", alongside=("sugar tablet",)),
    Term(("dose", "doses", "dosage", "dosing"), 'how much you take ("half a tablet")', rule=12),
    Term(("adherence", "confirmation"), "taken"),
    Term(("reading", "readings"), "your blood pressure"),
    Term(("log", "logs"), "your blood pressure book", rule=12),
    Term(
        ("result", "results", "panel", "labs", "lab"),
        "your blood test / your kidney test / your sugar test",
    ),
    Term(("creatinine", "egfr"), "your kidney number / your kidney filter"),
    Term(
        ("potassium",),
        'a body salt ("a body salt. Doctors call it potassium.")',
        alongside=("body salt",),
    ),
    Term(("hba1c",), "your sugar test. Lower is better."),
    Term(("orthostatic",), "dizzy when you stand up"),
    Term(("oedema", "edema", "fluid retention"), "swollen legs / water in the body"),
    Term(("symptom", "symptoms"), "how you feel"),
    Term(("flag", "flags", "flagged"), '"This one we do not wait for."', rule=12),
    Term(("alert", "alerts", "triage"), '"This one we do not wait for."'),
    Term(("red flag", "red flags"), '"Dr Tan wrote this in your hospital letter."'),
    Term(("discharge summary",), "your hospital letter"),
    Term(("follow-up", "follow up", "followup"), "see Dr Tan again", rule=12),
    Term(("review",), "see Dr Tan again"),
    Term(("recheck", "re-check"), "blood test again", rule=12),
    Term(("guarantee letter", "GL", "coverage"), "your insurance letter"),
    Term(("panel hospital",), '"Gleneagles is on your insurance."'),
    Term(("referral",), "a letter to see the eye doctor"),
    Term(("fasting",), "no food after 12 midnight. Water is OK."),
    Term(("explainer", "clip"), '"In simple words." / "A short explanation."'),
    Term(("feed", "timeline"), "your Today page"),
    Term(("record",), "your papers"),
    Term(("logged", "logging", "filed"), '"I wrote it down." / "Saved."', rule=12),
    Term(
        ("escalated", "escalate", "escalation", "notified", "notify", "notification"),
        '"Ash knows." / "Ash and Mei know now."',
    ),
    Term(("medical advice",), '"This is not a doctor\'s advice. Ask Dr Tan."'),
    Term(("urgent", "urgently"), '"Today." / "Not a worry."'),
    # Rule 11: the red words.
    Term(("missed",), '"was late" ("One tablet was late.")', rule=11),
    Term(
        ("failed", "failure", "fail", "fails"), "say what happened, without the red word", rule=11
    ),
    Term(("overdue",), '"late"', rule=11),
    Term(
        (
            "non-compliant",
            "noncompliant",
            "non-compliance",
            "noncompliance",
            "compliance",
            "compliant",
        ),
        "say what was taken and what was late",
        rule=11,
    ),
)
"""The doc's glossary, one entry per row, plus the red words of rule 11. "Saved." is in the
Say column, so it is not red here even though the row lists it: a word the doc tells us to
say cannot be banned. "record" is red as the surface's name ("the record", "a record"); his
own record ("your record", "Pa's record") is allowed, see `_POSSESSED_RECORD`."""

_POSSESSED_RECORD = re.compile(
    r"\b(?:your|his|her|my|their|our|\w+['’]s)\s+record\b", re.IGNORECASE
)

# Rule 13: the same words every time. Variants of his names for things, and what they are.
SAME_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bblood pressure (?:log|record|readings?|diary|chart)\b", re.IGNORECASE),
        "your blood pressure book",
    ),
    (re.compile(r"\bthe (?:log|readings)\b", re.IGNORECASE), "your blood pressure book"),
    (re.compile(r"\bthe record\b", re.IGNORECASE), "your papers"),
    (
        re.compile(r"\bdischarge (?:summary|letter|papers?|note)\b", re.IGNORECASE),
        "your hospital letter",
    ),
    (re.compile(r"\b(?:guarantee letter|GL)\b"), "your insurance letter"),
    (
        re.compile(r"\b(?:home ?page|dashboard|news ?feed|the feed|the timeline)\b", re.IGNORECASE),
        "your Today page",
    ),
    (re.compile(r"\bthe clinic\b", re.IGNORECASE), 'the doctor\'s name: "Dr Tan"'),
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_DAY_ABBREVIATIONS = re.compile(r"\b(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\b\.?")
_MONTH_ABBREVIATIONS = re.compile(r"\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b\.?")
_MONTH_ABBREVIATIONS_MS = re.compile(r"\b(?:Jan|Feb|Apr|Jul|Ogo|Sep|Sept|Okt|Nov|Dis)\b\.?")
"""The shortenings of the Malay months; "Jun" and "Mac" are whole Malay month names."""
_NUMERIC_DATE = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}-\d{1,2}-\d{2,4}\b"
)
_CLOCK_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b(?:\s*(?:am|pm|AM|PM))?")
_TIME_ZONE = re.compile(r"\b(?:UTC|GMT)\b(?:[+-]\d{1,2})?")
_ORDINAL_DAY = re.compile(r"\b(?:on\s+)?the\s+\d{1,2}(?:st|nd|rd|th)\b", re.IGNORECASE)
WEEKDAYS_MS = ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad")
MONTHS_MS = (
    "Januari",
    "Februari",
    "Mac",
    "April",
    "Mei",
    "Jun",
    "Julai",
    "Ogos",
    "September",
    "Oktober",
    "November",
    "Disember",
)
"""Rule 5 in Malay: "Isnin 29 Jun" says the day and the date, and "Jun" and "Mac" are whole
month names, not shortenings. The tables are keyed by the line's language: an English line
with a Malay weekday still fails, and a Malay line is held to all twelve Malay months."""

_WEEKDAYS_BY_LANGUAGE: dict[str, tuple[str, ...]] = {"en": WEEKDAYS, "ms": WEEKDAYS_MS}
_MONTHS_BY_LANGUAGE: dict[str, tuple[str, ...]] = {"en": MONTHS, "ms": MONTHS_MS}


def _month_date_pattern(months: tuple[str, ...]) -> re.Pattern[str]:
    joined = "|".join(months)
    return re.compile(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + joined + r")\b"
        r"|\b(" + joined + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b"
    )


_MONTH_DATE_BY_LANGUAGE: dict[str, re.Pattern[str]] = {
    code: _month_date_pattern(months) for code, months in _MONTHS_BY_LANGUAGE.items()
}
_WEEKDAY_BY_LANGUAGE: dict[str, re.Pattern[str]] = {
    code: re.compile(r"\b(?:" + "|".join(days) + r")\b")
    for code, days in _WEEKDAYS_BY_LANGUAGE.items()
}
_MONTH_DATE = _MONTH_DATE_BY_LANGUAGE["en"]
_WEEKDAY = _WEEKDAY_BY_LANGUAGE["en"]
_ZH_DATE = re.compile(r"\d{1,2}月\d{1,2}日")
_ZH_WEEKDAY = re.compile(r"(?:星期|周|禮拜|礼拜)[一二三四五六日天]")
"""Chinese says the date and then the day: "9月29日星期一". The weekday stands right beside
the date, before or after it."""


def _tables_for(language: str) -> tuple[re.Pattern[str], re.Pattern[str], tuple[str, ...]]:
    """The month-date and weekday patterns, and the whole month names, for a language. A
    language with no table of its own is read as English."""
    code = language if language in _MONTHS_BY_LANGUAGE else "en"
    return _MONTH_DATE_BY_LANGUAGE[code], _WEEKDAY_BY_LANGUAGE[code], _MONTHS_BY_LANGUAGE[code]


_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_NRIC = re.compile(r"\b[STFGMstfgm]\d{7}[A-Za-z]\b")
_MYKAD = re.compile(r"\b\d{6}-\d{2}-\d{4}\b")
_LONG_HEX = re.compile(r"\b[0-9a-f]{16,}\b")
_DIGIT_RUN = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{6,}\d(?![\w.])")

_ABBREVIATION = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")
_LATIN_ABBREVIATION = re.compile(r"\b(?:e\.g\.|i\.e\.|etc\.|vs\.?|approx\.|w/o)", re.IGNORECASE)
_UNIT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:mg/dL|mmol/L|mmHg|mmol|mcg|µg|ug|mg|mL|ml|dL|bpm|mEq|IU)\b"
)
ABBREVIATIONS_HE_USES = frozenset({"OK", "IC", "TV"})

EVERYDAY_WORDS = frozenset(
    {
        "everything",
        "everybody",
        "everywhere",
        "anybody",
        "emergency",
        "cholesterol",
        "temperature",
        "information",
        "understanding",
        "operation",
        "ambulance",
        "diabetes",
        "usually",
        "especially",
        "immediately",
        "ordinary",
        "necessary",
        "available",
        "comfortable",
        "vegetables",
        "medicines",
        "explanation",
    }
)
"""Long words he already uses, so their length is not held against them."""

NUMBER_WORDS: dict[str, str] = {
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
}
"""Rule 10 says digits. "One" is his word as often as a number ("One tablet was late.")."""

_BASE_VERBS = [
    "add",
    "agree",
    "answer",
    "arrive",
    "ask",
    "become",
    "begin",
    "bend",
    "book",
    "breathe",
    "bring",
    "call",
    "care",
    "carry",
    "change",
    "check",
    "choose",
    "close",
    "collect",
    "come",
    "cost",
    "cough",
    "count",
    "cover",
    "decide",
    "describe",
    "die",
    "do",
    "drink",
    "drive",
    "drop",
    "eat",
    "expect",
    "explain",
    "fall",
    "feel",
    "fill",
    "find",
    "finish",
    "forget",
    "get",
    "give",
    "go",
    "grow",
    "hand",
    "happen",
    "have",
    "hear",
    "help",
    "hold",
    "hurt",
    "include",
    "keep",
    "know",
    "learn",
    "leave",
    "let",
    "lie",
    "like",
    "listen",
    "live",
    "lock",
    "look",
    "love",
    "make",
    "matter",
    "mean",
    "measure",
    "meet",
    "move",
    "need",
    "open",
    "pay",
    "pick",
    "play",
    "prefer",
    "press",
    "provide",
    "put",
    "reach",
    "read",
    "remember",
    "rest",
    "ring",
    "rise",
    "run",
    "save",
    "say",
    "see",
    "seem",
    "send",
    "share",
    "show",
    "shut",
    "sign",
    "sit",
    "sleep",
    "sound",
    "speak",
    "stand",
    "start",
    "stay",
    "stop",
    "swell",
    "take",
    "talk",
    "tell",
    "think",
    "tire",
    "try",
    "turn",
    "type",
    "understand",
    "use",
    "visit",
    "wait",
    "wake",
    "walk",
    "want",
    "watch",
    "wear",
    "weigh",
    "work",
    "worry",
    "write",
]
_IRREGULAR_VERBS = [
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "had",
    "having",
    "goes",
    "does",
    "did",
    "done",
    "can",
    "could",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "ate",
    "began",
    "begun",
    "bent",
    "bought",
    "brought",
    "came",
    "chose",
    "chosen",
    "cost",
    "did",
    "drank",
    "drove",
    "drunk",
    "fell",
    "felt",
    "found",
    "forgot",
    "gave",
    "given",
    "gone",
    "went",
    "got",
    "grew",
    "grown",
    "heard",
    "held",
    "hurt",
    "kept",
    "knew",
    "known",
    "lay",
    "left",
    "let",
    "lost",
    "made",
    "met",
    "paid",
    "put",
    "ran",
    "rang",
    "read",
    "rose",
    "said",
    "sat",
    "saw",
    "seen",
    "sent",
    "shut",
    "slept",
    "sold",
    "spoke",
    "spoken",
    "stood",
    "swollen",
    "took",
    "taken",
    "thought",
    "told",
    "understood",
    "woke",
    "woken",
    "wore",
    "worn",
    "wrote",
    "written",
]


def _inflect(base: str) -> Iterator[str]:
    yield base
    if base.endswith(("s", "x", "ch", "sh")):
        yield base + "es"
    elif base.endswith("y") and base[-2] not in "aeiou":
        yield base[:-1] + "ies"
        yield base[:-1] + "ied"
    else:
        yield base + "s"
    if base.endswith("e"):
        yield base + "d"
        yield base[:-1] + "ing"
    else:
        yield base + "ed"
        yield base + "ing"


VERB_FORMS = frozenset(form for base in _BASE_VERBS for form in _inflect(base)) | frozenset(
    _IRREGULAR_VERBS
)
NEEDS_AN_OBJECT = frozenset(
    [
        "explain",
        "explains",
        "explained",
        "show",
        "shows",
        "showed",
        "tell",
        "tells",
        "told",
        "give",
        "gives",
        "gave",
        "mean",
        "means",
        "meant",
        "cover",
        "covers",
        "covered",
        "include",
        "includes",
        "included",
        "describe",
        "describes",
        "described",
        "provide",
        "provides",
        "provided",
        "bring",
        "brings",
        "brought",
        "make",
        "makes",
        "made",
        "let",
        "lets",
        "say",
        "says",
        "said",
        "keep",
        "keeps",
        "kept",
    ]
)
_OBJECT_STANDS_IN = frozenset(["what", "who", "which", "that", "it", "this", "them", "so"])
SUBJECTS = frozenset(["i", "you", "he", "she", "it", "we", "they", "nura", "this", "that", "who"])
_DETERMINERS = frozenset(
    [
        "the",
        "a",
        "an",
        "your",
        "my",
        "his",
        "her",
        "their",
        "our",
        "this",
        "that",
        "these",
        "those",
        "some",
        "any",
        "every",
        "each",
        "no",
        "only",
        "all",
    ]
)
_TIME_WORDS = re.compile(
    r"\b(?:today|tonight|tomorrow|now|morning|evening|afternoon|night|midnight|noon|"
    r"every|daily|before|after|at \d|by \d|when you|" + "|".join(WEEKDAYS) + r")\b",
    re.IGNORECASE,
)
_ACTOR_WORDS = re.compile(r"\b(?:Nura|you|your|yourself|Dr\s+[A-Z]\w*|the doctor|the nurse|I|we)\b")

# Fillers for `{slots}`: by exact slot name, then by a word the name contains.
FILLERS: dict[str, str] = {
    "doctor": "Dr Tan",
    "me": "you",
    "you": "you",
    "mine": "your",
    "your": "your",
    "patients": "your",
    "relationship": "your daughter",
    "title": "Keeping your papers",
    "language": "English",
    "language_name": "English",
    "region": "Singapore",
    "region_name": "Singapore",
    "country": "Singapore",
    "parts": "your medicines",
    "lines": "your medicines",
    "what_lines": "your medicines",
    "items": "your medicines",
    "opens": "open",
    "can": "can see",
    "captured_via_words": "on paper",
    "channel": "on paper",
}
_FILLER_BY_WORD: tuple[tuple[str, str], ...] = (
    ("date", "Monday 14 September"),
    ("day", "Monday 14 September"),
    ("when", "Monday 14 September"),
    ("plain", "Monday 14 September"),
    ("time", "Monday 14 September"),
    ("at", "Monday 14 September"),
    ("count", "2"),
    ("number", "2"),
    ("code", "2"),
    ("amount", "2"),
    ("total", "2"),
    ("kg", "2"),
    ("days", "2"),
    ("minutes", "2"),
    ("hours", "2"),
    ("weight", "2"),
    ("n", "2"),
)
DEFAULT_FILLER = "Ash"
_SLOT = re.compile(r"(?<!\{)\{([^{}]*)\}(?!\})")


_DAY_FILLER: dict[str, str] = {
    "en": "Monday 14 September",
    "ms": "Isnin 14 September",
    "zh": "9月14日星期一",
}
_TIME_FILLER: dict[str, str] = {"en": "10 in the morning", "ms": "10 pagi", "zh": "上午10点"}
"""A day and a time as the line's own language says them, so rule 5 reads a Malay or Chinese
template against its own weekday and month tables (E05 review, P3)."""


def filler_for(slot: str, language: str = "en") -> str:
    """The representative value a `{slot}` is checked with, from its name and the language."""
    name = slot.strip().split("!")[0].split(":")[0].strip().lower()
    if name in FILLERS:
        return FILLERS[name]
    parts = re.split(r"[^a-z0-9]+", name)
    if "time" in parts:
        return _TIME_FILLER.get(language, _TIME_FILLER["en"])
    for word, value in _FILLER_BY_WORD:
        if word in parts:
            if value == _DAY_FILLER["en"]:
                return _DAY_FILLER.get(language, value)
            return value
    return DEFAULT_FILLER


def fill(template: str, language: str = "en") -> str:
    """The template with every `{slot}` replaced by its filler; `{{` and `}}` become braces."""
    return (
        _SLOT.sub(lambda m: filler_for(m.group(1), language), template)
        .replace("{{", "{")
        .replace("}}", "}")
    )


# --- the checks --------------------------------------------------------------------------------

_CJK = re.compile(r"[㐀-䶿一-鿿　-〿＀-￯]")
_WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’-](?=[^\W\d_]))*")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(A-Z0-9])|(?<=[.!?][\"')])\s+(?=[\"'(A-Z0-9])")
_ZH_TERMINATOR = re.compile(r"[。！？；]")
_LEADING = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)?")
_HEADING = re.compile(r"^\s*(#+)\s*")


def language_of(text: str, fallback: str = "en") -> str:
    """Chinese by its script; otherwise what the source said, or English."""
    return "zh" if _CJK.search(text) else fallback


def syllables(word: str) -> int:
    """A rough count: vowel groups, minus a silent ending."""
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if (
        n > 1
        and w.endswith("e")
        and not w.endswith(("le", "ee", "ye", "oe"))
        or n > 1
        and w.endswith(("es", "ed"))
        and not w.endswith(("ses", "zes", "ted", "ded", "ies"))
    ):
        n -= 1
    return max(n, 1)


def has_letters(text: str) -> bool:
    return bool(re.search(r"[^\W\d_]", _SLOT.sub("", text)))


def is_code_token(text: str) -> bool:
    """`"en"`, `"out_of_date"`, `"text/markdown"`: a token for the program, not a word for him."""
    return re.fullmatch(r"[a-z0-9_.:/%+-]+", text) is not None


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def _substitute(line: str, match: re.Match[str], say: str) -> str:
    """The line with the red word replaced by the plain phrase, doubled articles dropped."""
    before = line[: match.start()]
    phrase = say
    if re.search(r"\b(?:the|your|a|an|his|my|their)\s+$", before, re.IGNORECASE):
        phrase = re.sub(r"^(?:the|your|a|an)\s+", "", phrase, flags=re.IGNORECASE)
    if match.start() == 0 or before.strip() == "":
        phrase = phrase[:1].upper() + phrase[1:]
    return before + phrase + line[match.end() :]


class _Line:
    """One line under check: the source as written and the filled text the rules read."""

    def __init__(self, source: str, language: str, kind: Kind, offset: int) -> None:
        self.source = source
        self.language = language
        self.kind: Kind = kind
        self.offset = offset
        stripped = _LEADING.sub("", source)
        heading = _HEADING.match(stripped)
        if heading:
            self.kind = "headline"
            stripped = stripped[heading.end() :]
        self.template = stripped.strip()
        self.slot_initial = self.template.startswith("{")
        self.text = fill(self.template, language)
        self.findings: list[Finding] = []
        self.covered: list[tuple[int, int]] = []

    def add(
        self, rule: int, problem: str, rewrite: str, severity: Literal["fail", "note"] = "fail"
    ) -> None:
        self.findings.append(
            Finding(
                rule,
                problem,
                rewrite,
                self.source,
                severity,
                self.language,
                self.kind,
                offset=self.offset,
            )
        )

    def cover(self, match: re.Match[str]) -> bool:
        """Claim a span so a later rule does not report the same words again."""
        span = match.span()
        if any(start < span[1] and span[0] < end for start, end in self.covered):
            return False
        self.covered.append(span)
        return True


def _check_identifiers(line: _Line) -> None:
    for pattern, what in (
        (_UUID, "an id"),
        (_EMAIL, "an email address"),
        (_NRIC, "an IC number"),
        (_MYKAD, "an IC number"),
        (_LONG_HEX, "a code"),
        (_DIGIT_RUN, "a phone number or an id"),
    ):
        for match in pattern.finditer(line.text):
            if pattern is _DIGIT_RUN and sum(c.isdigit() for c in match.group()) < 8:
                continue
            if line.cover(match):
                line.add(
                    12,
                    f'{what} he would have to decode: "{match.group()}"',
                    "never show a number that identifies him; say his name, or say nothing",
                )


def _check_dates(line: _Line) -> None:
    for match in _NUMERIC_DATE.finditer(line.text):
        if line.cover(match):
            line.add(
                5,
                f'a date as numbers: "{match.group()}"',
                'say the day and the date: "Monday 14 September"',
            )
    for match in _CLOCK_TIME.finditer(line.text):
        if line.cover(match):
            line.add(5, f'a clock time: "{match.group()}"', 'say it as he would: "Thursday at 10"')
    for match in _TIME_ZONE.finditer(line.text):
        if line.cover(match):
            line.add(
                5, f'a time zone: "{match.group()}"', 'his own clock, no zone: "Thursday at 10"'
            )
    for match in _ORDINAL_DAY.finditer(line.text):
        if line.cover(match):
            line.add(
                5,
                f'the date without the day: "{match.group()}"',
                'say the day and the date: "Monday 29 September"',
            )
    if line.language == "zh":
        for match in _ZH_DATE.finditer(line.text):
            around = line.text[max(0, match.start() - 4) : match.end() + 4]
            if not _ZH_WEEKDAY.search(around) and line.cover(match):
                line.add(
                    5,
                    f'the date without the day: "{match.group()}"',
                    f'say the day too: "{match.group()}星期一"',
                )
        return
    month_date, weekday, whole_months = _tables_for(line.language)
    for match in month_date.finditer(line.text):
        before = line.text[: match.start()]
        preceding = " ".join(before.split()[-3:])
        if not weekday.search(preceding) and line.cover(match):
            line.add(
                5,
                f'the date without the day: "{match.group()}"',
                f'say the day too: "{_WEEKDAYS_BY_LANGUAGE.get(line.language, WEEKDAYS)[0]} {match.group()}"',
            )
    month_shortenings = _MONTH_ABBREVIATIONS_MS if line.language == "ms" else _MONTH_ABBREVIATIONS
    for pattern, what, example in (
        (month_shortenings, "month", "September"),
        (_DAY_ABBREVIATIONS, "day", "Monday"),
    ):
        for match in pattern.finditer(line.text):
            # A whole month name in the line's language ("Jun", "Mac" in Malay) is no shortening.
            if match.group().rstrip(".") in whole_months:
                continue
            if line.cover(match):
                line.add(
                    5,
                    f'a shortened {what}: "{match.group()}"',
                    f'write the {what} out: "{example}"',
                )


def _term_pattern(word: str) -> re.Pattern[str]:
    flags = 0 if word.isupper() else re.IGNORECASE
    return re.compile(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", flags)


_TERM_PATTERNS: tuple[tuple[Term, re.Pattern[str]], ...] = tuple(
    (term, _term_pattern(word)) for term in GLOSSARY for word in term.words
)


def _check_same_words(line: _Line) -> None:
    if line.language != "en":
        return
    for pattern, canonical in SAME_WORDS:
        for match in pattern.finditer(line.text):
            if line.cover(match):
                line.add(
                    13,
                    f'"{match.group()}" is not his word for it',
                    _substitute(line.text, match, canonical),
                )


def _check_glossary(line: _Line) -> None:
    lowered = line.text.lower()
    for term, pattern in _TERM_PATTERNS:
        if term.alongside and any(plain in lowered for plain in term.alongside):
            continue
        for match in pattern.finditer(line.text):
            if term.words == ("record",) and _POSSESSED_RECORD.search(line.text[: match.end()]):
                continue
            if not line.cover(match):
                continue
            word = match.group()
            if term.rule == 11:
                line.add(11, f'a red word: "{word}"', term.say)
            elif term.alongside:
                line.add(
                    4, f'"{word}" stands alone', f'his name for it first: "{term.say} ({word})"'
                )
            else:
                problem = (
                    f'"{word}" is a word he would have to decode'
                    if term.rule == 12
                    else f'"{word}" is not his word'
                )
                line.add(term.rule, problem, _substitute(line.text, match, term.say))


def _check_abbreviations(line: _Line) -> None:
    for match in _ABBREVIATION.finditer(line.text):
        token = match.group()
        if token in ABBREVIATIONS_HE_USES or not any(c.isalpha() for c in token[1:]):
            continue
        if line.cover(match):
            line.add(12, f'an abbreviation: "{token}"', "write the words out, or leave it out")
    for match in _LATIN_ABBREVIATION.finditer(line.text):
        if line.cover(match):
            line.add(
                12,
                f'an abbreviation: "{match.group().strip()}"',
                'say it in words: "for example", "and so on"',
            )
    for match in _UNIT.finditer(line.text):
        if line.cover(match):
            line.add(
                12,
                f'a unit he does not use: "{match.group()}"',
                'say it his way: "half a tablet", "148", "1 kg"',
            )


def _check_numbers(line: _Line) -> None:
    if line.language == "en":
        for match in re.finditer(r"\b[A-Za-z]+\b", line.text):
            digits = NUMBER_WORDS.get(match.group().lower())
            if digits and line.cover(match):
                line.add(
                    10,
                    f'a number in words: "{match.group()}"',
                    _substitute(line.text, match, digits),
                )
    # A Chinese date is one number, the way "14 September" is: "9月14日" says one day.
    if len(_NUMBER.findall(_ZH_DATE.sub("1", line.text))) > 3:
        line.add(
            10,
            "more than three numbers on one line",
            "one number per idea; a second number is a second line",
        )


def _sentences(line: _Line) -> list[str]:
    if line.language == "zh":
        pieces = _ZH_TERMINATOR.split(line.text)
        return [p for p in pieces if _CJK.search(p) or has_letters(p)]
    pieces = [p for part in _SENTENCE_SPLIT.split(line.text) for p in part.split(";")]
    return [p.strip() for p in pieces if has_letters(p)]


def _check_one_idea(line: _Line) -> None:
    sentences = _sentences(line)
    if len(sentences) > 1:
        line.add(2, f"{len(sentences)} ideas on one line", " / ".join(sentences))


def _has_verb(words: Sequence[str]) -> bool:
    lowered = [w.lower() for w in words]
    for index, word in enumerate(lowered):
        if word in VERB_FORMS:
            return True
        if (
            word.endswith("ed")
            and len(word) > 4
            and word not in {"need", "indeed", "bed", "red", "shed"}
        ):
            return True
        if (
            index
            and word.endswith("s")
            and lowered[index - 1] in SUBJECTS
            and lowered[index - 1] not in _DETERMINERS
        ):
            return True
    return False


def _check_whole_sentence(line: _Line) -> None:
    text = line.text.rstrip("\"'”’)")
    if line.language == "zh":
        if text and text[-1] not in "。！？：":
            line.add(1, "the line does not end", f"{line.template}。")
        return
    words = _words(text)
    if not words:
        return
    first = text.lstrip("\"'“‘(")[:1]
    if not line.slot_initial and first.islower():
        line.add(
            1, "the line starts with a small letter", line.template[:1].upper() + line.template[1:]
        )
    if text[-1] not in ".!?:":
        line.add(1, "the line has no full stop", f"{line.template}.")
    if line.language != "en":
        return
    last = words[-1].lower()
    lowered = {w.lower() for w in words}
    if last in NEEDS_AN_OBJECT and not (lowered & _OBJECT_STANDS_IN):
        line.add(
            1,
            f'"{words[-1]}" what? the sentence stops short',
            'finish the thought: "A heart doctor talks about the water pill and bananas."',
        )
    elif not _has_verb(words) or len(words) < 2:
        line.add(
            1,
            "a fragment, not a sentence: nobody does anything in it",
            'a whole sentence a daughter would say: who does what. "It is 30 seconds long."',
        )


def _check_length(line: _Line) -> None:
    if line.language == "zh":
        return
    count = len(_words(line.text))
    if count > 15:
        line.add(3, f"{count} words on one line", "cut it into two lines, one idea each")
    elif count > 10 and line.kind != "headline":
        line.add(
            3,
            f"{count} words; under ten where it can be done",
            "a shorter line, if it can be done",
            "note",
        )
    if line.language != "en":
        return
    alongside = {plain for term in GLOSSARY for plain in term.words}
    for index, word in enumerate(_words(line.text)):
        low = word.lower()
        if index and word[:1].isupper():
            continue  # a name
        if low in EVERYDAY_WORDS or low in alongside or len(word) < 9 or syllables(word) < 4:
            continue
        line.add(
            3,
            f'"{word}" is a long word he would have to ask about',
            "a short everyday word instead",
        )


_TREATMENT_VERBS: dict[str, re.Pattern[str]] = {
    "en": re.compile(
        r"\b(?:start|starts|started|starting|stop|stops|stopped|stopping|double|doubles|"
        r"doubled|halve|halves|halved|increase|increases|increased|reduce|reduces|reduced|"
        r"take (?:more|less))\b",
        re.IGNORECASE,
    ),
    "ms": re.compile(
        r"\b(?:mula (?:makan|ambil)|berhenti (?:makan|ambil)|tambah|kurangkan|gandakan)\b",
        re.IGNORECASE,
    ),
    "zh": re.compile(r"开始吃|停吃|停药|停止吃|多吃|少吃|加量|减量|加倍"),
}
_MEDICINE_NOUNS: dict[str, re.Pattern[str]] = {
    "en": re.compile(
        r"\b(?:tablets?|pills?|capsules?|medicines?|insulin|injections?|aspirin|"
        r"water pill|sugar tablet|cholesterol tablet|blood pressure tablet)\b",
        re.IGNORECASE,
    ),
    "ms": re.compile(r"\b(?:ubat|pil|tablet|kapsul|insulin|suntikan|aspirin)\b", re.IGNORECASE),
    "zh": re.compile(r"药|片|胰岛素|阿司匹林"),
}
_CLINICIAN = r"(?:dr\.?\s|doctor|doktor|pharmacist|ahli farmasi)"
_ASKING = re.compile(
    r"^\W*(?:ask|tell)\b.{0,16}?"
    + _CLINICIAN
    + r"|^\W*(?:tanya|beritahu)\b.{0,16}?"
    + _CLINICIAN
    + r"|^\W*(?:问一问|问|告诉).{0,10}?(?:医生|大夫|药剂师|dr\.?\s)",
    re.IGNORECASE,
)
"""The boundary (CLAUDE.md): no line the patient reads starts, stops or changes a medicine.
A treatment-changing verb beside a medicine noun fails unless the line is a question put to
the doctor (or the pharmacist) — it begins by asking or telling *them*: "Ask Dr Tan about…",
"Tell Dr Tan about…", "Tanya doktor anda…", "问一问陈医生…". A line that tells someone else
("Tell Ash to stop the water pill.") or merely ends in a question mark is not one. Kept
tight the other way too: a verb alone ("You can tell Nura to stop at any time.") or a noun
alone passes."""

_ZH_NUMERALS = "一二三四五六七八九十百半两"


def _generic_token(language: str) -> str:
    """The fallback shape for a slot with no closed vocabulary to check against: one word in
    `en`/`ms` (no space — a space is how a whole extra clause hid inside the slot: "the water
    pill till Friday" as {medicine}, "Ash to stop the water pill" as {doctor}, both letters and
    spaces and nothing else, so a char class alone never caught them); one character in `zh`,
    which has no space to bound a run on at all ("不要自己停药改用胰岛素。" passed with
    medicine="药改用胰岛素", every character in it a plain CJK letter). No digit in any script
    either way, the CJK numerals (`_ZH_NUMERALS`) included, since those are ordinary characters
    in the CJK block and would otherwise pass as "letters" too.

    `app.medicines.strings.PLAIN_NAME` is the closed vocabulary for the medicine slot's own
    friendly, multi-word phrases ("the water pill"); this is only the fallback for a bare
    technical name beside them ("furosemide", "药"). Nothing closes the doctor slot — a real
    name — so it is always this fallback, single word or single character."""
    if language == "zh":
        return rf"(?:(?![{_ZH_NUMERALS}0-9])[\u4e00-\u9fffA-Za-z])"
    return r"[A-Za-z][A-Za-z'()-]*"


@cache
def _keep_taking_pattern(language: str) -> re.Pattern[str]:
    """The whitelist for rule 14's one allowance (#157): the line passes only if it is exactly
    one of `DO_NOT_STOP`'s templates (`app.reasoning.feelings.strings`) with its slots filled —
    the medicine slot a name the app itself uses (`app.medicines.strings.PLAIN_NAME`) or a bare
    technical name, the doctor slot a name (both `_generic_token`). Built from the templates
    themselves, not typed out again, so the two cannot drift apart.

    Imports lazily: `app.medicines` imports `app.safety.high_risk` at package level, so an
    import of `app.medicines.strings` at this module's top level would cycle back here."""
    from app.medicines.strings import PLAIN_NAME
    from app.reasoning.feelings.strings import DO_NOT_STOP

    known = sorted(PLAIN_NAME[language].values(), key=len, reverse=True)
    token = _generic_token(language)
    medicine = "(?:{}|{})".format("|".join(re.escape(name) for name in known), token)
    doctor = token
    alternatives = []
    for template in DO_NOT_STOP[language]:
        slotted = re.escape(template)
        slotted = slotted.replace(re.escape("{medicine}"), medicine)
        slotted = slotted.replace(re.escape("{doctor}"), doctor)
        alternatives.append(slotted)
    return re.compile("^(?:{})$".format("|".join(alternatives)))


def _check_boundary(line: _Line) -> None:
    language = line.language if line.language in _TREATMENT_VERBS else "en"
    verbs, nouns = _TREATMENT_VERBS[language], _MEDICINE_NOUNS[language]
    verb = verbs.search(line.text)
    if verb is None or nouns.search(line.text) is None:
        return
    if _ASKING.search(line.text):
        return
    if len(verbs.findall(line.text)) == 1 and _keep_taking_pattern(language).search(
        line.text.strip()
    ):
        return
    line.add(
        14,
        f'a medicine started, stopped or changed: "{verb.group()}"',
        'a question for the doctor: "Ask Dr Tan about the new amount of the water pill."',
    )


def _check_action(line: _Line) -> None:
    if line.language != "en":
        return
    words = _words(line.text)
    if not words:
        return
    lowered = [w.lower() for w in words]
    # A name before a verb ("Ash will", "Mei picks"); a sentence-initial "It" or "This" is not one.
    named = bool(_ACTOR_WORDS.search(line.text)) or any(
        w[:1].isupper()
        and lowered[i] not in SUBJECTS
        and lowered[i] not in _DETERMINERS
        and lowered[i] not in {"there", "here", "then"}
        and lowered[i + 1] in VERB_FORMS
        for i, w in enumerate(words[:-1])
    )
    lead = re.split(r",\s*", line.text, maxsplit=1)
    imperative_start = _words(lead[-1])[:1]
    imperative = (
        bool(imperative_start)
        and imperative_start[0].lower() in VERB_FORMS
        and (
            imperative_start[0].lower()
            not in {
                "is",
                "are",
                "was",
                "were",
                "has",
                "have",
                "had",
                "does",
                "do",
                "did",
                "can",
                "will",
                "would",
                "could",
                "should",
                "may",
                "might",
                "must",
            }
        )
    )
    if not named and not imperative:
        line.add(
            7,
            "it does not say who does the next thing",
            'name them: "Ash will book it." "Mei will pick you up at 9."',
        )
    if imperative and not _TIME_WORDS.search(line.text):
        line.add(
            6,
            "it says what to do but not when",
            'say when: "Every morning, stand on the scale before breakfast."',
        )


def verify(text: str, language: str = "en", kind: Kind = "line") -> list[Finding]:
    """Every failure and note in `text`, one line at a time, against the doc.

    `language` is the language the text is written in (`en`, `ms`, `zh`, `ta`); Chinese script
    is recognised whatever is passed. `kind` is how to read each line: a whole `line` he reads
    or hears, a `phrase` that fills a slot in a line, a `headline`, or an `action` card that
    must say who does the next thing and when. A line starting `#` is a headline; a leading
    bullet is not part of the line. `{slots}` are filled with representative values first.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    findings: list[Finding] = []
    for offset, source in enumerate(text.splitlines() or [text]):
        if not has_letters(source):
            continue
        line = _Line(source, language_of(source, language), kind, offset)
        if not has_letters(line.template):
            continue
        _check_identifiers(line)
        _check_dates(line)
        _check_same_words(line)
        _check_glossary(line)
        _check_abbreviations(line)
        _check_numbers(line)
        if line.kind in ("line", "action"):
            _check_one_idea(line)
            _check_whole_sentence(line)
        if line.kind != "phrase":
            _check_length(line)
        elif line.language == "en":
            _check_length_of_words_only(line)
        if line.kind == "action":
            _check_action(line)
        if line.kind != "phrase":
            _check_boundary(line)
        findings.extend(line.findings)
    return findings


def _check_length_of_words_only(line: _Line) -> None:
    """A phrase has no line length to speak of, but its words must still be his."""
    alongside = {plain for term in GLOSSARY for plain in term.words}
    for index, word in enumerate(_words(line.text)):
        low = word.lower()
        if (index and word[:1].isupper()) or low in EVERYDAY_WORDS or low in alongside:
            continue
        if len(word) >= 9 and syllables(word) >= 4:
            line.add(
                3,
                f'"{word}" is a long word he would have to ask about',
                "a short everyday word instead",
            )


# --- finding the strings in the source ---------------------------------------------------------

_TAG = re.compile(r"^@patient\b(?:\s+(line|phrase|headline|action)\b)?", re.IGNORECASE)
_EXEMPT = re.compile(r"^#\s*plain-words\s*:", re.IGNORECASE)
_COMMENT_TAG = re.compile(r"^#\s*@patient\b(?:\s+(line|phrase|headline|action)\b)?", re.IGNORECASE)
CODE_METHODS = frozenset(
    [
        # str methods whose arguments are for the program, not for him (`join` is not here:
        # `"\n".join([...])` joins his lines, and the receiver is skipped on its own).
        "split",
        "rsplit",
        "splitlines",
        "encode",
        "decode",
        "strip",
        "lstrip",
        "rstrip",
        "startswith",
        "endswith",
        "replace",
        "get",
        "setdefault",
        "pop",
        "format",
        "format_map",
        # regular expressions, reflection, files
        "compile",
        "match",
        "search",
        "sub",
        "subn",
        "findall",
        "finditer",
        "fullmatch",
        "getattr",
        "hasattr",
        "setattr",
        "isinstance",
        "open",
        # logging and argparse
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "log",
        "add_argument",
    ]
)


def _tag_kind(word: str | None) -> Kind:
    lowered = (word or "line").lower()
    return lowered if lowered in KINDS else "line"  # type: ignore[return-value]


def _start_line(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(d.lineno for d in decorators)])


def _statements(tree: ast.AST) -> list[ast.stmt]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.stmt)]


def _bodies(tree: ast.AST) -> Iterator[list[ast.stmt]]:
    for node in ast.walk(tree):
        for name in ("body", "orelse", "finalbody"):
            body = getattr(node, name, None)
            if isinstance(body, list) and body and isinstance(body[0], ast.stmt):
                yield body
        for handler in getattr(node, "handlers", []):
            yield handler.body
        for case in getattr(node, "cases", []):
            yield case.body


def _is_tag_string(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and _TAG.match(node.value.value.strip()) is not None
    )


def tagged_statements(source: str) -> list[tuple[ast.stmt, Kind]]:
    """Every statement carrying a `@patient` tag, with the kind the tag names."""
    tree = ast.parse(source)
    statements = _statements(tree)
    tagged: list[tuple[ast.stmt, Kind]] = []
    lines = source.splitlines()

    def outermost_at(line: int) -> ast.stmt | None:
        here = [s for s in statements if _start_line(s) == line]
        return (
            max(here, key=lambda s: (s.end_lineno or s.lineno) - _start_line(s)) if here else None
        )

    for token in tokenize.generate_tokens(_reader(source)):
        if token.type != tokenize.COMMENT:
            continue
        match = _COMMENT_TAG.match(token.string)
        if not match:
            continue
        row, column = token.start
        kind = _tag_kind(match.group(1))
        if lines[row - 1][:column].strip():
            target = outermost_at(row) or _enclosing(statements, row)
        else:
            following = [s for s in statements if _start_line(s) > row]
            target = outermost_at(min(_start_line(s) for s in following)) if following else None
        if target is not None:
            tagged.append((target, kind))
    for body in _bodies(tree):
        for index, node in enumerate(body):
            if index and _is_tag_string(node):
                value = node.value.value  # type: ignore[attr-defined]
                tagged.append((body[index - 1], _tag_kind(_TAG.match(value.strip()).group(1))))  # type: ignore[union-attr]
    return tagged


def _reader(source: str) -> Callable[[], str]:
    """A readline for `tokenize` over a string already in memory."""
    it = iter(source.splitlines(keepends=True))
    return lambda: next(it, "")


def _enclosing(statements: Iterable[ast.stmt], line: int) -> ast.stmt | None:
    inside = [s for s in statements if _start_line(s) <= line <= (s.end_lineno or s.lineno)]
    return (
        min(inside, key=lambda s: (s.end_lineno or s.lineno) - _start_line(s)) if inside else None
    )


def _slot_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            return node.slice.value
        return _slot_name(node.value)
    if isinstance(node, ast.Call):
        return _slot_name(node.func)
    return "value"


def _template_of(node: ast.JoinedStr) -> str:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value).replace("{", "{{").replace("}", "}}"))
        elif isinstance(value, ast.FormattedValue):
            parts.append("{" + _slot_name(value.value) + "}")
    return "".join(parts)


def _docstring_of(node: ast.AST) -> ast.stmt | None:
    body = getattr(node, "body", None)
    if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return body[0]
    return None


def _language_beside(node: ast.Call) -> str | None:
    for arg in [*node.args, *(k.value for k in node.keywords)]:
        if (
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and arg.value in LANGUAGE_CODES
        ):
            return arg.value
    return None


def literals_in(node: ast.AST, language: str = "en") -> Iterator[tuple[str, int, int, str]]:
    """Every patient-text literal in a tagged statement: (text, first line, last line, language).

    Literals in code positions are skipped; see the module docstring for the list.
    """
    yield from _literals(node, language, False)


def _literals(node: ast.AST, language: str, code: bool) -> Iterator[tuple[str, int, int, str]]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str) and not code:
            yield node.value, node.lineno, node.end_lineno or node.lineno, language
        return
    if isinstance(node, ast.JoinedStr):
        if not code:
            yield _template_of(node), node.lineno, node.end_lineno or node.lineno, language
        return
    if isinstance(node, (ast.Raise, ast.Assert)):
        return
    if isinstance(node, ast.Expr) and _is_tag_string(node):
        return
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        docstring = _docstring_of(node)
        for child in ast.iter_child_nodes(node):
            if child is docstring or child in node.decorator_list:
                continue
            if child is getattr(node, "returns", None) or child is getattr(node, "args", None):
                continue
            yield from _literals(child, language, code)
        return
    if isinstance(node, ast.AnnAssign):
        yield from _literals(node.target, language, True)
        if node.value is not None:
            yield from _literals(node.value, language, code)
        return
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            here = language
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in LANGUAGE_CODES
            ):
                here = key.value
            yield from _literals(value, here, code)
        return
    if isinstance(node, ast.Subscript):
        yield from _literals(node.value, language, code)
        yield from _literals(node.slice, language, True)
        return
    if isinstance(node, ast.Compare):
        yield from _literals(node.left, language, True)
        for comparator in node.comparators:
            yield from _literals(comparator, language, True)
        return
    if isinstance(node, ast.Attribute):
        yield from _literals(node.value, language, code or isinstance(node.value, ast.Constant))
        return
    if isinstance(node, ast.Call):
        method = (
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        )
        arguments_are_code = code or method in CODE_METHODS
        here = _language_beside(node) or language
        yield from _literals(node.func, language, code)
        for arg in node.args:
            yield from _literals(arg, here, arguments_are_code)
        for keyword in node.keywords:
            yield from _literals(keyword.value, here, arguments_are_code)
        return
    for child in ast.iter_child_nodes(node):
        yield from _literals(child, language, code)


def _lines_of(text: str, first: int, last: int) -> Iterator[tuple[int, str]]:
    """Each line of a literal with its source line, when the literal is laid out one per line."""
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    spans = last - first + 1
    for index, part in enumerate(parts):
        yield (first + index if len(parts) == spans else first), part


def exempt_lines(source: str) -> set[int]:
    """The lines carrying a `# plain-words: <reason>` comment: a literal starting there is history."""
    return {
        token.start[0]
        for token in tokenize.generate_tokens(_reader(source))
        if token.type == tokenize.COMMENT and _EXEMPT.match(token.string)
    }


def strings_in_python(path: Path, source: str | None = None) -> list[PatientString]:
    """Every patient string in one Python file, one per line of text."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    exempt = exempt_lines(text)
    found: list[PatientString] = []
    seen: set[tuple[int, str]] = set()
    for statement, kind in tagged_statements(text):
        for literal, first, last, language in literals_in(statement):
            if not has_letters(literal) or is_code_token(literal):
                continue
            for line, part in _lines_of(literal, first, last):
                if not has_letters(part) or (line, part) in seen:
                    continue
                seen.add((line, part))
                found.append(
                    PatientString(
                        path, line, part, language_of(part, language), kind, first in exempt
                    )
                )
    return found


def strings_in_xcstrings(path: Path, source: str | None = None) -> list[PatientString]:
    """Every patient string in an Xcode strings catalogue: entries whose comment carries the tag."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    catalogue = json.loads(text)
    default_language = catalogue.get("sourceLanguage", "en")
    found: list[PatientString] = []
    for key, entry in catalogue.get("strings", {}).items():
        comment = str(entry.get("comment", "")).strip()
        match = re.match(
            r"^(?:@?patient)\b(?:\s+(line|phrase|headline|action)\b)?", comment, re.IGNORECASE
        )
        if not match and "@patient" not in comment:
            continue
        kind = _tag_kind(match.group(1) if match else None)
        line = next((n for n, l in enumerate(text.splitlines(), 1) if json.dumps(key) in l), 1)
        localizations = entry.get("localizations") or {}
        values = {
            lang: loc.get("stringUnit", {}).get("value", "") for lang, loc in localizations.items()
        }
        if not values:
            values = {default_language: key}
        for language, value in values.items():
            for offset, part in enumerate(str(value).split("\n")):
                if has_letters(part):
                    found.append(
                        PatientString(
                            path, line + offset, part, language_of(part, language[:2]), kind
                        )
                    )
    return found


_TS_TAG = re.compile(r"//\s*@patient\b(?:\s+(line|phrase|headline|action)\b)?", re.IGNORECASE)
_TS_EXEMPT = re.compile(r"//\s*plain-words\s*:", re.IGNORECASE)
_TS_LITERAL = re.compile(
    r'"((?:[^"\\\n]|\\.)*)"'  # "double quoted"
    r"|'((?:[^'\\\n]|\\.)*)'"  # 'single quoted'
    r"|`((?:[^`\\$]|\\.|\$(?!\{))*)`"  # `template` with no ${…}
)
_TS_OPEN = "([{"
_TS_CLOSE = ")]}"


def _ts_code(line: str) -> str:
    """The line with its trailing `//` comment removed — a `//` inside a string literal stays."""
    without = _TS_LITERAL.sub(lambda m: " " * len(m.group(0)), line)
    cut = without.find("//")
    return line if cut < 0 else line[:cut]


def _ts_depth(code: str) -> int:
    """How many brackets the code opens and does not close, with string literals blanked."""
    blanked = _TS_LITERAL.sub(lambda m: " " * len(m.group(0)), code)
    return sum(blanked.count(c) for c in _TS_OPEN) - sum(blanked.count(c) for c in _TS_CLOSE)


def _ts_literals(code: str) -> Iterator[str]:
    for match in _TS_LITERAL.finditer(code):
        text = next(g for g in match.groups() if g is not None)
        yield text.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def strings_in_typescript(path: Path, source: str | None = None) -> list[PatientString]:
    """Every patient string in one TypeScript strings file, one per line of text.

    `// @patient [kind]` on a line of its own tags the statement that starts on the next
    line — up to and including the line where its brackets close — so one tag over a
    property covers a string, an array of lines, or a nested object. The same comment at
    the end of a code line tags that line alone. The language is the file's stem when it is
    one Nura speaks (`ms.ts`), else English; Chinese is always recognised by its script.
    """
    text = source if source is not None else path.read_text(encoding="utf-8")
    file_language = path.stem if path.stem in LANGUAGE_CODES else "en"
    lines = text.splitlines()
    found: list[PatientString] = []
    seen: set[tuple[int, str]] = set()

    def take(number: int, line: str, kind: Kind) -> None:
        exempt = _TS_EXEMPT.search(line) is not None
        for literal in _ts_literals(_ts_code(line)):
            if not has_letters(literal) or is_code_token(literal):
                continue
            for part in literal.replace("\r", "").split("\n"):
                part = part.strip()
                if not has_letters(part) or (number, part) in seen:
                    continue
                seen.add((number, part))
                found.append(
                    PatientString(
                        path, number, part, language_of(part, file_language), kind, exempt
                    )
                )

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        tag = _TS_TAG.match(stripped)
        if tag:  # a tag on its own line: the statement starting on the next line
            kind = _tag_kind(tag.group(1))
            index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            depth = 0
            while index < len(lines):
                depth += _ts_depth(_ts_code(lines[index]))
                take(index + 1, lines[index], kind)
                index += 1
                if depth <= 0:
                    break
            continue
        trailing = _TS_TAG.search(line)
        in_comment = stripped.startswith(("*", "/*", "//"))
        if trailing and not in_comment and _ts_code(line).strip():  # a tag ending a code line
            take(index + 1, line, _tag_kind(trailing.group(1)))
        index += 1
    return found


def strings_in(path: Path) -> list[PatientString]:
    if path.suffix == ".py":
        return strings_in_python(path)
    if path.suffix == ".xcstrings":
        return strings_in_xcstrings(path)
    if path.suffix == ".ts":
        return strings_in_typescript(path)
    text = path.read_text(encoding="utf-8")
    return [
        PatientString(path, number, line, language_of(line), "line")
        for number, line in enumerate(text.splitlines(), 1)
        if has_letters(line)
    ]


# --- the repository ----------------------------------------------------------------------------


def repo_root(start: Path | None = None) -> Path:
    """The directory holding `.claude/rules/patient-strings.md`, from here upwards."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / RULES_FILE).is_file():
            return candidate
    raise FileNotFoundError(f"no {RULES_FILE} above {here}")


def patient_paths(rules_text: str) -> list[str]:
    """The `paths:` list in the rules file's front matter."""
    match = re.match(r"^---\n(.*?)\n---", rules_text, re.DOTALL)
    if not match:
        return []
    paths: list[str] = []
    in_paths = False
    for raw in match.group(1).splitlines():
        if re.match(r"^paths\s*:", raw):
            in_paths = True
            continue
        if in_paths and re.match(r"^\s+-\s+", raw):
            paths.append(raw.split("-", 1)[1].strip().strip("\"'"))
        elif in_paths and raw.strip() and not raw.startswith(" "):
            in_paths = False
    return paths


def patient_files(root: Path) -> list[Path]:
    """Every file under the rules file's paths that the verifier knows how to read."""
    files: set[Path] = set()
    for pattern in patient_paths((root / RULES_FILE).read_text(encoding="utf-8")):
        base = root / pattern.split("*", 1)[0].rstrip("/")
        if base.is_file():
            files.add(base)
        elif base.is_dir():
            files.update(
                p
                for p in base.rglob("*")
                if p.suffix in (".py", ".xcstrings", ".ts") and p.is_file()
            )
    return sorted(files)


def check_strings(strings: Iterable[PatientString], root: Path | None = None) -> Report:
    report = Report()
    paths: set[Path] = set()
    for found in strings:
        paths.add(found.path)
        if found.exempt:
            report.exempt += 1
            continue
        report.strings += 1
        shown = (
            found.path.relative_to(root).as_posix()
            if root and found.path.is_relative_to(root)
            else str(found.path)
        )
        for finding in verify(found.text, found.language, found.kind):
            report.findings.append(
                Finding(
                    finding.rule,
                    finding.problem,
                    finding.rewrite,
                    finding.text,
                    finding.severity,
                    finding.language,
                    finding.kind,
                    shown,
                    found.line,
                )
            )
    report.files = len(paths)
    return report


def check_files(paths: Sequence[Path], root: Path | None = None) -> Report:
    return check_strings((s for path in paths for s in strings_in(path)), root)


def check_repo(root: Path | None = None, extra: Sequence[Path] = ()) -> Report:
    """`make plain-words`: every patient string under the rules file's paths, plus `extra`."""
    base = root or repo_root()
    files = [*patient_files(base), *(p.resolve() for p in extra)]
    return check_files(files, base)


# --- the command line --------------------------------------------------------------------------

EXPLANATION = """\
plain-words checks every patient string against docs/plain-words.md. By the doc's rule number:
  1  A whole sentence: a capital, a full stop (or ! ? :), a verb, and it does not stop on a
     verb that needs an object. "A heart doctor explains." fails; "Nura listens." passes.
  2  One idea per line: one sentence, no semicolon. A second idea is a second line.
  3  Short words, short lines: over 10 words is a note, over 15 fails. A word of 4+ syllables
     he would ask about fails; names and EVERYDAY_WORDS are left alone.
  4  His words for things: the glossary's red words fail and the plain phrase is the rewrite.
     A chemical name may stand second to his name for it, never alone.
  5  The day and the date: "14/09", "2026-09-14", "10:00", "UTC", "the 29th", a date with no
     weekday, "Sept" and "Mon" all fail. Say "Monday 29 September", "Thursday at 10".
  6  What to do, and when: an action card that tells him to do something says when.
  7  Who does the next thing: an action card names who. "Ash will book it."
  8  Answer the question he would ask — the reviewer's, not the verifier's.
  9  The small reassurance — the reviewer's.
  10 Numbers as digits, small and few: "ten" fails ("one" is allowed); over 3 numbers fail.
  11 Never a red word: missed, failed, overdue, non-compliant.
  12 Nothing to decode: dose, recheck, follow-up, flag, log; abbreviations in capitals (OK and
     IC are his); units he does not use (mg, mmHg, mmol/L); any id, phone number, IC number.
  13 The same words every time: "the log", "the readings", "discharge summary", "the clinic".
  14 The boundary: no line starts, stops or changes a medicine — a treatment verb beside a
     medicine noun fails unless the line asks the doctor, or says "Do not stop {medicine}
     yourself." and nothing more (en, ms and zh alike).
Kinds: line (default), phrase (fills a slot: rules 1-3 line checks skipped), headline, action.
Languages: en gets every rule; ms and zh get the glossary's chemical names, dates and times,
abbreviations, units, identifiers, one idea per line and the line's ending.
Tags: `# @patient [kind]` before a statement or at the end of its line; `\"\"\"@patient [kind] ...\"\"\"`
after an assignment. In an .xcstrings catalogue, a comment beginning `patient [kind]`. In a
web strings file (.ts), `// @patient [kind]` above a property or at the end of its line.
`# plain-words: <reason>` on the line a literal starts exempts it: history that is shown no more.
Fillers: {name} → Ash, {doctor} → Dr Tan, {date} → Monday 14 September, {count} → 2.
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plain-words", description="Check patient strings against docs/plain-words.md."
    )
    parser.add_argument(
        "files", nargs="*", type=Path, help="files to check as well as the rules file's paths"
    )
    parser.add_argument(
        "--only", action="store_true", help="check only the files given, not the rules file's paths"
    )
    parser.add_argument("--text", help="check this text instead of files")
    parser.add_argument(
        "--lang", default="en", choices=LANGUAGE_CODES, help="the language of --text"
    )
    parser.add_argument("--kind", default="line", choices=KINDS, help="how to read --text")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--explain", action="store_true", help="say what each rule checks")
    parser.add_argument("--quiet-notes", action="store_true", help="do not print notes")
    args = parser.parse_args(argv)

    if args.explain:
        print(EXPLANATION, end="")
        return 0
    if args.text is not None:
        report = Report(strings=1, files=0, findings=verify(args.text, args.lang, args.kind))
    elif args.only:
        report = check_files(args.files)
    else:
        report = check_repo(extra=args.files)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "strings": report.strings,
                    "files": report.files,
                    "failures": [asdict(f) for f in report.failures],
                    "notes": [asdict(f) for f in report.notes],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for finding in report.findings:
            if finding.severity == "note" and args.quiet_notes:
                continue
            print(finding)
            if args.text is not None:
                print(f"    {finding.text}")
        print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
