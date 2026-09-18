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
`app.delivery.feed.claude_adapters.ClaudeSearcher`). A tool for a scope this key does not hold
is never offered to the model at all: a withheld part cannot even be named, the same rule
`_corpus_stream` holds by never reading it. Every tool's result is plain lines already in his
own words, each carrying its own id — never a row, never a raw value the model could restate
past what is written down.

The answer is structured output: lines, each cited only to ids a tool actually returned this
ask; a boundary line, always the catalogue's own for the reader's language, whatever the model
wrote (`app.safety.boundary.boundary_lines`) — the model is never trusted with that line
itself. Every surviving line passes the plain-words verifier and the same conclusion-and-advice
blocklist `app.llm.narrate.ClaudeNarrator` holds every rephrase to, and is checked for
caregiver voice the same way (`app.channels.about_him.Reader`). A line that fails any of these
is dropped; a cite outside this ask's own tool results is dropped from its line; a line with
nothing left to cite is dropped. If nothing survives — or the call refuses, times out, runs
past `MAX_ROUNDS`, or answers something that does not parse — the answer is the rule-based
asker's own answer for the same question: the stream never ends without one.

Demo only (ADR 0017), the same story `app.llm.narrate.ClaudeNarrator`'s module docstring
tells: Anthropic's first-party API does not process in SG or MY, so this adapter may only be
built where every word it is shown is demo or test data (`app.search.asker_provider.
asker_for`, gated by `app.llm.residency.allow_external_model`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
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
from app.delivery.timeline_strings import honest_lines, reroute_lines, verified
from app.drugs.registry import DrugRegistry
from app.ingestion.objects import ObjectStore
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.insurance.ledger import insurance_ledger
from app.insurance.policy import current_policies
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.llm.narrate import _has_conclusion_language
from app.llm.prompts import load_prompt
from app.medicines.models import MedicationLine
from app.memory.models import Appointment, AppointmentStatus, Provider
from app.memory.spine import UPCOMING
from app.memory.timeline import language_for
from app.reasoning.feelings.service import recent_notes
from app.reasoning.visits.planner import propose_visits
from app.safety.boundary import Surface, boundary_lines
from app.safety.plain_words import verify
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
    Mode,
    NotAQuestion,
    Proposal,
    _facts_under,
    _is_reading,
    _keep_question,
    _plain_name,
    recall,
)
from app.search.asker import AnswerDelta
from app.search.conversation import ConversationMemory
from app.search.retrieve import Retriever

log = logging.getLogger("nura.llm.ask_agent")

MODEL: Final = "claude-opus-5"
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

_RULE_HINTS: Final[dict[int, str]] = {
    1: "each line is a whole sentence, someone doing something, ending in . ! ? or :",
    2: "one idea per line",
    3: "short words and short lines, under ten where it can be done, never over fifteen",
    4: "call things what he calls them, never the chemical or clinical name alone",
    5: "say the day and the date in words, never digits, a clock time or a time zone",
    10: "numbers as digits, small and few — never more than three on one line",
    11: "never a red word like missed, failed, overdue or non-compliant",
    12: "nothing to decode — no abbreviations, no units, no jargon like dose or follow-up",
    13: "the same words every time for the same thing",
    14: "never a line that starts, stops or changes a medicine",
}
"""One short, generic instruction per `docs/plain-words.md` rule (and rule 14, the boundary
check `_check_boundary` also runs), for the one repair round: the model is told which rules
its lines broke, never the lines themselves — nothing it wrote leaves this process twice."""

ANSWER_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines", "boundary"],
    "properties": {
        "lines": {
            "type": "array",
            "description": "What the record answers, each at most one sentence, plain, "
            "never what a number means and never advice.",
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
    },
}

_SYSTEM_PROMPT: Final = load_prompt("ask_agent")


@dataclass
class _ToolLine:
    """One line a tool gave back, and the `Cite` it stands for if the model names its id."""

    token: str
    text: str
    cite: Cite


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


def _register(
    lines: list[_ToolLine], counter: _TokenCounter, kind: str, id_: uuid.UUID, text: str
) -> str:
    token = counter.next(kind)
    lines.append(_ToolLine(token=token, text=f"{token}: {text}", cite=Cite(kind=kind, id=id_)))
    return token


