"""`ClaudeAsker` (`NURA_ASKER=claude`, demo-only): Ask as an agent.

Where `RuleBasedAsker` (`app.search.asker`, wrapping `app.search.ask.recall_stream`) reads
every part of the record its key opens and picks lines with keyword search, `ClaudeAsker`
decides for itself, question by question, which parts are worth opening — and its trace is
the model's own real tool calls, one `AskStep` per call, streamed the instant the call
actually runs. Nothing here is scripted or delayed for effect (docs/design-direction.md
"Conversation, waiting and thinking"): a step is yielded only when the read behind it has
already happened.

The tools are the same audited, scope-checked reads `recall_stream`'s own corpus-builder
(`app.search.ask._corpus_stream`) uses — `read_medicines`, `read_readings`, `read_visits`,
`read_records`, `read_feelings`, plus `search_online` (the allowlisted web,
`app.delivery.feed.claude_adapters.ClaudeSearcher`) — and `read_waiting_papers`
(`app.search.ask.waiting_papers`): a paper he has added but not yet said yes to is his own
information too — its kind, the date printed on it, and when he added it — never a value on
it (never even a `ReviewField`, so there is no free text to leak in the first place), which
stays behind the review screen until his own yes closes the card.
A tool for a scope this key does not hold is never offered to the model at all: a withheld
part cannot even be named, the same rule `_corpus_stream` holds by never reading it. Every
tool's result is plain lines already in his own words, each carrying its own id — never a row,
never a raw value the model could restate past what is written down. A dated line also carries
its own elapsed phrase, already computed (`app.search.elapsed`): "how long ago" is never the
model's arithmetic.

The answer reads as a natural, warm reply — two to four flowing sentences that answer the
question first, never a fact dump — because the prompt asks for that voice, not because the
gate is looser: every surviving line still passes the plain-words verifier, at Ask's own
profile (`docs/plain-words.md`, `app.safety.plain_words.Kind` `"ask"`), which relaxes only the
one-idea rule and raises the length ceiling from fifteen words to twenty — rule 14, the
boundary, is exactly as strict as everywhere else. Every line is also cited only to ids a tool
actually returned this ask; a boundary line, always the catalogue's own for the reader's
language, whatever the model wrote (`app.safety.boundary.boundary_lines`) — the model is never
trusted with that line itself. Every surviving line also passes the same conclusion-and-advice
blocklist `app.llm.narrate.ClaudeNarrator` holds every rephrase to, is checked for caregiver
voice the same way (`app.channels.about_him.Reader`), and is checked for an elapsed phrase the
model invented or reached for vaguely rather than copied (`_elapsed_claim`). A line that cites
an unconfirmed review card at all is checked, after removing every date and elapsed phrase this
ask actually rendered for that card, for a bare digit, a Chinese numeral run, or an en/ms
number word — the shape of a value, wherever it came from
(`_claims_a_value_from_an_unconfirmed_card`): belt and braces over `WaitingPaper`'s own refusal
to carry one at all, not a claim that this or any check reads and understands arbitrary prose.
A line that fails any of these, and cannot be repaired (below), is dropped; a cite outside this
ask's own tool results is dropped from its line; a line with nothing left to cite is dropped.

A dropped line is never just silently missing from the middle of the answer, either: if the
model's own first (lead) line is the one dropped, or a surviving line opens as though
answering one that is no longer there ("However…", "What … do hold…"), the survivors do not
stand alone as an answer — one whole-answer repair round asks the model to rewrite the whole
thing so it does, before anything is shown (`_parse_answer`'s `lead_dropped`/`dangling`,
`_whole_answer_repair_message`). If nothing survives at all — or that whole-answer repair also
comes back incoherent, or the call refuses, times out, runs past `MAX_ROUNDS`, or answers
something that does not parse — the answer is the rule-based asker's own answer for the same
question: the stream never ends without one, and never with a partial.

Streamed sentence by sentence: each line of the finished, already-checked answer is sent as
its own `AnswerDelta` (`app.search.asker`), text and cites together, in the order it will
appear — the wire's own `answer_sentence` event (`app.channels.api.timeline`). The model call
itself is not token-streamed (`output_config`'s structured JSON, and a tool-use round would
make token streaming meaningless mid-call anyway); a sentence is "streamed" the instant the
whole checked answer is ready, never held back for effect. `RuleBasedAsker` (`app.search.
asker`) holds the same contract — it replays `recall_stream`'s own already-composed, already-
verified lines the same way — so a caller never has to know which asker it is holding.

Demo only (ADR 0017), the same story `app.llm.narrate.ClaudeNarrator`'s module docstring
tells: Anthropic's first-party API does not process in SG or MY, so this adapter may only be
built where every word it is shown is demo or test data (`app.search.asker_provider.
asker_for`, gated by `app.llm.residency.allow_external_model`).
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Final

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_read
from app.audit.models import Action
from app.audit.trail import record as record_audit
from app.channels.about_him import Reader, reader_of
from app.db import as_utc, utcnow
from app.delivery.feed.compress import Searcher
from app.delivery.feed.sources import usable_sources
from app.delivery.timeline_strings import WHAT, day_of, honest_lines, reroute_lines, verified
from app.drugs.registry import DrugRegistry
from app.ingestion.objects import ObjectStore
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.insurance.ledger import insurance_ledger
from app.insurance.policy import current_policies
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.llm.call_counter import record_call
from app.llm.models import DEFAULT_MODELS, Task
from app.llm.narrate import _has_conclusion_language
from app.llm.prompts import load_prompt
from app.medicines.models import MedicationLine
from app.medicines.strings import say_date
from app.memory.models import Appointment, AppointmentStatus, Provider
from app.memory.spine import UPCOMING
from app.memory.timeline import language_for
from app.reasoning.feelings.service import recent_notes
from app.reasoning.visits.planner import propose_visits
from app.safety.boundary import Surface, boundary_lines
from app.safety.plain_words import _MEDICINE_NOUNS, Finding, verify
from app.safety.red_flags import detect
from app.search.ask import (
    _LATIN_WORD,
    ASK_TARGET,
    CHANGE_WORDS,
    CHANGE_WORDS_ZH,
    MEDICINE_WORDS,
    QUESTION_LENGTH,
    TEXT_LINES,
    Answer,
    AnswerLine,
    AskStep,
    Cite,
    Clarify,
    ClarifyOption,
    Mode,
    NotAQuestion,
    Proposal,
    _clarify_option_label,
    _facts_under,
    _is_reading,
    _keep_question,
    _plain_name,
    recall,
    waiting_papers,
)
from app.search.asker import AnswerDelta
from app.search.conversation import ConversationMemory
from app.search.elapsed import elapsed_phrase
from app.search.retrieve import Retriever

log = logging.getLogger("nura.llm.ask_agent")

MODEL: Final = DEFAULT_MODELS[Task.ASK]
"""The default `ClaudeAsker` is built with when a caller does not pass `model=` (a test,
mainly — `asker_for` always does). Opus 5: Ask decides for itself what to look at and answers
him directly, so quality and safety matter most here, the same as reading a paper."""
MAX_TOKENS: Final = 4096
MAX_ROUNDS: Final = 6
"""A round is one call and its response. A question this build cannot settle in six never
hangs — it falls back to the rule-based answer, the same clean ending a refusal falls back
to."""

TOOL_SCOPES: Final[dict[str, Scope]] = {
    "read_medicines": Scope.MEDICINES,
    "read_readings": Scope.READINGS,
    "read_visits": Scope.VISITS,
    "read_records": Scope.RECORDS,
    "read_feelings": Scope.RECORDS,
    "read_insurance": Scope.MONEY,
    "read_costs": Scope.MONEY,
    "read_plan": Scope.VISITS,
    "read_waiting_papers": Scope.RECORDS,
}
"""Which scope a tool's read rests on — the same scope `_corpus_stream` checks before it ever
reads that part. A key that does not hold it is never offered the tool at all. `read_insurance`
and `read_costs` rest on `Scope.MONEY`, the door `app.insurance.policy` and
`app.insurance.ledger` already stand behind — the owner, a steward, or the chief his family
named, never a caregiver or a viewer (W2 grounding: an insurance or cost question is never
answered for a key that cannot already see the policy or the ledger itself)."""

TOOL_STEP_KEYS: Final[dict[str, str]] = {
    "read_medicines": "medicines",
    "read_readings": "readings",
    "read_visits": "visits",
    "read_records": "records",
    "read_feelings": "feelings",
    "search_online": "search_online",
    "read_insurance": "insurance",
    "read_costs": "costs",
    "read_plan": "plan",
    "propose_action": "plan",
    "read_waiting_papers": "waiting_papers",
}
"""A tool call's `AskStep` key, into `app.delivery.timeline_strings.ASK_STEPS`/`_THEIRS` — the
same catalogue `recall_stream`'s own steps use, so the trace looks the same however it was
built."""

_TOOL_DEFS: Final[dict[str, dict[str, Any]]] = {
    "read_medicines": {
        "name": "read_medicines",
        "description": "His current medicines: each line, its own name and who prescribed it.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_readings": {
        "name": "read_readings",
        "description": "His blood pressure readings and other measurements he or his family "
        "keep, most recent first.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_visits": {
        "name": "read_visits",
        "description": "His doctor visits, past and coming, with who and when.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_records": {
        "name": "read_records",
        "description": "Facts and papers written to his record outside a visit or a reading "
        "(a discharge letter, a lab result, a note kept about him).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_waiting_papers": {
        "name": "read_waiting_papers",
        "description": "Papers he has added but not yet checked and said yes to — never what "
        "is on them, only that one exists: its kind, the date printed on it, and when it was "
        "added. Use this when a question could be about a paper that may still be waiting, "
        "so you can say it is waiting instead of saying nothing is written down.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_feelings": {
        "name": "read_feelings",
        "description": "What he last said he felt, and the note it became for the doctor.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "search_online": {
        "name": "search_online",
        "description": "The allowlisted public health web (regulators, ministries, hospital "
        "groups) for a general question the record itself does not answer.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look for."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "read_insurance": {
        "name": "read_insurance",
        "description": "His insurance policies in force: insurer, type, and what each covers "
        "as he or his chief wrote it down. Nothing here decides what is covered — only what "
        "the policy's own words say.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_costs": {
        "name": "read_costs",
        "description": "What he has actually paid or claimed before, by visit and policy — "
        "the only cost record this key can read. Never a public price list.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_plan": {
        "name": "read_plan",
        "description": "His visits already on the calendar, and the visits Nura proposes but "
        "has not booked — each with why it was proposed.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "propose_action": {
        "name": "propose_action",
        "description": "Offer the reader a next step to confirm for himself — adding a "
        "question to a coming visit, drafting a message to a provider, or booking a follow-up. "
        "This never happens by itself: it only ever produces something he must still say yes "
        "to, through the app's own confirm step. Call it at most once per question, only when "
        "a concrete next step is obvious from what was just read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["add_to_visit", "message_provider", "book_follow_up"],
                },
                "label": {
                    "type": "string",
                    "description": "The pill's own words, plain, short, an action he takes "
                    "(e.g. 'Add to Thursday's questions').",
                },
            },
            "required": ["kind", "label"],
            "additionalProperties": False,
        },
    },
}

def _boundary_rewrite(text: str, language: str) -> str | None:
    """Rule 14's one deterministic rewrite (`docs/plain-words.md` 14, `_check_boundary`): a
    line that only crosses the boundary — a treatment verb beside a medicine noun, and
    nothing else wrong with it — is turned into a question for the doctor, the same shape
    the verifier's own suggestion already names ('a question for the doctor: "Ask Dr Tan
    about the new amount of the water pill."'), instead of being thrown away outright
    (defect: every line the model wrote about a medicine dropped, repair round included, and
    the reader heard nothing). The medicine named is whichever of `_MEDICINE_NOUNS` the
    offending line already named — never a chemical name, never invented. `None` when the
    line does not actually name one (should not happen: `_check_boundary` only ever fires
    when it does), so the caller still falls back to dropping the line."""
    nouns = _MEDICINE_NOUNS.get(language, _MEDICINE_NOUNS["en"])
    found = nouns.search(text)
    if found is None:
        return None
    medicine = found.group()
    if language == "zh":
        return f"问一问医生关于{medicine}的事。"
    if language == "ms":
        return f"Tanya doktor anda tentang {medicine}."
    article = "" if medicine[:1].isupper() else "the "
    return f"Ask your doctor about {article}{medicine}."

ANSWER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines", "boundary"],
    "properties": {
        "lines": {
            "type": "array",
            "description": "Two to four sentences, in order, that together read as one "
            "natural, conversational answer, the question answered first — never a list of "
            "disconnected facts, never what a number means, never advice.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "cites"],
                "properties": {
                    "text": {"type": "string"},
                    "cites": {
                        "type": "array",
                        "description": "The ids (from tool results only) this line rests on.",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "boundary": {
            "type": "string",
            "description": "Handing anything beyond the record to his doctor. Never shown as "
            "written; the app says this itself.",
        },
        "clarify": {
            "type": ["object", "null"],
            "description": "Propose ONE clarifying question instead of answering — only when "
            "the question genuinely cannot be answered without a choice he must make (an "
            "ambiguous referent with 2+ real candidates in what you read this ask, a missing "
            "required detail, a pronoun with no antecedent). Leave 'lines' empty when you "
            "propose this. Never propose this twice in a row about the same thing, and never "
            "for a red-flag/emergency message.",
            "additionalProperties": False,
            "required": ["referent_class", "candidate_ids", "question"],
            "properties": {
                "referent_class": {
                    "type": "string",
                    "description": "What kind of choice this is, e.g. 'which_test', "
                    "'which_medicine', 'which_visit', 'which_paper', 'missing_parameter'.",
                },
                "candidate_ids": {
                    "type": "array",
                    "description": "2 to 4 of the tools' own short ids, the real candidates — "
                    "empty when the question is missing a detail no tool result can list "
                    "(a free-text reply is expected instead).",
                    "items": {"type": "string"},
                },
                "question": {
                    "type": "string",
                    "description": "One short, warm, natural sentence — never 'Please "
                    "specify', never a numbered menu, never two questions.",
                },
            },
        },
    },
}

_SYSTEM_PROMPT: Final = load_prompt("ask_agent")


@dataclass
class _ToolLine:
    """One line a tool gave back, and the `Cite` it stands for if the model names its id."""

    token: str
    text: str
    cite: Cite
    label: str | None = None
    """A clarifying question's own option label for this line, built here alone from
    confirmed data (W2) — never the model's words. `None` for a kind that never stands as a
    clarify candidate (a web result, a proposal, an insurance line): a clarify proposal naming
    one of those ids is dropped, the same as any other bad proposal."""
    label_safe: frozenset[str] = frozenset()
    """Every substring of `label` that is safe to carry a digit — the backend's own rendered
    date/elapsed phrase, or (a medicine) the licensed register's own generic name and strength
    — because this module built it, never an extractor or a hostile free-text field. Checked
    by `_parse_clarify` (review B2/B6): with these removed, nothing safe to say a number in
    remains, so any digit left in the label is not the backend's own."""


