"""Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html`, scene
`insight`): the moment a paper is confirmed, Nura connects it to the person's own record —
his medicines, his other results of the same analytes, his next visit — and offers back
questions for the doctor, never advice.

This reuses the Health Analyst's own machinery start to finish, the same gate every weekly
candidate already passes: `app.reasoning.analyst.pipeline.Candidate`/`finalize` is the one
safety check every candidate here goes through too, and a candidate that would touch a
medicine and fails it is rerouted through `app.reasoning.analyst.rule.ask_the_doctor` — the
same reroute the weekly report uses, never a second safety path. The Claude path (`app.
channels.api.analyst`) reuses `app.reasoning.analyst.claude_adapter.ClaudeAnalyst`'s own
`_ask_claude` unchanged to make the one call, but never its `_rebuild`: unlike the weekly
report, which lets the model rephrase, this module's own `choose_from_templates` (#303
review, B1b) reads only which candidate ids the model chose, and their order — never its
`text`/`why_plain` — so a model's own words can never reach this card at all, poisonous or
not. The cite check and the `EXTERNAL_MODEL_PROCESSOR` audit line stay the analyst's own.

Values are compared only with the range printed on the paper itself (`_printed_range`),
never a guideline table: a fact's own embedded `range` where a sibling builder's shape has
landed, else the legacy sibling fact `{attribute}_reference_range` this backend writes today
(`app.llm.prompts.extract_document.txt`) — both shapes are read, so this module does not
care which one is on a given profile.

`read_phase` is the one half of this module that touches the database; it never calls a
model. The caller (`app.channels.api.analyst`) is the one that structures the three short
units of work a stream needs — reads, then the model call with no session open at all, then
the rebuild and the save — so no database transaction is ever open while a model call is in
flight (the defect `app.delivery.feed.background`'s own docstring describes: a synchronous
model call blocking the one event loop, and by extension a connection, for as long as it
takes).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.channels.about_him import Reader
from app.db import as_utc, utcnow
from app.delivery import analyst_strings as words
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.ingestion.extract import parse_printed_range as extract_printed_range
from app.ingestion.models import ReviewCard, ReviewField
from app.ingestion.readings import READING
from app.ingestion.review import card_fields
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.models import Appointment
from app.memory.semantic import current_facts
from app.memory.spine import upcoming_appointments
from app.reasoning.analyst.pipeline import Candidate, finalize
from app.reasoning.analyst.port import AskWho, Confidence, Evidence, Insight, InsightKind
from app.reasoning.analyst.rule import ask_the_doctor
from app.safety.boundary import Surface, boundary_lines

REPORT_KEY = "questions_for_the_doctor"
"""The one section name a *saved* paper-scoped insight carries (`app.reasoning.analyst.
paper_service._section_json`) — cosmetic, read back by `questions_of` alone."""

CANDIDATE_SECTION_KEY = "paper_candidates"
"""The section key `app.channels.api.analyst._paper_events` puts the rule-finalised
candidates under before handing them to `ClaudeAnalyst`'s own `_ask_claude`/`_rebuild`
(`app.reasoning.analyst.claude_adapter`) — deliberately never
`app.reasoning.analyst.rule.QUESTIONS_KEY`: `_rebuild` treats that one key as the weekly
report's own rollup and always skips it, rebuilding it instead from what its other five
sections kept (its own docstring). A paper-scoped run has no other sections to roll up from,
so its own candidates must sit under an ordinary key `_rebuild` actually rebuilds."""


class NotAConfirmedPaper(Refusal):
    """No confirmed paper by this id on this profile — an unconfirmed card and another
    profile's artifact both refuse in these same words (404), the same standing `NoKey`
    already holds to (`app.keys.context`): neither should be told apart by what comes back.
    A key without RECORDS is turned away earlier and differently: `audited_read` requires
    the scope before it ever runs the query, so that case is `OutOfScope` (403), from
    `app.keys.context.KeyContext.require`, never this refusal."""


class PaperStepKey(StrEnum):
    """One real read behind a paper-scoped insight, in the order it happens. No `MEDICINES`
    step this release (#303 review, B2): medicines are not read for this card at all while
    it offers no medicine-linked question — never claim to have looked at something that was
    not actually used."""

    PAPER = "paper"
    HISTORY = "history"
    VISIT = "visit"


@dataclass(frozen=True, slots=True)
class PaperStep:
    key: PaperStepKey
    label: str


@dataclass(frozen=True, slots=True)
class LookedAt:
    kind: str
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class ReadResult:
    """Everything the read phase produced: finalised candidates (`pipeline.finalize` and,
    where a medicine one failed, `ask_the_doctor` already ran), ready either to become the
    insight as-is (rule mode) or to be shown to Claude to choose and rephrase from."""

    paper_label: str
    questions: tuple[Insight, ...]
    looked_at: tuple[LookedAt, ...]
    withheld: tuple[str, ...]


PaperReadEvent = PaperStep | ReadResult


@dataclass(frozen=True, slots=True)
class PaperInsight:
    """The finished, paper-scoped insight: a headline, what was actually read, and 1-4
    questions for the doctor — never a diagnosis, never advice."""

    report_id: str
    generated_at: datetime
    language: str
    source: str
    boundary: tuple[str, ...]
    headline: str
    looked_at: tuple[LookedAt, ...]
    questions: tuple[Insight, ...]
    withheld: tuple[str, ...]


def _parse_printed_range(text: str) -> tuple[float | None, float | None] | None:
    """Delegates to the ingestion extractor's own parser (`app.ingestion.extract.
    parse_printed_range`, #303 review, S2) — never a second parser of the same literal shapes
    that could drift from it or trust what that one already refuses: a low bound over the
    high one ("5.5 - 3.5", printed backwards or misread — this module's own earlier parser
    read that as `(5.5, 3.5)` and called 4.0 "below" it) and a compound or sex-specific range
    both come back with no bounds there, never guessed at here either. `None` — never a tuple
    of `None`s — exactly when neither bound parsed, so `_printed_range`'s own fallback order
    below still tries the next shape; `_printed_range`'s caller already treats a tuple of two
    `None`s the same as this bare `None` either way."""
    parsed = extract_printed_range(text)
    if parsed.low is None and parsed.high is None:
        return None
    return (parsed.low, parsed.high)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _printed_range(
    value: Any, sibling: Any, *, field_range: Mapping[str, Any] | None = None
) -> tuple[float | None, float | None] | None:
    """The range printed beside one value on the paper, in whichever shape this profile's own
    rows carry it — read in this order, the first that answers wins:

    1. `field_range` — `app.ingestion.models.ReviewField.range` (defect #3, #292): `{"low":
       number|null, "high": number|null, "text": string}`, already parsed by the confirm
       flow itself (`app.ingestion.extract.fold_legacy_reference_ranges`), the shape every
       confirm from here on carries. Bounds are read straight off it — never reparsed —
       *unless* neither bound parsed there either (both `None`, an unambiguous or compound
       range the extractor itself could not reduce to numbers); then `text` is tried here
       too, on the chance it is one of this module's own literal shapes after all.
    2. A `range` already embedded on the fact's own `value` (a sibling shape no confirm here
       writes yet, kept for forward compatibness — `{"value": 140, "range": "<130"}`).
    3. The legacy sibling fact this backend wrote before #292 (`{attribute}_reference_range`,
       a plain string) — a card confirmed on an older build, still on someone's record.

    None of the three needs to have landed for the others to work.
    """
    if field_range is not None:
        low, high = _number(field_range.get("low")), _number(field_range.get("high"))
        if low is not None and high is not None and low > high:
            # A backwards range is not a range (#303 re-review, NEW-1): the text path already
            # refuses one (`parse_printed_range`), but these numbers come straight from the
            # reader's JSON, and "5.5 to 3.5" made 4.0 read as BELOW a range it sits inside.
            return None
        if low is not None or high is not None:
            return (low, high)
        text = field_range.get("text")
        if isinstance(text, str):
            parsed = _parse_printed_range(text)
            if parsed is not None:
                return parsed
    if isinstance(value, Mapping) and "range" in value:
        embedded = value.get("range")
        if isinstance(embedded, str):
            return _parse_printed_range(embedded)
        return None
    if isinstance(sibling, str):
        return _parse_printed_range(sibling)
    return None


def _band(value: float, bounds: tuple[float | None, float | None]) -> str | None:
    low, high = bounds
    if low is not None and value < low:
        return "below"
    if high is not None and value > high:
        return "above"
    return None


_DETERMINER_PREFIX: dict[str, tuple[str, ...]] = {"en": ("your ", "the "), "zh": ("您的",)}
_DETERMINER_SUFFIX: dict[str, tuple[str, ...]] = {"ms": (" anda",)}


def _bare_word(plain: str, language: str) -> str:
    """`plain` with whatever determiner it already carries stripped off — a lab value's plain
    label (`words.ANALYTE_PLAIN_LABEL`, mirrored word for word from the web's own report
    table catalogue, "the bad cholesterol", "your body salt") — so a caller's own "my"/
    "{patient}'s" (or the Malay/Chinese equivalent) is never doubled onto it ("my the bad
    cholesterol"). `PAPER_SINGLE_VALUE_*`/`PAPER_AGGREGATE_VALUE` put their own determiner
    around the bare word instead. (No medicine-linked question this release — #303 review,
    B2 — so this no longer also bares a medicine's own plain name; the determiner tables
    above still carry `PLAIN_NAME`'s own shapes too, ready for when one returns.)"""
    for prefix in _DETERMINER_PREFIX.get(language, ()):
        if plain.startswith(prefix):
            return plain[len(prefix) :]
    for suffix in _DETERMINER_SUFFIX.get(language, ()):
        if plain.endswith(suffix):
            return plain[: -len(suffix)]
    return plain


def _analyte_label(subject: str, attribute: str, *, language: str) -> str | None:
    """The plain word for one line of a lab paper — the same word the report table itself
    already shows for it (`words.ANALYTE_PLAIN_LABEL`, mirrored from the web's own report
    table catalogue), never the raw subject/attribute code, and never carrying that
    catalogue's own determiner into a question that supplies its own (`_bare_word`). A code
    with no entry in the closed table is `None` — never the paper's own printed
    `ReviewField.label_on_paper` (#303 review, S1: extractor-written free text, hostile or
    jargon until a person has read it — "Apo-B ratio" printed verbatim would have gone
    straight onto the card and the visit card). A value with no plain word still counts
    toward the aggregate "{n} of my numbers…" question, which names no label at all — only
    the single-value question about that one value is left out."""
    table = words.ANALYTE_PLAIN_LABEL.get(language, words.ANALYTE_PLAIN_LABEL["en"])
    plain = table.get((subject, attribute))
    return _bare_word(plain, language) if plain else None


def _render(
    self_template: Mapping[str, str],
    theirs_template: Mapping[str, str],
    *,
    reader: Reader,
    language: str,
    **slots: object,
) -> str:
    """One of the card's own first-person questions, in the voice this key actually reads in
    — his own key gets `self_template` unchanged ("my", "I", "me"); anyone else's gets
    `theirs_template` with his name in `{patient}` — chosen here, explicitly, rather than left
    to `app.channels.about_him`'s generic pass: that pass only ever swaps a line that already
    says "you"/"your" (`TO_HIM`), which a first-person line never does (module docstring)."""
    if reader.his:
        return words.fill(self_template[language], **slots)
    return words.fill(theirs_template[language], patient=reader.name, **slots)


async def _confirmed_paper(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID
) -> ReviewCard:
    """The confirmed review card for this artifact, on this profile — or `NotAConfirmedPaper`
    for an unconfirmed card, another profile's artifact, or a key without RECORDS: all three
    read the same way an `audited_read` under RECORDS scoped to this profile already reads
    them, so none is told apart from another (`NoKey`'s own reasoning)."""
    found = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.artifact_id == artifact_id,),
    )
    confirmed = [card for card in found if not card.is_open]
    if not confirmed:
        raise NotAConfirmedPaper(
            f"no confirmed paper {artifact_id} on profile {context.profile_id}"
        )
    return confirmed[0]


def _page_of(fields: Sequence[ReviewField], *, subject: str, attribute: str) -> int | None:
    for field in fields:
        if field.subject == subject and field.attribute == attribute:
            span = field.span
            if isinstance(span, Mapping):
                page = span.get("page")
                if isinstance(page, int):
                    return page
    return None


def _field_range_of(
    fields: Sequence[ReviewField], *, subject: str, attribute: str
) -> Mapping[str, Any] | None:
    """The matching `ReviewField.range` (defect #3, #292: `{"low", "high", "text"}`), the
    range as the confirm flow itself already parsed it off the paper — read here rather than
    reparsed, the current, primary shape `_printed_range` prefers."""
    for field in fields:
        if field.subject == subject and field.attribute == attribute and isinstance(field.range, Mapping):
            return field.range
    return None


def _evidence_label(paper_label: str, page: int | None) -> str:
    return f"{paper_label} (page {page})" if page is not None else paper_label


@dataclass(frozen=True, slots=True)
class _FlaggedValue:
    """One value on this paper found outside its own printed range — never compared with a
    guideline table, only the range printed on this paper itself."""

    fact_id: uuid.UUID
    subject: str
    attribute: str
    band: str
    """`"above"` or `"below"` — `_band`'s own two words."""
    label: str | None
    """The plain word for this line (`_analyte_label`), or `None` when this surface has
    neither a plain word for the code nor a label printed on the paper for it — a value this
    still counts toward "how many are outside range", but is never named by its raw code."""
    page: int | None


def _value_evidence(
    paper_label: str, artifact_id: uuid.UUID, flagged: _FlaggedValue
) -> tuple[Evidence, ...]:
    return (
        Evidence(
            kind="fact",
            id=str(flagged.fact_id),
            label=flagged.label or paper_label,
            scope=Scope.RECORDS,
        ),
        Evidence(
            kind="artifact",
            id=str(artifact_id),
            label=_evidence_label(paper_label, flagged.page),
            scope=Scope.RECORDS,
        ),
    )


async def _flagged_values(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    moment: datetime,
    language: str,
) -> list[_FlaggedValue]:
    """Every value on this paper found outside its own printed range, in the order the paper
    prints its fields.

    A paper can carry more than one kind of fact — a lab row under RECORDS beside a vital
    the confirm route turned into a READINGS reading (`app.ingestion.review`, the module
    doc's own example) — so each subject is read only where this key holds the scope it
    sits under (`scope_for_subject`); a subject outside the key's scopes is skipped, never a
    reason to refuse the whole insight."""
    fields = await card_fields(session, context=context, card_id=card.id)
    subjects = sorted(
        {
            field.subject
            for field in fields
            if context.allows(scope_for_subject(field.subject))
        }
    )
    flagged: list[_FlaggedValue] = []
    seen_facts: set[tuple[uuid.UUID, str]] = set()
    for subject in subjects:
        facts = await current_facts(session, context=context, subject=subject, at=moment)
        by_attribute = {fact.attribute: fact for fact in facts if fact.artifact_id == card.artifact_id}
        for attribute, fact in by_attribute.items():
            if attribute.endswith(("_reference_range", "_flagged", "_date")):
                continue
            # A vital on a lab paper is not a plain number: the confirm route folds it into ONE
            # reading fact, `attribute="reading"`, `value={"glucose": 19}` (or the pair of a
            # blood pressure) — `app.ingestion.review._write_lab_readings`. Read as a plain
            # number it was skipped in silence, and a paper whose only out-of-range value was a
            # sugar of 19 against a printed <6.0 said "Nothing on this paper looks worth a
            # question" (#303 re-review, NEW-2). Each key of a reading is the field's own
            # attribute under the same subject, so its printed range and label are found there.
            if attribute == READING and isinstance(fact.value, Mapping):
                measured = [(key, _number(each)) for key, each in fact.value.items()]
            else:
                measured = [(attribute, _number(fact.value))]
            for key, number in measured:
                if number is None or (fact.id, key) in seen_facts:
                    continue
                sibling = by_attribute.get(f"{key}_reference_range")
                field_range = _field_range_of(fields, subject=subject, attribute=key)
                bounds = _printed_range(
                    fact.value if key == attribute else number,
                    sibling.value if sibling is not None else None,
                    field_range=field_range,
                )
                if bounds is None or (bounds[0] is None and bounds[1] is None):
                    continue
                band = _band(number, bounds)
                if band is None:
                    continue
                seen_facts.add((fact.id, key))
                page = _page_of(fields, subject=subject, attribute=key)
                label = _analyte_label(subject, key, language=language)
                flagged.append(
                    _FlaggedValue(
                        fact_id=fact.id, subject=subject, attribute=key, band=band, label=label, page=page
                    )
                )
    return flagged


def _value_candidate(
    flagged: Sequence[_FlaggedValue],
    *,
    artifact_id: uuid.UUID,
    paper_label: str,
    reader: Reader,
    language: str,
) -> Candidate | None:
    """The card's own first question: one out-of-range value asks about that value by name;
    several ask, once, how many — never a question per value (the blueprint's own card asks
    about "four of my numbers", not four separate lines)."""
    if not flagged:
        return None
    why = _render(words.PAPER_VALUE_WHY, words.PAPER_VALUE_WHY_THEIRS, reader=reader, language=language)
    if len(flagged) == 1:
        only = flagged[0]
        if only.label is None:
            return None
        above = only.band == "above"
        template = words.PAPER_SINGLE_VALUE_ABOVE if above else words.PAPER_SINGLE_VALUE_BELOW
        template_theirs = (
            words.PAPER_SINGLE_VALUE_ABOVE_THEIRS if above else words.PAPER_SINGLE_VALUE_BELOW_THEIRS
        )
        text = _render(template, template_theirs, reader=reader, language=language, label=only.label)
        evidence = _value_evidence(paper_label, artifact_id, only)
        insight_id = f"paper_value:{only.fact_id}"
    else:
        text = _render(
            words.PAPER_AGGREGATE_VALUE, words.PAPER_AGGREGATE_VALUE_THEIRS,
            reader=reader, language=language, n=len(flagged),
        )
        evidence = tuple(e for one in flagged for e in _value_evidence(paper_label, artifact_id, one))
        insight_id = f"paper_values:{artifact_id}"
    return Candidate(
        insight_id=insight_id,
        kind=InsightKind.CHECK,
        text=text,
        ask_who=AskWho.DOCTOR,
        evidence=evidence,
        why_plain=why,
        confidence=Confidence.WORTH_A_LOOK,
    )


def _retest_candidate(
    flagged: Sequence[_FlaggedValue], *, artifact_id: uuid.UUID, paper_label: str, language: str
) -> Candidate | None:
    """The card's own closing question — always, once anything at all is outside range. Names
    no person, so the same line serves either voice (`PAPER_RETEST_QUESTION` carries no
    `_THEIRS` twin)."""
    if not flagged:
        return None
    evidence = tuple(
        Evidence(kind="fact", id=str(one.fact_id), label=one.label or paper_label, scope=Scope.RECORDS)
        for one in flagged
    )
    return Candidate(
        insight_id=f"paper_retest:{artifact_id}",
        kind=InsightKind.CHECK,
        text=words.PAPER_RETEST_QUESTION[language],
        ask_who=AskWho.DOCTOR,
        evidence=evidence,
        why_plain=words.PAPER_REPEAT_WHY[language],
        confidence=Confidence.WORTH_A_LOOK,
    )


async def read_phase(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    language: str,
    reader: Reader,
    registry: DrugRegistry | None = None,
    now: datetime | None = None,
) -> Any:
    """An async generator: a `PaperStep` the instant each real read finishes, then one
    `ReadResult`, last. Never calls a model — see the module docstring. `reader` is the same
    one the caller already resolved (`app.channels.about_him.reader_of`) to say a step's own
    label about him or not; the card's own first-person questions need it too, to choose
    between "my"/"I" and his name explicitly rather than leaving it to the generic pass that
    resolves everything else here (`_render`'s own docstring)."""
    moment = now if now is not None else utcnow()
    card = await _confirmed_paper(session, context=context, artifact_id=artifact_id)
    paper_label = words.LOOKED_AT_LABEL[language]["paper"]
    yield PaperStep(PaperStepKey.PAPER, words.PAPER_STEP_LABEL[language]["paper"])

    looked_at = [LookedAt(kind="artifact", id=str(artifact_id), label=paper_label)]
    withheld: list[str] = []

    flagged = await _flagged_values(session, context=context, card=card, moment=moment, language=language)
    yield PaperStep(PaperStepKey.HISTORY, words.PAPER_STEP_LABEL[language]["history"])

    next_visit: Appointment | None = None
    if context.allows(Scope.VISITS):
        upcoming = await upcoming_appointments(session, context=context, at=moment)
        ordered = sorted(upcoming, key=lambda visit: (as_utc(visit.scheduled_at), str(visit.id)))
        next_visit = ordered[0] if ordered else None
        yield PaperStep(PaperStepKey.VISIT, words.PAPER_STEP_LABEL[language]["visit"])
        if next_visit is not None:
            looked_at.append(
                LookedAt(
                    kind="appointment",
                    id=str(next_visit.id),
                    label=words.LOOKED_AT_LABEL[language]["visit"],
                )
            )

    candidates: list[Candidate] = []
    value_candidate = _value_candidate(
        flagged, artifact_id=artifact_id, paper_label=paper_label, reader=reader, language=language
    )
    if value_candidate is not None:
        candidates.append(value_candidate)
    # No medicine-linked question this release (#303 review, B2): `ANALYTE_DRUG_CLASS_HINTS`
    # is this module's own heuristic, never a pharmacist-reviewed mapping, and it fired for a
    # value's own band without regard to which way the medicine actually pushes it — a
    # potassium reading BELOW range beside an antihypertensive read as "is your blood
    # pressure tablet still right", which a person could act on by skipping a dose. Returns
    # only when a pharmacist-reviewed analyte-to-medicine mapping exists.
    retest_candidate = _retest_candidate(
        flagged, artifact_id=artifact_id, paper_label=paper_label, language=language
    )
    if retest_candidate is not None:
        candidates.append(retest_candidate)

    async def reroute(candidate: Candidate) -> Insight | None:
        return await ask_the_doctor(session, context, language, candidate)

    questions = [
        insight
        for candidate in candidates
        if (insight := await finalize(candidate, language=language, reroute=reroute)) is not None
    ]

    yield ReadResult(
        paper_label=paper_label,
        questions=tuple(questions),
        looked_at=tuple(looked_at),
        withheld=tuple(withheld),
    )


class _ModelChosenId(Protocol):
    """What a model's own choice needs to carry for `choose_from_templates` to use it — its
    `insight_id` alone (`app.reasoning.analyst.claude_adapter._ModelChoice` satisfies this
    without either module importing the other at load time; `choose_from_templates` never
    reads `.text`/`.why_plain` off it, on purpose — see its own docstring). A read-only
    `@property`, not a plain attribute: a plain annotation asks a frozen dataclass like
    `_ModelChoice` for a setter it deliberately does not have."""

    @property
    def insight_id(self) -> str: ...


def choose_from_templates(
    original: Sequence[Insight], choices: Sequence[_ModelChosenId]
) -> list[Insight]:
    """The model may CHOOSE which of the card's own, already-verified, closed-template
    questions to keep, and their order — never rewrite one. Unlike the weekly report's own
    `claude_adapter._rebuild`, a choice's `text`/`why_plain` are never read here at all: every
    returned `Insight` is one `read_phase` itself already built and ran through `finalize`,
    untouched (#303 review — a model that could put its own words into a paper's own
    questions could put a dose change into one; this is the fix, not tighter wording).

    A duplicated id keeps only its first appearance; an id `original` never offered is
    dropped; with fewer than one id left after that, the rule-based selection — every
    question `read_phase` found, in its own order — is kept instead of an empty card."""
    by_id = {insight.insight_id: insight for insight in original}
    seen: set[str] = set()
    selected: list[Insight] = []
    for choice in choices:
        if choice.insight_id in seen or choice.insight_id not in by_id:
            continue
        seen.add(choice.insight_id)
        selected.append(by_id[choice.insight_id])
    return selected if selected else list(original)


_KIND_CODE_BY_PREFIX: dict[str, str] = {
    "paper_value": "value",
    "paper_values": "aggregate",
    "paper_retest": "retest",
}
"""The closed vocabulary `sanitized_for_model` reads an insight's own id prefix into — every
prefix `_value_candidate`/`_retest_candidate` actually mint (`f"paper_value:{fact_id}"`,
`f"paper_values:{artifact_id}"`, `f"paper_retest:{artifact_id}"`)."""


def sanitized_for_model(insight: Insight) -> Insight:
    """The same insight, `text`/`why_plain` replaced by a closed kind code — never the
    rendered sentence, which could carry the patient's real name (caregiver voice, `_render`
    bakes it in at candidate-build time), a value, a date or a plain-language label (#303
    review, S3). The model is asked only to choose which of these to keep and in what order
    (`choose_from_templates`); it never needs the words themselves to do that, so it is never
    shown them. `insight_id`/`kind`/`evidence`/`ask_who`/`confidence` are unchanged — the
    prompt `app.reasoning.analyst.claude_adapter.ClaudeAnalyst._ask_claude` builds from an
    `Insight` already sends only `evidence.id`, never `evidence.label`, so those are safe as
    they are."""
    code = _KIND_CODE_BY_PREFIX.get(insight.insight_id.split(":", 1)[0], "question")
    return Insight(
        insight_id=insight.insight_id,
        kind=insight.kind,
        text=code,
        ask_who=insight.ask_who,
        evidence=insight.evidence,
        why_plain=code,
        confidence=insight.confidence,
    )


def build_insight(
    *,
    language: str,
    source: str,
    questions: Sequence[Insight],
    looked_at: Sequence[LookedAt],
    withheld: Sequence[str],
    now: datetime,
    reader: Reader,
) -> PaperInsight:
    """`reader` is the same one `read_phase` already resolved (#303 review, S4ii — its own
    absence here was the bug: `PAPER_HEADLINE_THEIRS`/`PAPER_NOTHING_LINE_THEIRS` existed and
    were never reachable, so a caregiver's own headline read "Here is what I would ask." —
    his own first-person voice — never naming the patient at all)."""
    headline = (
        _render(words.PAPER_HEADLINE, words.PAPER_HEADLINE_THEIRS, reader=reader, language=language)
        if questions
        else _render(words.PAPER_NOTHING_LINE, words.PAPER_NOTHING_LINE_THEIRS, reader=reader, language=language)
    )
    return PaperInsight(
        report_id=str(uuid.uuid4()),
        generated_at=now,
        language=language,
        source=source,
        boundary=boundary_lines(Surface.INSIGHT, language, doctor=None),
        headline=headline,
        looked_at=tuple(looked_at),
        questions=tuple(questions[:4]),
        withheld=tuple(withheld),
    )


__all__ = [
    "CANDIDATE_SECTION_KEY",
    "REPORT_KEY",
    "LookedAt",
    "NotAConfirmedPaper",
    "PaperInsight",
    "PaperReadEvent",
    "PaperStep",
    "PaperStepKey",
    "ReadResult",
    "build_insight",
    "choose_from_templates",
    "read_phase",
    "sanitized_for_model",
]