async def _read_medicines(
    session: AsyncSession,
    context: KeyContext,
    registry: DrugRegistry | None,
    language: str,
    counter: _TokenCounter,
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
        started = line.started_at.date().isoformat()
        _register(
            lines, counter, "medication_line", line.id, f"{name}, {who}, started {started}"
        )
    return lines, len(found)


async def _read_readings(
    session: AsyncSession, context: KeyContext, language: str, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    facts = await _facts_under(session, context, Scope.READINGS)
    lines: list[_ToolLine] = []
    for fact in facts:
        date = fact.valid_from.date().isoformat()
        if _is_reading(fact):
            value = fact.value
            text = f"blood pressure {value['systolic']}/{value['diastolic']} on {date}"
        else:
            text = f"{fact.subject} {fact.attribute} = {fact.value} on {date}"
        _register(lines, counter, "fact", fact.id, text)
    return lines, len(facts)


async def _read_visits(
    session: AsyncSession, context: KeyContext, counter: _TokenCounter
) -> tuple[list[_ToolLine], int, list[Appointment], dict[uuid.UUID, Provider]]:
    providers = {p.id: p for p in await audited_read(session, Provider, context, Scope.VISITS)}
    visits = await audited_read(session, Appointment, context, Scope.VISITS)
    lines: list[_ToolLine] = []
    for visit in visits:
        provider = providers.get(visit.provider_id)
        who = provider.name if provider is not None else "an unnamed provider"
        when = visit.scheduled_at.date().isoformat()
        text = f"with {who} on {when}, status {visit.status.value}"
        _register(lines, counter, "appointment", visit.id, text)
    return lines, len(visits), list(visits), providers


async def _read_records(
    session: AsyncSession, context: KeyContext, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    facts = await _facts_under(session, context, Scope.RECORDS)
    lines: list[_ToolLine] = []
    for fact in facts:
        date = fact.valid_from.date().isoformat()
        _register(
            lines, counter, "fact", fact.id, f"{fact.subject} {fact.attribute} = {fact.value} on {date}"
        )
    return lines, len(facts)


async def _read_feelings(
    session: AsyncSession, context: KeyContext, counter: _TokenCounter
) -> tuple[list[_ToolLine], int]:
    notes, _withheld = await recent_notes(session, context=context)
    lines: list[_ToolLine] = []
    for note in notes:
        date = note.created_at.date().isoformat()
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
            proposal.suggested_at.date().isoformat()
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
    if history is None or (not history.recent and not history.summary):
        return ""
    parts = ["\n\nThis is a continuing conversation. Earlier in it:"]
    if history.summary:
        parts.append(f"Summary of earlier turns: {history.summary}")
    for turn in history.recent[-HISTORY_TURNS:]:
        said = "; ".join(turn.answer_lines) or "; ".join(turn.honest) or "nothing was found"
        parts.append(f'He asked: "{turn.question}" — Nura said: {said}')
    parts.append(
        'If this question refers back to something above (e.g. "that", "it", "the same '
        'thing"), resolve it using the above before deciding which tools to call.'
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

    def __init__(self, client: AsyncAnthropic, *, searcher: Searcher) -> None:
        self._client = client
        self._searcher = searcher

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
            return await recall(
                session,
                context=context,
                question=question,
                mode=mode,
                retriever=retriever,
                store=store,
                registry=registry,
                language=language,
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

            answer: Answer | None = None
            repaired = False
            try:
                for _round in range(MAX_ROUNDS):
                    response = await self._client.messages.create(  # type: ignore[call-overload]
                        model=MODEL,
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
                        failed_rules: set[int] = set()
                        parsed = (
                            None
                            if payload is None
                            else _answer_from_payload(
                                payload, known, lang, reader, mode, failed_rules
                            )
                        )
                        if parsed is None and failed_rules and not repaired:
                            # One repair round (defect: "the agent still returns an empty
                            # answer"): tell the model which rules its lines broke — never
                            # what it wrote — and give it one more try before falling back.
                            repaired = True
                            log.info(
                                "claude asker: repair round, rules=%s", sorted(failed_rules)
                            )
                            assistant_content = getattr(response, "content", None) or []
                            messages.append(
                                {"role": "assistant", "content": assistant_content}
                            )
                            hints = "; ".join(
                                _RULE_HINTS.get(rule, f"rule {rule}")
                                for rule in sorted(failed_rules)
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
                        answer = parsed
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

            if answer is None or not answer.lines:
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
                if answer is None or (not answer.lines and not answer.honest):
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
            if _would_change_treatment(text, about_medicine):
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

            for answer_line in answer.lines:
                yield AnswerDelta(text=answer_line.text)
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
    ) -> tuple[list[_ToolLine], int]:
        if name == "read_medicines":
            return await _read_medicines(session, context, registry, language, counter)
        if name == "read_readings":
            return await _read_readings(session, context, language, counter)
        if name == "read_visits":
            lines, count, visits, providers = await _read_visits(session, context, counter)
            visits_seen.extend(visits)
            providers_seen.update(providers)
            return lines, count
        if name == "read_records":
            return await _read_records(session, context, counter)
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


def _plain_words_rules(text: str, language: str) -> tuple[int, ...]:
    """The `docs/plain-words.md` rule numbers `text` fails, sorted — never the text itself.
    Logged by `_drop` and, once per ask, handed to the model as `_RULE_HINTS` for the one
    repair round: which rule, never which words."""
    return tuple(
        sorted({finding.rule for finding in verify(text, language, "line") if finding.severity == "fail"})
    )


def _answer_from_payload(
    payload: Mapping[str, Any],
    known: Mapping[str, _ToolLine],
    language: str,
    reader: Reader,
    mode: Mode,
    failed_rules: set[int] | None = None,
) -> Answer | None:
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list):
        log.info("claude asker: payload had no 'lines' list")
        return None
    # Case-insensitive, so `M1` or `m1 ` matches the `m1` a tool result actually carried —
    # the model is asked to copy a short id back, not retype a uuid, but it still may not get
    # the case exactly right, and a line should not be thrown away over that alone.
    known_ci = {token.strip().lower(): line for token, line in known.items()}
    lines: list[AnswerLine] = []
    for entry in raw_lines:
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
        if not verified(text, language):
            rules = _plain_words_rules(text, language)
            if failed_rules is not None:
                failed_rules.update(rules)
            _drop("plain_words_failed", rules=rules)
            continue
        if _has_conclusion_language(text, language):
            _drop("conclusion_language")
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
        lines.append(AnswerLine(text=heard, cites=cites))
    if not lines:
        log.info(
            "claude asker: no line survived out of %d the model offered", len(raw_lines)
        )
        return None
    kept_lines = lines[:1] if mode is Mode.VOICE else lines[:TEXT_LINES]
    return Answer(
        question_artifact_id=uuid.uuid4(),  # overwritten by the caller with the kept artefact
        mode=mode,
        language=language,
        lines=tuple(kept_lines),
        honest=(),
        boundary=(),
        withheld=(),
        dropped=len(raw_lines) - len(kept_lines),
    )


__all__ = ["ClaudeAsker"]