_TOKEN_PREFIXES: Final[dict[str, str]] = {
    "medication_line": "m",
    "fact": "f",
    "appointment": "v",
    "feeling_note": "g",
    "web": "w",
    "policy": "p",
    "claim": "c",
    "plan": "n",
    "proposal": "x",
    "review_card": "r",
}
"""One letter per kind, for `_TokenCounter` — never the uuid itself. A model given `m1` and
`v2` to cite back can actually copy them; one given a raw uuid to retype byte for byte
regularly could not, and its whole line was dropped for a cite that matched nothing."""


class _TokenCounter:
    """Short, stable ids for this ask alone: one running number per kind (`m1`, `m2`, `v1`,
    ...), reset fresh for every `ask_stream` call. Never persisted, never shown to the reader —
    only ever cited back by the model, and matched back to a `Cite` by `known`."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def next(self, kind: str) -> str:
        prefix = _TOKEN_PREFIXES.get(kind, (kind[:1] or "x"))
        n = self._seen.get(prefix, 0) + 1
        self._seen[prefix] = n
        return f"{prefix}{n}"


_INVISIBLE_RANGES: Final = (
    (0x200B, 0x200F),  # zero-width space through right-to-left mark
    (0x202A, 0x202E),  # left-to-right/right-to-left embedding and override
    (0x2060, 0x2069),  # word joiner and the directional isolates
    (0xFEFF, 0xFEFF),  # zero-width no-break space / byte-order mark
)
_CONTROL_CHARS: Final = re.compile(
    # The ASCII controls and the newline family — including the three Unicode line terminators
    # a "\n"-only strip misses: NEL (U+0085), LINE SEPARATOR (U+2028), PARAGRAPH SEPARATOR
    # (U+2029). Third review pass: with those kept, the round-1 forgery survived byte for byte.
    "[\r\n\t\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x85\u2028\u2029"
    + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _INVISIBLE_RANGES)
    + "]+"
)
"""A tool line is data about his record read back to the model, never an instruction — but a
free-text field (a note, a provider's name, a label typed on a review card) is his or a
family member's words, or an extractor's read of an arbitrary uploaded page, not a value this
adapter controls (review defect #2: a hostile page's text carrying a newline could forge what
looked like a second "r2: ..." tool line, or a line that reads like a new instruction). Beyond
the ASCII control characters and the usual newline family, this also strips the zero-width and
bidi-override characters (U+200B-U+200F, U+202A-U+202E, U+2060-U+2069, U+FEFF/BOM) a hostile
page could use to hide or reorder text past a human reviewer while still reading as plain
characters to code that does not special-case them. Every line goes through `_register`, the
one place a tool result is built, so this is stripped once, for every tool, not per field."""

_FORGED_ID = re.compile(r"\b[a-z]{1,2}\d+:", re.IGNORECASE)
"""A free-text field's value cannot forge a second tool-result line by starting with something
that reads like this ask's own short-id shape (`_TokenCounter`, "m1:", "r2:") — only the colon
is dropped, so the token stays as harmless text (review defect #2, second pass: a hostile
"facility" value naming a fake "r2:" survived control-character stripping once newlines alone
were collapsed to spaces, since "r2:" mid-line still read as a plausible second citable line).
Never applied to the line's own genuine leading token, which `_register` adds after this runs."""


def _sanitize_free_text(text: str) -> str:
    """The one place a free-text field is made safe to carry anywhere in this module — a tool
    line (`_register`), a clarifying question, or an option label (review B2/B6): the same
    control-character strip and forged-id neutraliser, applied once here so neither a
    clarifying question nor a label can carry what a tool line already could not — a hostile
    provider name or a hostile page's text hiding a bidi override, a line-separator forging a
    second line, or a forged short-id colon."""
    clean = _CONTROL_CHARS.sub(" ", text).strip()
    return _FORGED_ID.sub(lambda match: match.group()[:-1], clean)


def _register(
    lines: list[_ToolLine],
    counter: _TokenCounter,
    kind: str,
    id_: uuid.UUID,
    text: str,
    *,
    label: str | None = None,
    label_safe: frozenset[str] = frozenset(),
) -> str:
    token = counter.next(kind)
    clean = _sanitize_free_text(text)
    lines.append(
        _ToolLine(
            token=token,
            text=f"{token}: {clean}",
            cite=Cite(kind=kind, id=id_),
            label=label,
            label_safe=label_safe,
        )
    )
    return token


def _today(context: KeyContext) -> date:
    """Now, on his own clock (`app.db.utcnow`, honouring a frozen clock exactly as every
    other timestamp in this app does), read on his region's calendar — never
    `datetime.now()`, and never the model's own idea of "today"."""
    return day_of(utcnow(), context.region)


def _elapsed(context: KeyContext, language: str, moment: date, seen: set[str]) -> str:
    """The elapsed phrase for a dated tool line (fix: "how long ago" is computed here, never
    guessed by the model mid-answer — `app.search.elapsed`). `seen` collects every phrase
    handed out this ask, so a line that invents its own ("about 5 years ago" when nothing this
    ask read said that) can be told apart from one that copied a phrase actually given
    (`_parse_answer`'s invented-elapsed check)."""
    phrase = elapsed_phrase(_today(context), moment, language)
    seen.add(phrase)
    return phrase


async def _read_medicines(
    session: AsyncSession,
    context: KeyContext,
    registry: DrugRegistry | None,
    language: str,
    counter: _TokenCounter,
    elapsed_seen: set[str],
    reader: Reader,
) -> tuple[list[_ToolLine], int]:
    found = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(MedicationLine.superseded_at.is_(None),),
    )
    lines: list[_ToolLine] = []
    for line in found:
        name = _plain_name(registry, line.generic, language)
        who = f"prescribed by {line.prescriber}" if line.prescriber else "no prescriber written down"
        started_on = day_of(line.started_at, context.region)
        elapsed = _elapsed(context, language, started_on, elapsed_seen)
        label, label_safe = _medicine_clarify_label(line, name, reader, language)
        _register(
            lines,
            counter,
            "medication_line",
            line.id,
            f"{name}, {who}, started {started_on.isoformat()} ({elapsed})",
            label=label,
            label_safe=label_safe,
        )
    return lines, len(found)


_DETERMINER_PREFIXES: Final[dict[str, tuple[str, ...]]] = {
    "en": ("your ", "the "),
    "zh": ("您的", "他的", "她的"),
}
"""`PLAIN_NAME`'s own strings already carry a determiner ("your blood pressure tablet", "the
water pill") — stripped here before a clarify label adds its own, so a caregiver's chip never
doubles it ("Your your blood pressure tablet", review B4). Malay's own plain names are already
bare (no "anda" prefix baked in the way `_plain_names`' suffix-strip in `app.search.ask`
handles the opposite case), so it carries no entry."""


def _bare_plain_name(name: str, language: str) -> str:
    bare = name
    for prefix in _DETERMINER_PREFIXES.get(language, ()):
        if bare.lower().startswith(prefix.lower()):
            bare = bare[len(prefix) :]
            break
    return bare.removesuffix(" anda").strip()


def _medicine_clarify_label(
    line: MedicationLine, plain_name: str, reader: Reader, language: str
) -> tuple[str, frozenset[str]]:
    """A medicine's own clarify-option label (W2): the plain name, in caregiver voice, never a
    doubled determiner (review B4 — `PLAIN_NAME` already carries its own "your"/"the", so this
    strips it and rebuilds with the right one for this reader) — then always the licensed
    register's own generic name and strength, small and second (plain-words rule 4: his word
    first, the chemical name second), because his own list can hold two medicines under the
    very same plain word (two blood-pressure tablets) and a chip that cannot tell them apart is
    worse than one that names the chemical once. `detail` (never free text — `line.generic` and
    `line.strength` are the registry's own match, columns on his confirmed medication line, the
    same source `MedicineRefOut` already shows him) is returned as the one substring this label
    may carry a digit in."""
    bare = _bare_plain_name(plain_name, language)
    strength = (line.strength or "").strip()
    detail = f"{line.generic} {strength}".strip() if strength else line.generic
    if language == "zh":
        subject = "您的" if reader.his else f"{reader.name or '他'}的"
        label = f"{subject}{bare}（{detail}）"
    elif language == "ms":
        who = "anda" if reader.his else (reader.name or "pesakit")
        label = f"{bare} {who} ({detail})"
    else:
        subject = "Your" if reader.his else f"{reader.name or 'the patient'}'s"
        label = f"{subject} {bare} ({detail})"
    return label, frozenset({detail})


def _dated_clarify_label(
    what: str, on: date, language: str, reader: Reader
) -> tuple[str, frozenset[str]]:
    """A test/paper/visit's own clarify-option label (W2): its plain word, and the said-date
    of it, in caregiver voice — the same shape `app.search.ask._clarify_option_label` builds
    for the rule-based asker, so a chip reads the same whichever asker offered it. `what` is
    sanitised the same way any other free-text field this module reads is (review B2/B6 — a
    visit's own label embeds a provider's typed name), and the said-date is the one substring
    this label may carry a digit in."""
    said = say_date(on, language)
    clean_what = _short_words(_sanitize_free_text(what), CLARIFY_FREE_TEXT_LENGTH)
    return _clarify_option_label(clean_what, said, language, reader), frozenset({said})


CLARIFY_FREE_TEXT_LENGTH: Final = 48
"""How much of a free-text name (a provider he or his family typed, or accepted from a calendar)
a choice may carry. The cap is on THIS part alone, before the backend's own said-date is added
(re-review of #311, N1): capping the finished label instead cut the date off the chip ("…of
Saturday", no day) or left a digit of it outside the safe substring, which silently dropped
the whole question for an ordinary long clinic name."""


def _short_words(text: str, limit: int) -> str:
    """`text` whole if it fits, else cut at a word boundary with an ellipsis — never mid-word,
    and never into anything the backend itself wrote after it."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") or text[: limit - 1]
    return f"{cut}…"


async def _read_readings(
    session: AsyncSession,
    context: KeyContext,
    language: str,
    counter: _TokenCounter,
    elapsed_seen: set[str],
    reader: Reader,
) -> tuple[list[_ToolLine], int]:
    facts = await _facts_under(session, context, Scope.READINGS)
    lines: list[_ToolLine] = []
    for fact in facts:
        on = day_of(fact.valid_from, context.region)
        elapsed = _elapsed(context, language, on, elapsed_seen)
        if _is_reading(fact):
            value = fact.value
            text = f"blood pressure {value['systolic']}/{value['diastolic']} on {on.isoformat()} ({elapsed})"
            catalogue_word: str | None = WHAT[language].get("blood_pressure")
        else:
            text = f"{fact.subject} {fact.attribute} = {fact.value} on {on.isoformat()} ({elapsed})"
            # Review B3: the raw subject is an extractor-written code (validated only as
            # `^[a-z][a-z0-9_]{0,63}$` — it may itself contain digits, "sugar_11_4"), never
            # shown as a label. Only a real, closed-catalogue word for it may be offered as a
            # clarify candidate at all; a subject this table does not know gets no label.
            catalogue_word = WHAT[language].get(str(fact.subject))
        label: str | None = None
        label_safe: frozenset[str] = frozenset()
        if catalogue_word is not None:
            label, label_safe = _dated_clarify_label(catalogue_word, on, language, reader)
        _register(
            lines, counter, "fact", fact.id, text, label=label, label_safe=label_safe
        )
    return lines, len(facts)


async def _read_visits(
    session: AsyncSession,
    context: KeyContext,
    language: str,
    counter: _TokenCounter,
    elapsed_seen: set[str],
    reader: Reader,
) -> tuple[list[_ToolLine], int, list[Appointment], dict[uuid.UUID, Provider]]:
    providers = {p.id: p for p in await audited_read(session, Provider, context, Scope.VISITS)}
    visits = await audited_read(session, Appointment, context, Scope.VISITS)
    lines: list[_ToolLine] = []
    for visit in visits:
        provider = providers.get(visit.provider_id)
        who = provider.name if provider is not None else "an unnamed provider"
        when = day_of(visit.scheduled_at, context.region)
        elapsed = _elapsed(context, language, when, elapsed_seen)
        text = f"with {who} on {when.isoformat()} ({elapsed}), status {visit.status.value}"
        label, label_safe = _dated_clarify_label(f"visit with {who}", when, language, reader)
        _register(
            lines, counter, "appointment", visit.id, text, label=label, label_safe=label_safe
        )
    return lines, len(visits), list(visits), providers


async def _read_records(
    session: AsyncSession,
    context: KeyContext,
    language: str,
    counter: _TokenCounter,
    elapsed_seen: set[str],
    reader: Reader,
) -> tuple[list[_ToolLine], int]:
    facts = await _facts_under(session, context, Scope.RECORDS)
    lines: list[_ToolLine] = []
    for fact in facts:
        on = day_of(fact.valid_from, context.region)
        elapsed = _elapsed(context, language, on, elapsed_seen)
        # Review B3: only a real, closed-catalogue word for the subject may ever be a clarify
        # candidate's label — never the raw, extractor-written subject code.
        catalogue_word = WHAT[language].get(str(fact.subject))
        label = None
        label_safe: frozenset[str] = frozenset()
        if catalogue_word is not None:
            label, label_safe = _dated_clarify_label(catalogue_word, on, language, reader)
        _register(
            lines,
            counter,
            "fact",
            fact.id,
            f"{fact.subject} {fact.attribute} = {fact.value} on {on.isoformat()} ({elapsed})",
            label=label,
            label_safe=label_safe,
        )
    return lines, len(facts)


def _waiting_clarify_label(kind: str, said: str | None, language: str) -> tuple[str, frozenset[str]]:
    """The one shape a waiting paper's clarify-option label may ever take (W2, review defect
    #1's own rule carried into clarifying questions): the closed-catalogue kind word, the
    backend's own said-date, and "not yet checked" — never anything an extractor read off the
    page, never a number beyond the date itself."""
    if language == "zh":
        label = f"{said}的{kind}，还没检查" if said else f"{kind}，还没检查"
    elif language == "ms":
        label = f"{kind} bertarikh {said}, belum disemak" if said else f"{kind}, belum disemak"
    else:
        label = f"{kind} of {said}, not yet checked" if said else f"{kind}, not yet checked"
    return label, frozenset({said}) if said else frozenset()


async def _read_waiting_papers(
    session: AsyncSession,
    context: KeyContext,
    language: str,
    counter: _TokenCounter,
    elapsed_seen: set[str],
    card_safe_text: dict[uuid.UUID, set[str]],
) -> tuple[list[_ToolLine], int]:
    """A paper he has added but not yet checked (fix 2, this module's docstring): only the
    three things safe to say before his yes — the closed-catalogue kind word, the sanity-
    checked printed date (`app.search.ask.MAX_PAPER_AGE_YEARS`), and when it was added — never
    an extracted value, unit, range or facility name (review defect #1: `WaitingPaper` reads
    no `ReviewField` at all, so there is no free text left here to leak in the first place).

    The printed date is handed over already in words (`say_date`, not the ISO form) — the same
    "the backend computes it, the model copies it" rule the elapsed phrase already holds, so
    the model never has to work out a weekday from an ISO date either. `card_safe_text` collects
    every date/elapsed string actually rendered for each card this ask, so a later check
    (`_claims_a_value_from_an_unconfirmed_card`) can tell his own written-down date apart from
    a value the model invented."""
    found = await waiting_papers(session, context, language=language)
    lines: list[_ToolLine] = []
    for paper in found:
        safe: set[str] = set()
        said: str | None = None
        if paper.document_date is not None:
            said = say_date(paper.document_date, language)
            doc_elapsed = _elapsed(context, language, paper.document_date, elapsed_seen)
            safe.add(said)
            # Never the bare year: `say_date` says no year (plain words rule 5), and with it in
            # the safe set "Your sugar was 2026." passed (third review pass, note C).
            safe.add(doc_elapsed)
            dated = f", dated {said} ({doc_elapsed})"
        else:
            dated = ""
        added = _elapsed(context, language, day_of(paper.added_at, context.region), elapsed_seen)
        safe.add(added)
        card_safe_text[paper.card_id] = safe
        text = f"{paper.kind}{dated}, added {added}, not yet checked"
        label, label_safe = _waiting_clarify_label(paper.kind, said, language)
        _register(
            lines,
            counter,
            "review_card",
            paper.card_id,
            text,
            label=label,
            label_safe=label_safe,
        )
    return lines, len(found)


async def _read_feelings(
    session: AsyncSession, context: KeyContext, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    notes, _withheld = await recent_notes(session, context=context)
    lines: list[_ToolLine] = []
    for note in notes:
        date = day_of(note.created_at, context.region).isoformat()
        said = " ".join(note.lines) if note.lines else note.headline
        _register(
            lines,
            counter,
            "feeling_note",
            note.id,
            f"he said he felt {note.word.value} on {date}: {said}",
        )
    return lines, len(notes)


async def _search_online(
    session: AsyncSession,
    context: KeyContext,
    searcher: Searcher,
    query: str,
    counter: _TokenCounter,
) -> tuple[list[_ToolLine], int]:
    sources = await usable_sources(session, region=context.region)
    domains = [source.domain for source in sources]
    if not domains or not query.strip():
        return [], 0
    found = await asyncio.to_thread(searcher.find, [query], domains)
    lines: list[_ToolLine] = []
    for result in found:
        synthetic = uuid.uuid5(uuid.NAMESPACE_URL, result.url)
        text = f"{result.title} — {result.url} ({result.domain})"
        _register(lines, counter, "web", synthetic, text)
    return lines, len(found)


async def _read_insurance(
    session: AsyncSession, context: KeyContext, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    """His policies in force, each cited to itself: what the policy's own words say it
    covers, nothing Nura decided (`app.insurance.policy`, "the owner's decision, written
    down")."""
    policies = await current_policies(session, context=context)
    lines: list[_ToolLine] = []
    for policy in policies:
        covers = policy.covers or "nothing written down about what it covers"
        text = (
            f"{policy.insurer_name}, {policy.policy_type.value.replace('_', ' ')}, "
            f"status {policy.status.value}, covers: {covers}"
        )
        _register(lines, counter, "policy", policy.id, text)
    return lines, len(policies)


async def _read_costs(
    session: AsyncSession, context: KeyContext, language: str, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    """What he has actually paid or claimed, by visit — his own ledger
    (`app.insurance.ledger`), never a public price list: this build carries no cost-expectation
    module, so a cost question is answered from his own record or not at all."""
    ledger = await insurance_ledger(session, context=context, language=language)
    lines: list[_ToolLine] = []
    for row in ledger.lines:
        amount = row.paid_by_patient_said or row.claimed_amount_said or "no amount written down"
        text = (
            f"{row.visit_purpose} under {row.policy_name} on {row.visit_date_said}: "
            f"{amount}, {row.status_word}"
        )
        _register(lines, counter, "claim", row.claim_id, text)
    return lines, len(ledger.lines)


async def _read_plan(
    session: AsyncSession, context: KeyContext, language: str, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    """The visits Nura proposes but has not booked (`app.reasoning.visits.planner`), each with
    why — never a row of the record it rests on, only the proposal's own plain-words purpose."""
    proposed = await propose_visits(
        session, context=context, language=language, region=context.region
    )
    lines: list[_ToolLine] = []
    for proposal in proposed.proposals:
        synthetic = uuid.uuid5(uuid.NAMESPACE_URL, f"visit-proposal:{proposal.proposal_id}")
        when = (
            day_of(proposal.suggested_at, context.region).isoformat()
            if proposal.suggested_at is not None
            else "no date written down"
        )
        text = f"Nura suggests: {proposal.purpose} (around {when})"
        _register(lines, counter, "plan", synthetic, text)
    return lines, len(proposed.proposals)


async def _propose_action(
    kind: str, label: str, counter: _TokenCounter, proposals: list[Proposal]
) -> tuple[list[_ToolLine], int]:
    """Note a proposal for the reader to confirm himself; never a write, a booking or a send
    by this call (the module docstring's grounding rule). `proposals` is mutated in place —
    the caller attaches it to the final `Answer` only once the answer itself survives every
    check, so a proposal offered mid-loop but dropped along with a refused answer is never
    shown."""
    label = " ".join(label.split())[:120] or "Do this"
    proposals.append(Proposal(kind=kind, label=label))
    lines: list[_ToolLine] = []
    _register(
        lines,
        counter,
        "proposal",
        uuid.uuid4(),
        f"noted: '{label}' will be offered to him to confirm; nothing was written, booked or "
        "sent",
    )
    return lines, 1


def _would_change_treatment(question: str, about_medicine: bool) -> bool:
    """`app.search.ask._would_change_treatment`'s own check, without its `hits`: `about_medicine`
    is true when a surviving line already cites a medicine, the agent's own twin of a keyword
    hit landing on one."""
    low = question.lower()
    latin = set(_LATIN_WORD.findall(low))
    changing = bool(latin & CHANGE_WORDS) or any(word in low for word in CHANGE_WORDS_ZH)
    return changing and (about_medicine or bool(latin & MEDICINE_WORDS) or "药" in low)


def _tools_for(context: KeyContext) -> list[str]:
    names = [name for name, scope in TOOL_SCOPES.items() if context.allows(scope)]
    names.append("search_online")
    names.append("propose_action")
    return names


HISTORY_TURNS: Final = 6
"""How many of the most recent turns `_history_block` writes out in full — the same
`app.search.conversation.KEPT_VERBATIM` the caller's `history` was already built to."""


def _history_block(history: ConversationMemory | None) -> str:
    """Conversation memory (W2), folded into the system prompt rather than the message list:
    the smallest change this file takes to let a follow-up resolve "that" or "it" against
    what was just asked and found. `None`, or a thread with nothing on it yet, adds nothing.
    Never the whole record — only what was already said in this thread."""
    if history is None or (not history.recent and not history.summary and history.resolved_focus is None):
        return ""
    parts = ["\n\nThis is a continuing conversation. Earlier in it:"]
    if history.summary:
        parts.append(f"Summary of earlier turns: {history.summary}")
    for turn in history.recent[-HISTORY_TURNS:]:
        if turn.was_clarify:
            said = "Nura asked a clarifying question instead of answering"
        else:
            said = "; ".join(turn.answer_lines) or "; ".join(turn.honest) or "nothing was found"
        parts.append(f'He asked: "{turn.question}" — Nura said: {said}')
    parts.append(
        'If this question refers back to something above (e.g. "that", "it", "the same '
        'thing"), resolve it using the above before deciding which tools to call.'
    )
    if history.resolved_focus_label:
        # W2: he tapped a clarifying question's own option (or typed a free-text reply the
        # backend already resolved) — the answer is about exactly this, never asked again.
        parts.append(
            f"He just chose: {history.resolved_focus_label}. Answer directly about that; do "
            "not propose a clarifying question about it again."
        )
    if history.recent and history.recent[-1].was_clarify:
        # Fix 1 (module docstring): never two clarifying questions in a row about the same
        # thing. This turn must answer with the best-grounded reading — and say, in the
        # answer's own first line, which reading was taken.
        parts.append(
            "You already asked a clarifying question last turn and were not given a specific "
            "choice back. Do NOT propose another clarifying question now, on any subject — "
            "answer with your single best-grounded reading of this question, and say plainly, "
            "in your first line, which reading you took."
        )
    return "\n".join(parts)


def _doctor_name(visits: Sequence[Appointment], providers: Mapping[uuid.UUID, Provider]) -> str | None:
    now = utcnow()
    ordered = sorted(visits, key=lambda visit: as_utc(visit.scheduled_at))
    coming = [v for v in ordered if v.status in UPCOMING and as_utc(v.scheduled_at) >= now]
    happened = [
        v for v in ordered if v.status == AppointmentStatus.ATTENDED and as_utc(v.scheduled_at) <= now
    ]
    chosen = coming[0] if coming else (happened[-1] if happened else None)
    if chosen is None:
        return None
    provider = providers.get(chosen.provider_id)
    return None if provider is None else provider.name


def _structured_json(response: Any) -> dict[str, Any] | None:
    for block in getattr(response, "content", None) or []:
        block_type = block.get("type") if isinstance(block, Mapping) else getattr(block, "type", None)
        if block_type != "text":
            continue
        text = block.get("text") if isinstance(block, Mapping) else getattr(block, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _tool_use_blocks(response: Any) -> list[Any]:
    blocks = []
    for block in getattr(response, "content", None) or []:
        block_type = block.get("type") if isinstance(block, Mapping) else getattr(block, "type", None)
        if block_type == "tool_use":
            blocks.append(block)
    return blocks


def _block_get(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, Mapping):
        return block.get(key, default)
    return getattr(block, key, default)


class ClaudeAsker:
    """The `Asker` port, answered for real: an agent that decides what to look at. See the
    module docstring for the gate, the tools and the safety checks around the answer."""

    external_processor: str | None = "anthropic"
    """Every ask that reaches the model sends its question, and every tool's plain lines the
    model chose to open, to Anthropic's first-party API (the module docstring). A caller
    writes this reach to the audit trail once per ask, the way `ClaudeNarrator` already does
    for narration."""

    def __init__(
        self, client: AsyncAnthropic, *, searcher: Searcher, model: str = MODEL
    ) -> None:
        self._client = client
        self._searcher = searcher
        self._model = model

    async def ask_stream(
        self,
        session: AsyncSession,
        *,
        context: KeyContext,
        question: str,
        mode: Mode,
        retriever: Retriever,
        store: ObjectStore,
        registry: DrugRegistry | None = None,
        language: str | None = None,
        history: ConversationMemory | None = None,
    ) -> AsyncIterator[AskStep | AnswerDelta | Answer]:
        async def fallback() -> Answer:
            # W2: the fallback holds the same "never twice in a row" and "already resolved"
            # signals the model's own attempt did — a bad or missing proposal from the model
            # never gives the rule-based safety net a second free clarifying question either.
            # `kept_question=kept`: this is not a fresh question — `kept` below already holds
            # the artefact this exact text was kept as, before the model was ever asked, so
            # the fallback must not call `_keep_question` a second time for it (audit-2026-09-
            # 22.md's coordinator note on the (profile_id, sha256) index: reuse the bytes,
            # never let a caller that should not be re-asking skip straight past why).
            focus = None if history is None else history.resolved_focus
            return await recall(
                session,
                context=context,
                question=question,
                mode=mode,
                retriever=retriever,
                store=store,
                registry=registry,
                language=language,
                focus=focus,
                skip_clarify=already_clarified,
                kept_question=kept,
            )

        async with audited_guard(session, context, Action.READ, Scope.ASK, ASK_TARGET):
            context.require(Scope.ASK)
            text = question.strip()
            if not text or len(text) > QUESTION_LENGTH or "\n" in text or "\r" in text:
                raise NotAQuestion(f"a question is one line of one to {QUESTION_LENGTH} characters")
            lang = await language_for(session, context, language)
            reader = await reader_of(session, context, language)
            kept = await _keep_question(session, context, store, text)

            tool_names = _tools_for(context)
            tool_defs = [_TOOL_DEFS[name] for name in tool_names]
            known: dict[str, _ToolLine] = {}
            counter = _TokenCounter()
            visits_seen: list[Appointment] = []
            providers_seen: dict[uuid.UUID, Provider] = {}
            proposals: list[Proposal] = []
            elapsed_seen: set[str] = set()
            """Every elapsed phrase actually handed to the model this ask (fix: "how long
            ago" is computed once here, never guessed by the model — `_parse_answer`'s
            invented-elapsed check catches a line that says one this ask never gave it)."""
            card_safe_text: dict[uuid.UUID, set[str]] = {}
            """Every date/elapsed string actually rendered for each waiting card this ask
            (`_read_waiting_papers`), so a line citing it can be told apart from one that
            states a value the card never gave the model at all."""

            # Written once per ask, before the first call: every round reaches Anthropic's
            # first-party API, whether or not it ends up calling a tool (ADR 0017, mirroring
            # `app.ingestion.review.review_artifact`'s EXTERNAL_MODEL_PROCESSOR line for the
            # extractor, and `ClaudeNarrator`'s for narration).
            await record_audit(
                session,
                context=context,
                action=Action.SHARE,
                scope=Scope.ASK,
                target=EXTERNAL_MODEL_PROCESSOR,
                rows=1,
                shared_with_label=self.external_processor,
            )

            voice = (
                "You are speaking to the patient himself."
                if reader.his
                else f"You are speaking to a family member, about the patient, whose name is "
                f"{reader.name or 'the patient'}."
            )
            system = (
                f"{_SYSTEM_PROMPT}\n\n{voice} Answer in language code {lang!r}."
                f"{_history_block(history)}"
            )
            messages: list[dict[str, Any]] = [{"role": "user", "content": text}]

            already_clarified = bool(history is not None and history.recent and history.recent[-1].was_clarify)
            """Fix 1 (module docstring): the turn right before this one on the same thread was
            itself a clarifying question — never two in a row about the same thing. Enforced
            here, server-side, never trusted to the prompt alone (`_history_block`'s own
            instruction is a hint, not the guarantee): any clarify the model proposes this
            round is simply never looked at."""

            answer: Answer | None = None
            line_repaired = False
            whole_repaired = False
            try:
                for _round in range(MAX_ROUNDS):
                    record_call(Task.ASK, self._model)
                    response = await self._client.messages.create(  # type: ignore[call-overload]
                        model=self._model,
                        max_tokens=MAX_TOKENS,
                        system=system,
                        thinking={"type": "adaptive"},
                        tools=tool_defs,
                        messages=messages,
                        output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
                    )
                    stop_reason = getattr(response, "stop_reason", None)
                    if stop_reason == "refusal":
                        log.info("claude asker: the model refused; the rule-based answer said it")
                        break
                    if stop_reason == "max_tokens":
                        log.warning("claude asker: the model's answer was cut off at max_tokens")
                        break
                    if stop_reason != "tool_use":
                        payload = _structured_json(response)
                        if payload is not None and not already_clarified:
                            clarify = _parse_clarify(
                                payload,
                                known,
                                lang,
                                reader,
                                frozenset(elapsed_seen),
                                {card: frozenset(safe) for card, safe in card_safe_text.items()},
                            )
                            if clarify is not None:
                                answer = Answer(
                                    question_artifact_id=uuid.uuid4(),
                                    mode=mode,
                                    language=lang,
                                    lines=(),
                                    honest=(),
                                    boundary=(),
                                    withheld=(),
                                    dropped=0,
                                    clarify=clarify,
                                )
                                break
                        failed_findings: dict[int, Finding] = {}
                        parsed = (
                            None
                            if payload is None
                            else _parse_answer(
                                payload,
                                known,
                                lang,
                                reader,
                                mode,
                                failed_findings,
                                frozenset(elapsed_seen),
                                {card: frozenset(safe) for card, safe in card_safe_text.items()},
                            )
                        )
                        if parsed is not None and parsed.answer is None and failed_findings and not line_repaired:
                            # One repair round (defect: "the agent still returns an empty
                            # answer"): tell the model which rules its lines broke, in the
                            # verifier's own words for exactly that failure — never the line
                            # itself — and give it one more try before falling back. A generic
                            # "never a line that starts, stops or changes a medicine" was not
                            # concrete enough for the model to fix (defect: rule 14 dropped
                            # every line, repair round included); the verifier's own rewrite
                            # ('a question for the doctor: "Ask Dr Tan about the new amount of
                            # the water pill."') gives it a template to copy.
                            line_repaired = True
                            log.info(
                                "claude asker: repair round, rules=%s",
                                sorted(failed_findings),
                            )
                            assistant_content = getattr(response, "content", None) or []
                            messages.append(
                                {"role": "assistant", "content": assistant_content}
                            )
                            hints = "; ".join(
                                f"rule {rule} — {finding.problem} — say instead: {finding.rewrite}"
                                for rule, finding in sorted(failed_findings.items())
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "Those lines did not pass the house style. Rewrite "
                                        f"them so that: {hints}. Cite the same ids as before."
                                    ),
                                }
                            )
                            continue
                        if (
                            parsed is not None
                            and parsed.answer is not None
                            and (parsed.lead_dropped or parsed.dangling)
                            and not whole_repaired
                        ):
                            # Fix 1b/1d: some lines survived, but not all of them together
                            # still read as one whole answer — either the lead (the direct
                            # answer) was the one dropped, or a survivor opens as though
                            # answering a line that is no longer there. One whole-answer
                            # repair round, counted like any other round: send the model its
                            # own answer back, the dropped line marked, and ask it to rewrite
                            # the whole thing so every sentence left stands alone — no new
                            # tool call, the same checks applied to what comes back.
                            whole_repaired = True
                            log.info(
                                "claude asker: whole-answer repair round, lead_dropped=%s "
                                "dangling=%s",
                                parsed.lead_dropped,
                                parsed.dangling,
                            )
                            assistant_content = getattr(response, "content", None) or []
                            messages.append(
                                {"role": "assistant", "content": assistant_content}
                            )
                            raw_lines = payload.get("lines") if isinstance(payload, Mapping) else []
                            messages.append(
                                {
                                    "role": "user",
                                    "content": _whole_answer_repair_message(
                                        raw_lines if isinstance(raw_lines, list) else [], parsed
                                    ),
                                }
                            )
                            continue
                        if (
                            parsed is not None
                            and parsed.answer is not None
                            and (parsed.lead_dropped or parsed.dangling)
                        ):
                            # The one whole-answer repair chance also failed to make it stand
                            # alone: never show a partial answer (fix 1c) — the rule-based
                            # fallback says it instead.
                            log.info(
                                "claude asker: whole-answer repair still incoherent; the "
                                "rule-based answer said it"
                            )
                            answer = None
                            break
                        answer = None if parsed is None else parsed.answer
                        break

                    tool_uses = _tool_use_blocks(response)
                    if not tool_uses:
                        # `stop_reason` said "tool_use" but there is no tool_use block to run:
                        # never guessed at — the rule-based answer says it instead.
                        log.warning("claude asker: stop_reason was tool_use with no tool call")
                        break

                    assistant_content = getattr(response, "content", None) or []
                    messages.append({"role": "assistant", "content": assistant_content})
                    results: list[dict[str, Any]] = []
                    for block in tool_uses:
                        name = _block_get(block, "name")
                        tool_id = _block_get(block, "id")
                        if name not in tool_names:
                            # Review defect #8: a scope this key does not hold offers no tool
                            # for it (`_tools_for`) — but nothing stopped the model naming one
                            # anyway, and the call ran regardless, its step and "Looked at"
                            # entry reaching the wire as if a withheld part had been read.
                            # Refused here, before anything runs: no step, no result but a
                            # refusal, the same rule a withheld part is never even named by.
                            log.warning(
                                "claude asker: the model named a tool never offered to it: %s",
                                name,
                            )
                            results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": "that tool is not available",
                                }
                            )
                            continue
                        args = _block_get(block, "input") or {}
                        step_lines, count = await self._run_tool(
                            name,
                            args,
                            session=session,
                            context=context,
                            registry=registry,
                            language=lang,
                            visits_seen=visits_seen,
                            providers_seen=providers_seen,
                            counter=counter,
                            proposals=proposals,
                            elapsed_seen=elapsed_seen,
                            card_safe_text=card_safe_text,
                            reader=reader,
                        )
                        for line in step_lines:
                            known[line.token] = line
                        yield AskStep(key=TOOL_STEP_KEYS.get(name, name), count=count)
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": "\n".join(line.text for line in step_lines)
                                or "nothing found",
                            }
                        )
                    messages.append({"role": "user", "content": results})
                else:
                    log.warning("claude asker: hit MAX_ROUNDS without a final answer")
            except (TimeoutError, APITimeoutError, APIConnectionError, APIStatusError) as unreachable:
                log.warning(
                    "claude asker: the call did not answer (%s); the rule-based answer said it",
                    type(unreachable).__name__,
                )
                answer = None
            except Exception:
                log.exception("claude asker: the call failed; the rule-based answer said it")
                answer = None

            if answer is None or (not answer.lines and answer.clarify is None):
                try:
                    answer = await fallback()
                except Exception:
                    # The rule-based answer is supposed to always say something and never
                    # raise — but if it does, that must never be the reason he hears nothing
                    # at all (defect: "the agent's answer reached the phone empty, and so did
                    # the fallback"). Fall through to the belt-and-braces line below.
                    log.exception(
                        "claude asker: the rule-based fallback failed; sending the "
                        "catalogue's honest line"
                    )
                    answer = None
                if answer is None or (
                    not answer.lines and not answer.honest and answer.clarify is None
                ):
                    # Belt and braces: even the rule-based answer, which is supposed to
                    # always say something, came back with nothing to say (or failed
                    # outright, above). Never let only the boundary reach him — say the
                    # catalogue's own honest line ourselves.
                    log.warning(
                        "claude asker: the rule-based fallback had nothing to say; "
                        "sending the catalogue's honest line"
                    )
                    doctor = _doctor_name(visits_seen, providers_seen)
                    withheld = tuple(
                        dict.fromkeys(
                            scope for scope in TOOL_SCOPES.values() if not context.allows(scope)
                        )
                    )
                    answer = Answer(
                        question_artifact_id=kept.id,
                        mode=mode,
                        language=lang,
                        lines=(),
                        honest=tuple(honest_lines(lang, doctor)),
                        boundary=boundary_lines(Surface.RECALL, lang, doctor=doctor),
                        withheld=withheld,
                        dropped=0,
                    )
                if answer.clarify is not None:
                    yield AnswerDelta(text=answer.clarify.question, cites=())
                yield answer
                return

            joined = " ".join(line.text for line in answer.lines)
            if detect(joined) is not None or detect(text) is not None:
                # A red word anywhere near this ask takes the existing red-flag path, not a
                # model-composed line: the safest thing this adapter can do with one it did not
                # expect is say nothing of its own and let the rule-based answer say it plainly.
                log.info("claude asker: a red word was heard; the rule-based answer said it")
                answer = await fallback()
                yield answer
                return

            doctor = _doctor_name(visits_seen, providers_seen)
            withheld = tuple(
                dict.fromkeys(
                    scope for scope in TOOL_SCOPES.values() if not context.allows(scope)
                )
            )
            about_medicine = any(
                any(cite.kind == "medication_line" for cite in line.cites)
                for line in answer.lines
            )
            if answer.clarify is None and _would_change_treatment(text, about_medicine):
                # The same reroute `recall_stream` gives: a question that would change
                # treatment is answered with a question for his doctor, never a model's own
                # lines about it — whatever it composed is not shown.
                answer = Answer(
                    question_artifact_id=kept.id,
                    mode=mode,
                    language=lang,
                    lines=(),
                    honest=tuple(reroute_lines(lang, doctor)),
                    boundary=boundary_lines(Surface.RECALL, lang, doctor=doctor),
                    withheld=withheld,
                    dropped=len(answer.lines),
                )
                yield answer
                return

            if answer.clarify is not None:
                yield AnswerDelta(text=answer.clarify.question, cites=())
            for answer_line in answer.lines:
                yield AnswerDelta(text=answer_line.text, cites=answer_line.cites)
            answer = Answer(
                question_artifact_id=kept.id,
                mode=mode,
                language=lang,
                lines=answer.lines,
                honest=answer.honest,
                boundary=boundary_lines(Surface.RECALL, lang, doctor=doctor),
                withheld=withheld,
                dropped=answer.dropped,
                proposals=tuple(proposals),
                clarify=answer.clarify,
            )
            await record_audit(
                session,
                context=context,
                action=Action.READ,
                scope=Scope.ASK,
                target=ASK_TARGET,
                target_id=kept.id,
                rows=len(answer.lines),
            )
            yield answer

    async def _run_tool(
        self,
        name: str,
        args: Mapping[str, Any],
        *,
        session: AsyncSession,
        context: KeyContext,
        registry: DrugRegistry | None,
        language: str,
        visits_seen: list[Appointment],
        providers_seen: dict[uuid.UUID, Provider],
        counter: _TokenCounter,
        proposals: list[Proposal],
        elapsed_seen: set[str],
        card_safe_text: dict[uuid.UUID, set[str]],
        reader: Reader,
    ) -> tuple[list[_ToolLine], int]:
        if name == "read_medicines":
            return await _read_medicines(
                session, context, registry, language, counter, elapsed_seen, reader
            )
        if name == "read_readings":
            return await _read_readings(session, context, language, counter, elapsed_seen, reader)
        if name == "read_visits":
            lines, count, visits, providers = await _read_visits(
                session, context, language, counter, elapsed_seen, reader
            )
            visits_seen.extend(visits)
            providers_seen.update(providers)
            return lines, count
        if name == "read_records":
            return await _read_records(session, context, language, counter, elapsed_seen, reader)
        if name == "read_feelings":
            return await _read_feelings(session, context, counter)
        if name == "search_online":
            query = str(args.get("query") or "")
            return await _search_online(session, context, self._searcher, query, counter)
        if name == "read_insurance":
            return await _read_insurance(session, context, counter)
        if name == "read_costs":
            return await _read_costs(session, context, language, counter)
        if name == "read_plan":
            return await _read_plan(session, context, language, counter)
        if name == "read_waiting_papers":
            return await _read_waiting_papers(
                session, context, language, counter, elapsed_seen, card_safe_text
            )
        if name == "propose_action":
            kind = str(args.get("kind") or "")
            label = str(args.get("label") or "")
            return await _propose_action(kind, label, counter, proposals)
        return [], 0


def _drop(reason: str, *, rules: Sequence[int] = ()) -> None:
    """One line logged, its reason class only — never its text, never a cite, never a value
    off his record (defect: "the agent's answer reached the phone empty", fixed by knowing,
    from the logs alone, which gate a line actually failed). `rules` names which
    `docs/plain-words.md` rule numbers a `plain_words_failed` drop broke — still never the
    words that broke them."""
    if rules:
        log.info("claude asker: dropped a line, reason=%s, rules=%s", reason, list(rules))
    else:
        log.info("claude asker: dropped a line, reason=%s", reason)


def _plain_words_findings(text: str, language: str) -> list[Finding]:
    """The `docs/plain-words.md` findings `text` fails against Ask's own profile
    (`kind="ask"`: rule 2 off, rule 3's ceiling twenty words — every other rule, 14 included,
    exactly as strict as `kind="line"`), one per broken rule, sorted by rule — never the text
    itself. Logged (by rule number only) by `_drop`, and handed to the model, problem and
    rewrite but never the line, as the one repair round's hint."""
    by_rule = {
        finding.rule: finding
        for finding in verify(text, language, "ask")
        if finding.severity == "fail"
    }
    return [by_rule[rule] for rule in sorted(by_rule)]


_DANGLING_OPENERS: Final[dict[str, tuple[str, ...]]] = {
    "en": (
        "however",
        "but",
        "instead",
        "it also",
        "still",
        "on the other hand",
        "apart from that",
        "also",
    ),
    "ms": ("tetapi", "namun", "sebaliknya", "selain itu", "juga"),
    "zh": ("但是", "不过", "然而", "另外", "此外", "而且"),
}
"""A small, named list (fix 1d, this module's docstring; review defect #9) of contrastive or
anaphoric openers that only make sense right after the line they answer back to — "What your
papers DO hold…" after a dropped lead is the live defect this catches. The prompt
(`ask_agent.txt`) forbids every one of these outright; this is the cheap backstop for when the
model writes one anyway.

Never bare "that"/"this"/"so": a review defect, twice over — first, "so" matched inside
"Something"/"Soon"/"Sometimes" because the check was a plain `str.startswith`, not a real word
boundary; fixed for every opener here with `\\b`. Second, requiring "so" be followed by a comma
still could not tell "So, the tablet was late." (dangling) from "So far nothing is written
down." or "So the answer is..." (not — "so" is followed by ordinary words, not a reference back)
without also missing "But your next visit…"/"However your…"/"Instead your…", which open with
nothing after them but a space, no comma at all. Rather than chase "so"'s ambiguity further,
it — and "that"/"this", which matched far more ordinary sentences ("That tablet is your water
pill.", "This is written down in your papers.") than real dangling references — are simply not
in the list. Every opener that remains is unambiguous enough on its own that a comma OR a
plain space after it is enough (`_dangling_pattern_latin`); Chinese needs neither, since a
connective character run at the very start of the line already reads as one (module docstring
below, `_dangling_pattern_zh`)."""


def _dangling_pattern_latin(openers: tuple[str, ...]) -> re.Pattern[str]:
    """en/ms: the opener as a whole word (or phrase) right at the start, followed by a comma
    or any whitespace — never nothing at all, so it can never match as a mere prefix of a
    longer, unrelated word."""
    longest_first = sorted(openers, key=len, reverse=True)
    body = "|".join(re.escape(word) for word in longest_first)
    return re.compile(rf"^(?:{body})\b(?:[,]|\s)", re.IGNORECASE)


def _dangling_pattern_zh(openers: tuple[str, ...]) -> re.Pattern[str]:
    """zh: no word boundaries (CJK has none the way Latin script does — `\\b但是您` has no
    boundary between "是" and "您" at all) and no punctuation required; the opener characters
    right at the start of the line are enough on their own."""
    longest_first = sorted(openers, key=len, reverse=True)
    body = "|".join(re.escape(word) for word in longest_first)
    return re.compile(rf"^(?:{body})")


_DANGLING_PATTERN: Final[dict[str, re.Pattern[str]]] = {
    "en": _dangling_pattern_latin(_DANGLING_OPENERS["en"]),
    "ms": _dangling_pattern_latin(_DANGLING_OPENERS["ms"]),
    "zh": _dangling_pattern_zh(_DANGLING_OPENERS["zh"]),
}

_WHAT_DO_HOLD: Final[dict[str, re.Pattern[str]]] = {
    "en": re.compile(r"^what\b.{0,40}\bdo(?:es)?\s+hold\b", re.IGNORECASE),
    "ms": re.compile(r"^apa\b.{0,40}\bada\b", re.IGNORECASE),
    "zh": re.compile(r"^(?:那|这)(?:些)?(?:文件|papers)?(?:里|中)?有的"),
}
"""The one concrete shape named in the fix ("What your papers DO hold…"): a dangling opener
even where a bare "what"/"apa" alone would be too broad to flag on its own."""


def _starts_with_dangling_opener(text: str, language: str) -> bool:
    stripped = text.strip()
    pattern = _DANGLING_PATTERN.get(language, _DANGLING_PATTERN["en"])
    if pattern.match(stripped):
        return True
    what_do_hold = _WHAT_DO_HOLD.get(language, _WHAT_DO_HOLD["en"])
    return bool(what_do_hold.match(stripped))


_ELAPSED_CLAIM: Final[dict[str, re.Pattern[str]]] = {
    "en": re.compile(
        r"\b(?:yesterday|\d+\s+days?\s+ago|about\s+\d+\s+(?:weeks?|months?|years?)\s+ago"
        r"|in\s+about\s+\d+\s+(?:weeks?|months?|years?))\b",
        re.IGNORECASE,
    ),
    "ms": re.compile(
        r"\b(?:semalam|\d+\s+hari\s+lalu|kira-kira\s+\d+\s+(?:minggu|bulan|tahun)\s+lalu"
        r"|dalam\s+kira-kira\s+\d+\s+(?:minggu|bulan|tahun))\b",
        re.IGNORECASE,
    ),
    "zh": re.compile(r"(?:昨天|\d+天前|大约\d+(?:周|个月|年)前|大约\d+(?:周|个月|年)后)"),
}
"""The shape of a *computed* elapsed claim (fix 3, this module's docstring; review defect #4):
deliberately narrow — "N days/weeks/months/years ago", "about N … ago", "in about N …", and
"yesterday" — never the bare, ordinary words "today", "tomorrow" or "in N days" on their own,
which turned up in perfectly innocent lines with no date claim at all ("Ask Dr Tan about the
water pill today.") and were wrongly dropped. A line whose elapsed-shaped words do not match
one this ask actually handed it (`elapsed_given`) is treated like an uncited claim — repaired
or dropped, never shown as though it were read off the record."""

_VAGUE_ELAPSED: Final[dict[str, tuple[str, ...]]] = {
    "en": (
        "over a year ago",
        "a couple of years ago",
        "a few months ago",
        "some time ago",
        "not long ago",
        "a while ago",
        "last year",
        "recently",
    ),
    "ms": (
        "lebih setahun lalu",
        "beberapa tahun lalu",
        "beberapa bulan lalu",
        "sekian lama",
        "tidak lama dahulu",
        "seketika dahulu",
        "tahun lepas",
        "baru-baru ini",
    ),
    "zh": ("一年多前", "好几年前", "好几个月前", "一段时间前", "不久前", "前阵子", "去年", "最近"),
}
"""Review defect #5: the computed-shape check above under-fires on a vague elapsed claim with
no number at all ("last year", "recently", "a while ago") — this app's own `elapsed_phrase`
never produces one of these, so any occurrence is always wrong, never checked against
`elapsed_given`. Kept as its own small, named constant, per language, so the list stays
auditable rather than folded into the regex above. The bare, unnumbered forms of "months ago"
("bulan lalu") are handled separately, by `_BARE_UNIT_AGO` below: as a *literal* string each
would also match inside a perfectly legitimate computed phrase this ask really gave
("20 months ago" contains the substring "months ago"), so they need the negative lookbehind a
plain substring check cannot express."""

_BARE_UNIT_AGO: Final[dict[str, re.Pattern[str]]] = {
    "en": re.compile(r"(?<!\d )(?<!\d)months? ago\b", re.IGNORECASE),
    "ms": re.compile(r"(?<!\d )(?<!\d)bulan lalu\b", re.IGNORECASE),
    "zh": re.compile(r"(?<!\d)个月前"),
}
""""Months ago" (or its ms/zh equivalent) with no number in front of it at all — always vague,
always wrong — but excluded, by the lookbehind, from matching inside a legitimate "20 months
ago" this ask actually gave."""

_VAGUE_BACK_AGO_FAMILY: Final[dict[str, re.Pattern[str]]] = {
    "en": re.compile(r"\b(?:ages?|a long time|a few \w+|several \w+)\s+(?:back|ago)\b", re.IGNORECASE),
    "ms": re.compile(r"\b(?:sudah lama|beberapa \w+)\s+(?:dahulu|yang lalu)\b", re.IGNORECASE),
    "zh": re.compile(r"(?:很久|好久)(?:以前|之前)"),
}
"""A family, not a fixed list: a vague quantity word ("ages", "a long time", "a few …",
"several …" / "sudah lama", "beberapa …" / 很久, 好久) right before "back"/"ago" ("lalu"/
"dahulu" folded into the family above; "前"/"以前" folded into the zh pattern itself) is always
vague, whatever the quantity word — catches "a few months back", "ages ago", "a long time
back" and their ms/zh equivalents without enumerating every combination as a literal."""


def _elapsed_claim(text: str, language: str, elapsed_given: frozenset[str]) -> str | None:
    """The first elapsed-shaped phrase `text` claims that this ask never actually gave it —
    a computed shape ("about 3 weeks ago") not, case-insensitively, in `elapsed_given`, or any
    vague phrase at all (`_VAGUE_ELAPSED`/`_BARE_UNIT_AGO`/`_VAGUE_BACK_AGO_FAMILY`, always
    wrong). `None` when the line makes no such claim, or every one it makes was really given."""
    for vague in _VAGUE_ELAPSED.get(language, _VAGUE_ELAPSED["en"]):
        if vague in text.lower():
            return vague
    bare_unit = _BARE_UNIT_AGO.get(language, _BARE_UNIT_AGO["en"])
    bare_match = bare_unit.search(text)
    if bare_match is not None:
        return bare_match.group()
    family = _VAGUE_BACK_AGO_FAMILY.get(language, _VAGUE_BACK_AGO_FAMILY["en"])
    family_match = family.search(text)
    if family_match is not None:
        return family_match.group()
    pattern = _ELAPSED_CLAIM.get(language, _ELAPSED_CLAIM["en"])
    given_lower = {phrase.lower() for phrase in elapsed_given}
    for match in pattern.finditer(text):
        if match.group().lower() not in given_lower:
            return match.group()
    return None


_ELAPSED_RULE: Final = 90
"""Never a real `docs/plain-words.md` rule number (those run 1-14): a pseudo-rule so an
invented or vague elapsed claim can still ride the same `Finding`-based repair-hint machinery
every other broken rule does (review defect #4 — the drop used to record no `Finding` at all,
so it could never trigger a repair round)."""


def _elapsed_claim_finding(phrase: str, language: str) -> Finding:
    return Finding(
        rule=_ELAPSED_RULE,
        problem=f'"{phrase}" is not one of the elapsed times this ask actually gave you',
        rewrite="use the elapsed words given beside the date exactly, word for word",
        text=phrase,
        severity="fail",
        language=language,
        kind="ask",
    )


_VALUE_RULE: Final = 91
"""Another pseudo-rule (see `_ELAPSED_RULE`), for a line rejected by
`_claims_a_value_from_an_unconfirmed_card`: recorded so the repair round fires with a concrete
instruction, rather than the line simply vanishing (review defect #1, second pass)."""


def _unconfirmed_card_value_finding(language: str) -> Finding:
    return Finding(
        rule=_VALUE_RULE,
        problem="a line about a paper he has not checked yet states a number from it",
        rewrite=(
            "say only that it is waiting for him to check, and its date — never a number, "
            "not even one you are sure of"
        ),
        text="",
        severity="fail",
        language=language,
        kind="ask",
    )


_EN_NUMBER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
        "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
        "eighty", "ninety", "hundred", "thousand", "point",
    }
)
_MS_NUMBER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "kosong", "sifar", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "lapan",
        "sembilan", "sepuluh", "belas", "puluh", "ratus", "ribu", "perpuluhan",
    }
)
_ZH_NUMERAL_RUN: Final = re.compile(r"[零一二三四五六七八九十百千两〇点]{2,}")
_WORD: Final = re.compile(r"[a-z]+")


def _strip_safe_substrings(text: str, safe: frozenset[str]) -> str:
    """`text` with every phrase in `safe` removed, longest first, so a shorter phrase never
    eats part of a longer one it is itself a substring of ("today" inside a longer elapsed
    phrase that happens to contain it, though none of this app's own phrases do)."""
    stripped = text
    for phrase in sorted((p for p in safe if p), key=len, reverse=True):
        stripped = stripped.replace(phrase, " ")
    return stripped


def _contains_a_number_shape(text: str) -> bool:
    """Whether `text` (already NFKC-normalised and stripped of whatever substrings are safe
    to carry one) says a number in any shape this app knows: any digit at all (so a full-width
    "１１．４" counts once normalised), any run of two or more Chinese numeral characters, or two
    en/ms number words in a row. A single number word alone is ordinary speech, and the
    catalogue's own waiting lines use it — "Satu ujian darah menunggu…", 一份血液报告…, "one
    paper is waiting", "at this point" — which an earlier version of this check rejected,
    switching the waiting-paper line off in Malay and Chinese (third review pass, finding B).
    Shared by `_claims_a_value_from_an_unconfirmed_card` (a line touching an unconfirmed card)
    and `_parse_clarify` (a clarifying question, and every option label — review B1/B2/B4/B6):
    the shape of a stated value, wherever it came from, is checked identically everywhere."""
    if re.search(r"\d", text):
        return True
    if _ZH_NUMERAL_RUN.search(text):
        return True
    number_words = _EN_NUMBER_WORDS | _MS_NUMBER_WORDS
    tokens = _WORD.findall(text.lower())
    return any(a in number_words and b in number_words for a, b in itertools.pairwise(tokens))


def _claims_a_value_from_an_unconfirmed_card(
    text: str, cites: Sequence[Cite], safe_for_card: frozenset[str]
) -> bool:
    """Whether `text` says a number that is not one of `safe_for_card` — the dates and elapsed
    phrases this ask actually rendered for the review card(s) it cites — belt and braces over
    `WaitingPaper`'s own refusal to read a value at all (review defect #1, second pass): not a
    claim that this reads or understands prose, only that a line touching an unconfirmed card
    is checked, after removing his own written-down date, for the shape of a stated value
    (`_contains_a_number_shape`). Fires on `any` cite naming a review card, not `all` of them —
    one legitimate cite alongside it must never turn this check off."""
    if not any(cite.kind == "review_card" for cite in cites):
        return False
    normalized = unicodedata.normalize("NFKC", text)
    stripped = _strip_safe_substrings(normalized, safe_for_card)
    return _contains_a_number_shape(stripped)


@dataclass(frozen=True, slots=True)
class _Parsed:
    """The result of checking the model's own payload against every gate (fix 1, this
    module's docstring): the answer that survives, and whether it stands alone. `lead_dropped`
    is true when the model's own first line did not survive but at least one later line did —
    the live defect ("What your papers DO hold…" with no lead). `dangling` is true when a
    surviving line opens as though answering something that is no longer there, whether or not
    the lead specifically was the one dropped."""

    answer: Answer | None
    lead_dropped: bool = False
    dangling: bool = False


def _parse_answer(
    payload: Mapping[str, Any],
    known: Mapping[str, _ToolLine],
    language: str,
    reader: Reader,
    mode: Mode,
    failed_findings: dict[int, Finding] | None = None,
    elapsed_given: frozenset[str] = frozenset(),
    card_safe_text: Mapping[uuid.UUID, frozenset[str]] = MappingProxyType({}),
) -> _Parsed:
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list):
        log.info("claude asker: payload had no 'lines' list")
        return _Parsed(None)
    # Case-insensitive, so `M1` or `m1 ` matches the `m1` a tool result actually carried —
    # the model is asked to copy a short id back, not retype a uuid, but it still may not get
    # the case exactly right, and a line should not be thrown away over that alone.
    known_ci = {token.strip().lower(): line for token, line in known.items()}
    lines: list[AnswerLine] = []
    origins: list[int] = []
    for index, entry in enumerate(raw_lines):
        if not isinstance(entry, Mapping):
            _drop("malformed_entry")
            continue
        raw_text, raw_cites = entry.get("text"), entry.get("cites")
        if not isinstance(raw_text, str) or not isinstance(raw_cites, list):
            _drop("malformed_text_or_cites")
            continue
        text = raw_text.strip()
        if not text:
            _drop("empty_text")
            continue
        if not verified(text, language, "ask"):
            findings = _plain_words_findings(text, language)
            rules = tuple(finding.rule for finding in findings)
            if failed_findings is not None:
                for finding in findings:
                    failed_findings.setdefault(finding.rule, finding)
            rewritten = _boundary_rewrite(text, language) if rules == (14,) else None
            if rewritten is not None and verified(rewritten, language, "ask"):
                # Rule 14 alone, and nothing else wrong with the line: rewritten into the
                # catalogue's own shape for it — a question for the doctor — rather than
                # dropped outright (defect: every medicine line dropped, on both rounds, and
                # the reader heard nothing at all).
                text = rewritten
            else:
                _drop("plain_words_failed", rules=rules)
                continue
        if _has_conclusion_language(text, language):
            _drop("conclusion_language")
            continue
        elapsed_problem = _elapsed_claim(text, language, elapsed_given)
        if elapsed_problem is not None:
            # Fix 3 / review defect #4: the model did its own date arithmetic, or reached for
            # a vague phrase this app never produces, instead of using an elapsed phrase this
            # ask actually gave it — treated like an uncited claim, never shown. Recorded as a
            # `Finding` (a pseudo-rule, `_ELAPSED_RULE`) so it can still trigger a repair round
            # the same way a broken plain-words rule does.
            if failed_findings is not None:
                finding = _elapsed_claim_finding(elapsed_problem, language)
                failed_findings.setdefault(finding.rule, finding)
            _drop("invented_elapsed_phrase")
            continue
        heard = reader.says(text)
        if not reader.his and reader.speaks_to_him(heard):
            _drop("caregiver_voice")
            continue
        cites = tuple(
            dict.fromkeys(
                known_ci[str(token).strip().lower()].cite
                for token in raw_cites
                if str(token).strip().lower() in known_ci
            )
        )
        if not cites:
            _drop("no_cite_matched")
            continue
        safe_for_card: set[str] = set()
        for cite in cites:
            if cite.kind == "review_card":
                safe_for_card |= card_safe_text.get(cite.id, frozenset())
        if _claims_a_value_from_an_unconfirmed_card(heard, cites, frozenset(safe_for_card)):
            # Review defect #1, second layer: a line touching an unconfirmed review card has
            # no value to say beyond its own written-down date — `WaitingPaper` carries none —
            # so a line that states one anyway is dropped, whatever put it there, and recorded
            # as a `Finding` so the repair round fires.
            if failed_findings is not None:
                finding = _unconfirmed_card_value_finding(language)
                failed_findings.setdefault(finding.rule, finding)
            _drop("value_from_unconfirmed_card")
            continue
        lines.append(AnswerLine(text=heard, cites=cites))
        origins.append(index)
    if not lines:
        log.info(
            "claude asker: no line survived out of %d the model offered", len(raw_lines)
        )
        return _Parsed(None)
    kept_lines = lines[:1] if mode is Mode.VOICE else lines[:TEXT_LINES]
    kept_origins = origins[: len(kept_lines)]
    lead_dropped = bool(raw_lines) and (not kept_origins or kept_origins[0] != 0)
    survived = set(kept_origins)
    dangling = any(
        _starts_with_dangling_opener(line.text, language)
        and (origin == 0 or origin - 1 not in survived)
        for line, origin in zip(kept_lines, kept_origins, strict=True)
    )
    answer = Answer(
        question_artifact_id=uuid.uuid4(),  # overwritten by the caller with the kept artefact
        mode=mode,
        language=language,
        lines=tuple(kept_lines),
        honest=(),
        boundary=(),
        withheld=(),
        dropped=len(raw_lines) - len(kept_lines),
    )
    return _Parsed(answer, lead_dropped=lead_dropped, dangling=dangling)


MIN_CLARIFY_CANDIDATES: Final = 2
MAX_CLARIFY_CANDIDATES: Final = 4
CLARIFY_LABEL_LENGTH: Final = 140

_ASKER_DIRECTED_IDIOMS: Final[dict[str, tuple[str, ...]]] = {
    "en": ("do you mean", "did you mean", "are you asking about", "which one do you mean"),
    "ms": ("adakah maksud anda", "yang mana anda maksudkan", "awak maksudkan"),
    "zh": ("您是指", "你是指", "您说的是", "你说的是"),
}
"""A clarifying question addresses whoever is asking, never the patient (module docstring,
fix 1): "Which blood test do you mean?" said to a caregiver is correct — the "you" is her, not
Pa — but the blunt "you/your" scan `Reader.speaks_to_him` runs (built for a line ABOUT him)
cannot tell that apart from "your blood test", said about the patient, which is wrong in her
voice (review S4). Exempts only these known, asker-directed idioms; any other "you/your" in
the question still fails exactly as it would for any other line."""


def _clarify_question_voice_ok(heard: str, reader: Reader, language: str) -> bool:
    """Whether `heard` is safe in `reader`'s own voice (review S4): always true for the
    patient's own key; for anyone else, true when it either never speaks to him at all, or
    every "you/your" in it is inside a known asker-directed idiom — never a possessive about
    the patient himself, which is exactly as wrong here as it would be in any other line."""
    if reader.his or not reader.speaks_to_him(heard):
        return True
    stripped = heard
    for idiom in _ASKER_DIRECTED_IDIOMS.get(language, ()):
        stripped = re.sub(re.escape(idiom), " ", stripped, flags=re.IGNORECASE)
    return not reader.speaks_to_him(stripped)


def _parse_clarify(
    payload: Mapping[str, Any],
    known: Mapping[str, _ToolLine],
    language: str,
    reader: Reader,
    elapsed_given: frozenset[str],
    card_safe_text: Mapping[uuid.UUID, frozenset[str]],
) -> Clarify | None:
    """The model's own proposed clarifying question (W2), validated before a single word of it
    ever reaches the wire — a bad proposal is dropped entirely, never repaired, never shown:
    the caller falls back to an ordinary answer (or the rule-based one) exactly as it would for
    no proposal at all. Every option's label is built here alone, from confirmed data the
    model already read (`_ToolLine.label`) — never the model's own words for it.

    The question and every label are a new way for words to reach him, so both get every
    protection a tool line and an answer line already have (independent safety review, the
    round that found B1-B6): the same control-character/forged-id sanitiser `_register`
    already applies (`_sanitize_free_text`), the same closed no-number rule everywhere a value
    could otherwise slip through (`_contains_a_number_shape` — unconditional on the question,
    never gated by which cites a candidate happens to carry; a label may carry a digit only
    inside its own `label_safe` substring), a length cap, and never two options sharing one
    label (he could never tell them apart, and the next turn would answer about the wrong
    one)."""
    raw = payload.get("clarify")
    if not isinstance(raw, Mapping):
        return None
    raw_question = raw.get("question")
    if not isinstance(raw_question, str) or not raw_question.strip():
        _drop("clarify_no_question")
        return None
    question = _sanitize_free_text(raw_question.strip())
    if not question:
        _drop("clarify_no_question")
        return None
    raw_ids = raw.get("candidate_ids")
    ids = [str(each).strip() for each in raw_ids] if isinstance(raw_ids, list) else []
    known_ci = {token.strip().lower(): line for token, line in known.items()}
    options: tuple[ClarifyOption, ...]
    if ids:
        if not (MIN_CLARIFY_CANDIDATES <= len(ids) <= MAX_CLARIFY_CANDIDATES):
            _drop("clarify_bad_candidate_count")
            return None
        resolved: list[_ToolLine] = []
        seen_cites: set[tuple[str, uuid.UUID]] = set()
        for raw_id in ids:
            line = known_ci.get(raw_id.lower())
            if line is None:
                _drop("clarify_candidate_not_in_tool_results")
                return None
            if line.label is None:
                # This kind never stands as a clarify candidate (a web result, a proposal, an
                # insurance line): the model named one anyway — the whole proposal is dropped,
                # never partially shown (module docstring: "a bad proposal never reaches the
                # wire").
                _drop("clarify_candidate_has_no_backend_label")
                return None
            key = (line.cite.kind, line.cite.id)
            if key in seen_cites:
                continue
            seen_cites.add(key)
            resolved.append(line)
        safe_options: list[ClarifyOption] = []
        seen_labels: set[str] = set()
        collision = False
        for line in resolved:
            assert line.label is not None
            # Sanitised, never truncated here: every free-text part was already cut to length
            # where the label was built, BEFORE the rendered date was added. A label still
            # longer than the hard ceiling is not cut (that is what lost the date): the
            # candidate is left out.
            clean_label = _sanitize_free_text(line.label).strip()
            if not clean_label:
                _drop("clarify_label_empty_after_sanitising")
                continue
            if len(clean_label) > CLARIFY_LABEL_LENGTH:
                _drop("clarify_label_too_long")
                continue
            normalized_label = unicodedata.normalize("NFKC", clean_label)
            stripped_label = _strip_safe_substrings(normalized_label, line.label_safe)
            if _contains_a_number_shape(stripped_label):
                # Review B1/B4: a value outside the one substring this label is allowed to
                # carry a digit in (a rendered date, or a medicine's own generic+strength) is
                # never repaired — this one candidate is simply dropped.
                _drop("clarify_label_value_outside_the_safe_substring")
                continue
            if clean_label in seen_labels:
                # Review B4: two options may never carry the same label — never repaired
                # either; a collision drops the whole clarify, below.
                collision = True
                continue
            seen_labels.add(clean_label)
            safe_options.append(
                ClarifyOption(label=clean_label, value=uuid.uuid4().hex, cite=line.cite)
            )
        if collision or not (MIN_CLARIFY_CANDIDATES <= len(safe_options) <= MAX_CLARIFY_CANDIDATES):
            _drop("clarify_bad_candidate_count")
            return None
        options = tuple(safe_options)
    else:
        # No candidates: a missing required detail (a procedure, a date range) — a free-text
        # reply is expected instead. Never an ordinary answer's list of options either way.
        options = ()
    allow_other = not ids
    if not verified(question, language, "ask"):
        _drop("clarify_question_plain_words_failed")
        return None
    if _has_conclusion_language(question, language):
        _drop("clarify_question_conclusion_language")
        return None
    if _elapsed_claim(question, language, elapsed_given) is not None:
        _drop("clarify_question_invented_elapsed_phrase")
        return None
    if _starts_with_dangling_opener(question, language):
        _drop("clarify_question_dangling_opener")
        return None
    # Review B1: a clarifying question never needs a number at all — every date lives in the
    # backend-built option labels, never in the sentence that asks which one. Unconditional:
    # never gated by which cites a candidate happens to carry (the live defect this closes —
    # "Do you mean the blood test where your sugar was 11.4?", with `candidate_ids: []`, so
    # the old, cite-gated unconfirmed-card check never even ran for it).
    if _contains_a_number_shape(unicodedata.normalize("NFKC", question)):
        _drop("clarify_question_contains_a_number")
        return None
    heard = reader.says(question)
    if not _clarify_question_voice_ok(heard, reader, language):
        _drop("clarify_question_caregiver_voice")
        return None
    if detect(heard) is not None:
        _drop("clarify_question_red_word")
        return None
    return Clarify(question=heard, options=options, allow_other=allow_other)


def _answer_from_payload(
    payload: Mapping[str, Any],
    known: Mapping[str, _ToolLine],
    language: str,
    reader: Reader,
    mode: Mode,
    failed_findings: dict[int, Finding] | None = None,
) -> Answer | None:
    """`_parse_answer`'s answer alone — kept as its own name for the callers (and the unit
    tests) that only ever wanted the answer, never the coherence flags."""
    return _parse_answer(payload, known, language, reader, mode, failed_findings).answer


def _whole_answer_repair_message(raw_lines: Sequence[Any], parsed: _Parsed) -> str:
    """The whole-answer repair round's own message (fix 1b/1d, this module's docstring): his
    full answer, sent straight back — the model's own words, never logged — with the line the
    house style dropped marked, asking for the whole answer rewritten so every line left reads
    on its own. Same tool results, same checks; no new tool call is asked for."""
    marked = []
    for index, entry in enumerate(raw_lines):
        text = entry.get("text") if isinstance(entry, Mapping) else None
        text = text if isinstance(text, str) and text.strip() else "(not text)"
        marked.append(f"{index + 1}. {text}")
    reason = (
        "its lead line (the direct answer) was removed by the house style"
        if parsed.lead_dropped
        else "a line that is left opens as though answering a line that is no longer there"
    )
    return (
        "Your last answer, before the house style checked it, was:\n"
        + "\n".join(marked)
        + f"\n\nOne problem with it: {reason}. Rewrite the WHOLE answer so every sentence "
        "left stands on its own and the set together still answers the question — never "
        "start a sentence with a word like 'However', 'But', 'Instead', 'That', 'It also' or "
        "'What ... do hold' that only makes sense right after a sentence that is no longer "
        "there. Use only the same tool results already given; call no new tool. Cite the "
        "same ids as before."
    )


__all__ = ["ClaudeAsker"]
