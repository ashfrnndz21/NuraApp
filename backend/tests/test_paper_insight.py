"""Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html`, scene
`insight`): the paper-scoped insight (`app.reasoning.analyst.paper`) and keeping its offered
questions on a visit (`app.reasoning.visits.questions.keep_paper_insight_questions`).

Mocked throughout — no live model call, no API key: `RuleAnalyst`'s own candidate machinery
(`app.reasoning.analyst.pipeline.finalize`, `app.reasoning.analyst.rule.ask_the_doctor`) is
reused unchanged, and the Claude path is exercised the same way
`tests/test_analyst_claude.py` exercises `ClaudeAnalyst`: a fake `anthropic` client.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.about_him import Reader
from app.delivery import analyst_strings as words
from app.drugs.fixture import FixtureRegistry
from app.ingestion.objects import LocalObjectStore
from app.keys.scopes import KeyRole, Scope
from app.reasoning.analyst.claude_adapter import ClaudeAnalyst
from app.reasoning.analyst.paper import (
    CANDIDATE_SECTION_KEY,
    NotAConfirmedPaper,
    ReadResult,
    _FlaggedValue,
    build_insight,
    read_phase,
)
from app.reasoning.analyst.paper import _analyte_label as analyte_label
from app.reasoning.analyst.paper import _render as render_question
from app.reasoning.analyst.paper import _value_candidate as value_candidate
from app.reasoning.analyst.pipeline import blocked
from app.reasoning.analyst.port import AskWho, InsightKind, Report, Section
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.questions import (
    current_questions,
    keep_paper_insight_questions,
    patient_card,
)
from app.safety.plain_words import verify
from tests.conftest import Deployment
from tests.medicines_support import add as add_medicine
from tests.medicines_support import label
from tests.paper import LAB_REPORT_NOT_HIS, LAB_REPORT_VITALS, LIPID_GLUCOSE_PANEL, LIPID_PANEL, LIPID_PANEL_2025
from tests.safety_support import clinic, let_in, pa
from tests.test_ingestion import _card, _decide, _yes
from tests.timeline_support import book

REGISTRY = FixtureRegistry.load()


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    from app.regions import Region

    return LocalObjectStore(tmp_path, Region.SG)


@pytest.fixture
def extractor():
    from app.ingestion.extract import FixtureExtractor
    from tests.paper import PAPER

    return FixtureExtractor(PAPER)


async def _confirm_paper(session, context, store, extractor, paper_label=LAB_REPORT_VITALS):
    """A confirmed review card for one lab paper, the artifact it names — the shape
    `_confirmed_paper` (`app.reasoning.analyst.paper`) needs to run at all."""
    card, fields = await _card(session, context, store, extractor, paper_label)
    decisions = _decide(fields)
    yes = await _yes(session, context, card, decisions)
    from app.ingestion.review import confirm_review_card

    card, _decided, _facts = await confirm_review_card(
        session, context=context, card_id=card.id, decisions=decisions, confirmation_id=yes
    )
    return card


AFTER_THE_PAPER = datetime(2026, 9, 21, tzinfo=UTC)
"""After every paper fixture's own document date (10-13 September 2026) and after the
suite's frozen clock (3 September 2026, `tests/conftest.FROZEN_AT`): `current_facts` only
returns a fact whose `valid_from` has arrived by `now`, so a paper-scoped read needs its own
`now` past the paper's date, the same way `tests/timeline_support.book` books a visit ahead
of it rather than behind."""


async def _drain(
    session: AsyncSession, context, artifact_id, *, language: str = "en", registry=None, reader: Reader | None = None
) -> ReadResult:
    result: ReadResult | None = None
    async for event in read_phase(
        session,
        context=context,
        artifact_id=artifact_id,
        language=language,
        reader=reader or Reader(his=True),
        registry=registry,
        now=AFTER_THE_PAPER,
    ):
        if isinstance(event, ReadResult):
            result = event
    assert result is not None
    return result


# --- the happy path: an out-of-range value beside a related medicine -----------------------


async def test_an_out_of_range_value_offers_the_cards_own_two_questions(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """`LAB_REPORT_VITALS` has exactly one out-of-range value (LDL, above) — the blueprint's
    card, two real questions: the value and the retest closer, in that order, first person,
    never a dose or a verdict. No medicine-linked question this release (#303 review, B2):
    `add_medicine` below is still seeded to prove the card never mentions it — medicines are
    not read for this card at all, so the analyst.rule the medicine used to be linked through
    can never fire a third question, dormant or otherwise."""
    owner = await pa(sg, phone="+6591160001")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)

    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)

    assert len(result.questions) == 2, [q.text for q in result.questions]
    value, retest = result.questions

    assert value.kind is InsightKind.CHECK
    assert value.ask_who is AskWho.DOCTOR
    assert value.text == "Why is my bad cholesterol above the range on this paper?"
    value_kinds = {e.kind for e in value.evidence}
    assert {"fact", "artifact"} <= value_kinds
    artifact_evidence = next(e for e in value.evidence if e.kind == "artifact")
    assert artifact_evidence.id == str(card.artifact_id)

    assert retest.kind is InsightKind.CHECK
    assert retest.text == words.PAPER_RETEST_QUESTION["en"]

    # No dose, no verdict, no medicine named — real questions worth asking, never advice.
    for question in result.questions:
        lowered = question.text.lower()
        for word in ("should i", "you should", "stop", "start", "change the", "high", "low", "normal", "atorvastatin", "tablet", "medicine"):
            assert word not in lowered, question.text
    # "Looked at" names only the paper and the visit — never the medicines this card no
    # longer reads at all (a real read, never claimed just because it happened elsewhere).
    kinds_seen = {one.kind for one in result.looked_at}
    assert "artifact" in kinds_seen
    assert "medicines" not in kinds_seen
    assert not result.withheld


async def test_two_or_more_out_of_range_values_ask_once_how_many_never_one_question_each(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """`LIPID_GLUCOSE_PANEL` carries several values outside their own printed ranges — the
    card still asks about them once, together, never one line a value (the blueprint's own
    card: "Four of my numbers are above the range on this paper.", not four separate lines)."""
    owner = await pa(sg, phone="+6591160019")
    card = await _confirm_paper(sg, owner, store, extractor, LIPID_GLUCOSE_PANEL)

    result = await _drain(sg, owner, card.artifact_id)

    value = result.questions[0]
    assert value.kind is InsightKind.CHECK
    match = re.fullmatch(r"Why are (\d+) of my numbers outside the range on this paper\?", value.text)
    assert match, value.text
    n = int(match.group(1))
    assert n >= 2, "the fixture's own point: several flagged values, not just one"
    # One retest closer, still — never one per value.
    assert sum(1 for q in result.questions if q.text == words.PAPER_RETEST_QUESTION["en"]) == 1
    # Every flagged value's own fact is cited, even though none is named individually.
    fact_ids = {e.id for q in result.questions for e in q.evidence if e.kind == "fact"}
    assert len(fact_ids) >= n


# --- every question, every real label, every language, both voices: never a doubled ----------
# determiner, never blocked -------------------------------------------------------------------

_DOUBLED_DETERMINER_EN = ("my the", "my your", "the the", "your your", "the your", "your the")
_THEIRS_SUFFIX_EN = ("'s the", "'s your")
_VOICES = (Reader(his=True), Reader(his=False, name="Pa"))


def _assert_never_doubled(text: str, language: str) -> None:
    """`words.ANALYTE_PLAIN_LABEL` and `PLAIN_NAME` both carry the real catalogue's own
    determiner ("the bad cholesterol", "your insulin", "ujian gula anda", "您的血糖检查") —
    `_bare_word` (`app.reasoning.analyst.paper`) strips it before a template ever puts its own
    "my"/"{patient}'s" around the bare word, so composing the two never reads "my the bad
    cholesterol" or "my your insulin". This is the one, general check for that, in every
    language: self voice never says "the"/"your" twice over ("my the", "my your", "the the",
    "your your" and the transposed pair); caregiver voice never says "the"/"your" straight
    after the patient's own possessive ("Pa's the", "Pa's your") — and MS/ZH never say "anda"/
    "您的"/"你的" at all here, self or caregiver, since neither voice this module ever renders
    ("saya"/"{patient}", "我的"/"{patient}的") is the second-person "anda"/"您的" to begin
    with — its mere presence is itself proof a determiner from the source catalogue leaked
    through unstripped."""
    lowered = text.lower()
    if language == "en":
        for pair in _DOUBLED_DETERMINER_EN:
            assert pair not in lowered, (pair, text)
        for suffix in _THEIRS_SUFFIX_EN:
            assert suffix not in lowered, (suffix, text)
    elif language == "ms":
        assert "anda" not in lowered, text
    elif language == "zh":
        assert "您的" not in text and "你的" not in text, text


def _assert_clean(text: str, language: str) -> None:
    _assert_never_doubled(text, language)
    findings = [f for f in verify(text, language, "line") if f.severity != "note"]
    assert not findings, (text, [str(f) for f in findings])
    assert not blocked(text, language), text


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_every_value_question_with_every_real_label_never_doubles_its_determiner(
    language: str,
) -> None:
    """Every plain label the catalogue actually carries (`words.ANALYTE_PLAIN_LABEL`), through
    the exact same composition `_value_candidate` uses (`_analyte_label`, `_render`), in both
    voices, for both "above" and "below" — plain-words' own `line` profile and the conclusion-
    and-advice blocklist, both green, and never a doubled determiner (#303's own follow-up:
    the coordinator's own catch, "my the bad cholesterol")."""
    for subject, attribute in words.ANALYTE_PLAIN_LABEL[language]:
        label = analyte_label(subject, attribute, language=language)
        assert label is not None
        for reader in _VOICES:
            for above, self_t, theirs_t in (
                (True, words.PAPER_SINGLE_VALUE_ABOVE, words.PAPER_SINGLE_VALUE_ABOVE_THEIRS),
                (False, words.PAPER_SINGLE_VALUE_BELOW, words.PAPER_SINGLE_VALUE_BELOW_THEIRS),
            ):
                text = render_question(self_t, theirs_t, reader=reader, language=language, label=label)
                _assert_clean(text, language)


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_the_aggregate_and_retest_questions_are_clean_in_every_language_and_voice(
    language: str,
) -> None:
    for reader in _VOICES:
        text = render_question(
            words.PAPER_AGGREGATE_VALUE, words.PAPER_AGGREGATE_VALUE_THEIRS,
            reader=reader, language=language, n=3,
        )
        _assert_clean(text, language)
    _assert_clean(words.PAPER_RETEST_QUESTION[language], language)


def test_analyte_label_is_closed_table_only_never_the_papers_own_printed_text() -> None:
    """A planted `label_on_paper` — the extractor's own free text, exactly the "Apo-B ratio"
    the #303 review named — must never surface as a question's own plain word: an attribute
    with no entry in `words.ANALYTE_PLAIN_LABEL` is `None`, whatever the paper happens to
    print beside it (S1). `_analyte_label`'s own signature no longer even takes a
    `label_on_paper` — there is nothing left for a caller to plant it into."""
    for language in ("en", "ms", "zh"):
        assert analyte_label("lipid_panel", "other", language=language) is None
        assert analyte_label("liver_panel", "made_up_code", language=language) is None


def test_a_flagged_value_with_no_plain_label_is_left_out_of_the_single_question_but_still_counts_toward_the_aggregate() -> None:
    """A value outside its own printed range whose code carries no plain word (a planted
    `label_on_paper` of "Apo-B", never surfaced) is dropped from the single-value question —
    `_value_candidate` returns `None` for it alone — but still counts toward the aggregate
    "N of my numbers…" question, which names no label at all, once a second, plain-labelled
    value joins it."""
    unlabelled = _FlaggedValue(
        fact_id=uuid.uuid4(), subject="lipid_panel", attribute="other", band="above", label=None, page=1
    )
    labelled = _FlaggedValue(
        fact_id=uuid.uuid4(), subject="lipid_panel", attribute="ldl", band="above", label="bad cholesterol", page=1
    )
    artifact_id = uuid.uuid4()
    reader = Reader(his=True)

    alone = value_candidate([unlabelled], artifact_id=artifact_id, paper_label="this paper", reader=reader, language="en")
    assert alone is None

    together = value_candidate(
        [unlabelled, labelled], artifact_id=artifact_id, paper_label="this paper", reader=reader, language="en"
    )
    assert together is not None
    assert together.text == "Why are 2 of my numbers outside the range on this paper?"
    assert "apo" not in together.text.lower()
    # Both facts are still cited, even though only one is named.
    fact_ids = {e.id for e in together.evidence if e.kind == "fact"}
    assert fact_ids == {str(unlabelled.fact_id), str(labelled.fact_id)}


async def test_a_paper_with_no_printed_range_has_nothing_worth_asking(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """`LIPID_PANEL` carries no `_reference_range` sibling on any of its rows: nothing to
    compare against, so nothing is worth asking — said honestly, never padded."""
    owner = await pa(sg, phone="+6591160002")
    card = await _confirm_paper(sg, owner, store, extractor, LIPID_PANEL)

    result = await _drain(sg, owner, card.artifact_id)
    assert result.questions == ()
    insight = build_insight(
        language="en",
        source="rule",
        questions=result.questions,
        looked_at=result.looked_at,
        withheld=result.withheld,
        now=datetime(2026, 9, 21, tzinfo=UTC),
        reader=Reader(his=True),
    )
    assert insight.headline == words.PAPER_NOTHING_LINE["en"]


async def test_build_insight_says_the_headline_in_the_readers_own_voice(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """#303 review, S4ii: `build_insight` used to take no `reader` at all, so
    `PAPER_HEADLINE_THEIRS`/`PAPER_NOTHING_LINE_THEIRS` were dead code and a caregiver's own
    headline always read "Here is what I would ask." — his own first-person voice, never
    naming the patient. `reader` now chooses explicitly, the same way `_render` already does
    for every question on the card."""
    owner = await pa(sg, phone="+6591160022")
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    assert result.questions

    self_voiced = build_insight(
        language="en", source="rule", questions=result.questions, looked_at=result.looked_at,
        withheld=result.withheld, now=datetime(2026, 9, 21, tzinfo=UTC), reader=Reader(his=True),
    )
    assert self_voiced.headline == words.PAPER_HEADLINE["en"]

    caregiver_voiced = build_insight(
        language="en", source="rule", questions=result.questions, looked_at=result.looked_at,
        withheld=result.withheld, now=datetime(2026, 9, 21, tzinfo=UTC),
        reader=Reader(his=False, name="Pa"),
    )
    assert caregiver_voiced.headline == "Here is what I would ask about Pa's *paper.*"
    assert caregiver_voiced.headline != self_voiced.headline

    # And the "nothing to ask" headline, in both voices too.
    empty_self = build_insight(
        language="en", source="rule", questions=(), looked_at=result.looked_at,
        withheld=result.withheld, now=datetime(2026, 9, 21, tzinfo=UTC), reader=Reader(his=True),
    )
    assert empty_self.headline == words.PAPER_NOTHING_LINE["en"]
    empty_theirs = build_insight(
        language="en", source="rule", questions=(), looked_at=result.looked_at,
        withheld=result.withheld, now=datetime(2026, 9, 21, tzinfo=UTC),
        reader=Reader(his=False, name="Pa"),
    )
    assert empty_theirs.headline == words.PAPER_NOTHING_LINE_THEIRS["en"].format(patient="Pa")


# --- refusals: an unconfirmed card, another profile's artifact -----------------------------


async def test_an_unconfirmed_card_is_refused(sg: AsyncSession, store: LocalObjectStore, extractor) -> None:
    owner = await pa(sg, phone="+6591160003")
    card, _fields = await _card(sg, owner, store, extractor, LAB_REPORT_VITALS)  # never confirmed

    with pytest.raises(NotAConfirmedPaper):
        await _drain(sg, owner, card.artifact_id)


async def test_a_set_aside_card_is_refused_never_narrated(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """B2, the independent safety review's own worst finding: `_confirmed_paper` used to read
    `not card.is_open`, which is `True` for a card set aside on its own whose-paper question
    exactly as it is for one never said yes to at all — so a stranger's paper, rejected with
    "someone else's", could still be read into an insight and narrated as his own. Proven
    directly: confirm his own first paper (so the record holds a confirmed birth year to
    mismatch against), read a demo-style paper that mismatches it, answer "someone else's",
    and assert the insight route refuses it exactly as an unconfirmed card is refused —
    never narrates a line from it."""
    from app.ingestion.review import answer_review_card_question

    owner = await pa(sg, phone="+6591160006")
    await _confirm_paper(sg, owner, store, extractor, LIPID_PANEL_2025)
    card, _fields = await _card(sg, owner, store, extractor, LAB_REPORT_NOT_HIS)
    assert card.awaiting_answer and card.pending_question is not None

    answered = await answer_review_card_question(
        sg, context=owner, card_id=card.id, value="someone_elses"
    )
    assert answered.is_set_aside and not answered.is_confirmed

    with pytest.raises(NotAConfirmedPaper):
        await _drain(sg, owner, card.artifact_id)


async def test_another_profiles_artifact_is_refused(sg: AsyncSession, store: LocalObjectStore, extractor) -> None:
    owner = await pa(sg, phone="+6591160004")
    stranger = await pa(sg, phone="+6591160005")
    card = await _confirm_paper(sg, owner, store, extractor)

    with pytest.raises(NotAConfirmedPaper):
        await _drain(sg, stranger, card.artifact_id)


# --- a key without MEDICINES: no different from one with it — medicines are not read at all,
# for any key, now that no question is ever linked to one (#303 review, B2) --------------------


async def test_a_key_without_medicines_still_gets_the_full_insight_since_medicines_are_never_read(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160006")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)

    viewer = await let_in(
        sg, owner, phone="+6591160007", name="Mei", role=KeyRole.VIEWER,
        scopes={Scope.RECORDS, Scope.VISITS},
    )

    result = await _drain(sg, viewer, card.artifact_id, registry=REGISTRY)
    # Medicines are not read for this card at all any more, so a key without that scope is
    # never told anything was withheld — there is nothing this card ever reads there to deny.
    assert "medicines_and_supplements" not in result.withheld
    assert result.questions
    assert all(q.kind is not InsightKind.MEDICINE for q in result.questions)
    assert not any(e.kind == "medication_line" for q in result.questions for e in q.evidence)
    assert not any(one.kind == "medicines" for one in result.looked_at)


# --- keep: idempotent, on the next visit ----------------------------------------------------


async def test_keep_is_idempotent_and_lands_on_the_next_visit(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160009")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    assert result.questions

    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, datetime(2026, 10, 1, 10, 0, tzinfo=UTC), "check-up")

    first = await keep_paper_insight_questions(
        sg, context=owner, appointment_id=visit.id, artifact_id=card.artifact_id,
        insights=result.questions,
    )
    assert len(first) == len(result.questions)

    second = await keep_paper_insight_questions(
        sg, context=owner, appointment_id=visit.id, artifact_id=card.artifact_id,
        insights=result.questions,
    )
    assert second == []  # nothing new: keeping twice never duplicates

    # Every kept question is verified again on the way out (`patient_card`'s own docstring),
    # in its default `line` profile — one idea, at most fifteen words. A candidate that only
    # passed the pipeline's own gate as two sentences would be refused here (`NotPlainEnough`);
    # this is the real, once-round-trip proof that never happens for these.
    card_lines = await patient_card(sg, context=owner, appointment_id=visit.id)
    for question in result.questions:
        assert question.text in card_lines

    current = await current_questions(sg, context=owner, appointment_id=visit.id)
    assert len([q for q in current if q.source_kind == "paper_insight"]) == len(result.questions)


# --- the Claude adapter path: a fake client, reusing the analyst's own machinery -----------


@dataclass
class FakeMessage:
    content: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def _text_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "text", "text": json.dumps(payload)}


def _temp_report(result: ReadResult, *, language: str = "en") -> Report:
    return Report(
        report_id=str(uuid.uuid4()),
        generated_at=datetime(2026, 9, 21, tzinfo=UTC),
        week_of=datetime(2026, 9, 21, tzinfo=UTC).date(),
        language=language,
        source="rule",
        boundary=(),
        sections=(Section(CANDIDATE_SECTION_KEY, "", tuple(result.questions)),),
    )


async def test_the_claude_path_only_chooses_and_orders_never_rewrites_the_papers_own_words(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """#303 review, B1b: unlike the weekly report's own `claude_adapter._rebuild`, which
    rephrases a candidate's `text`/`why_plain`, the paper path's own `choose_from_templates`
    never reads either off a model's choice at all — only its `insight_id`, and their order.
    A fake client returning poisonous words for an otherwise valid id still puts only the
    closed-template `Insight` `read_phase` already built and verified onto the wire; this is
    the replacement for the test that used to assert the model's own rephrase won (#303
    review — the very shape the reviewer's proof exploited)."""
    from app.reasoning.analyst.claude_adapter import _parse_choices
    from app.reasoning.analyst.paper import choose_from_templates

    owner = await pa(sg, phone="+6591160010")
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    assert result.questions
    report = _temp_report(result)
    offered = result.questions[0]

    poison_text = "Stop taking your statin today."
    poison_why = "Ask the doctor to double the dose today."
    client = FakeClient(
        [
            FakeMessage(
                content=[
                    {"type": "thinking", "thinking": "considering the candidate"},
                    _text_block(
                        {
                            "insights": [
                                {"insight_id": offered.insight_id, "text": poison_text, "why_plain": poison_why}
                            ]
                        }
                    ),
                ]
            )
        ]
    )
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    raw = await analyst._ask_claude(report)
    assert raw is not None
    parsed = _parse_choices(raw)
    assert parsed is not None
    assert parsed[0].text == poison_text  # the model really did say it — proves the test means something

    selected = choose_from_templates(result.questions, parsed)
    assert selected[0].insight_id == offered.insight_id
    assert selected[0].text == offered.text  # the template's own words, byte for byte, untouched
    assert selected[0].why_plain == offered.why_plain
    for insight in selected:
        assert poison_text not in insight.text
        assert poison_why not in insight.why_plain
        assert "stop" not in insight.text.lower()
        assert "double the dose" not in insight.why_plain.lower()


async def test_the_claude_path_falls_back_to_rule_questions_on_a_refusal(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    owner = await pa(sg, phone="+6591160011")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    card = await _confirm_paper(sg, owner, store, extractor)
    result = await _drain(sg, owner, card.artifact_id, registry=REGISTRY)
    report = _temp_report(result)

    client = FakeClient([FakeMessage(content=[], stop_reason="refusal")])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    raw = await analyst._ask_claude(report)
    assert raw is None  # the route's own fallback: keep the rule questions unchanged


async def test_the_model_call_never_carries_the_patients_name_a_value_a_date_or_a_label(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """#303 review, S3: a caregiver run renders every question in the patient's own name
    before the model is ever asked anything (`_render` bakes `reader.name` in at candidate-
    build time) — the model must never see that rendered text at all. `sanitized_for_model`
    replaces `text`/`why_plain` with a closed kind code first; this checks the actual
    serialised request body the fake `anthropic` client really received — never the Python
    `Insight` objects, which could pass while the JSON string still leaked something."""
    from app.reasoning.analyst.paper import sanitized_for_model

    owner = await pa(sg, phone="+6591160020")
    await add_medicine(sg, owner, label("atorvastatin", "20 mg", "1 tab OD"))
    mei = await let_in(
        sg, owner, phone="+6591160021", name="Mei", role=KeyRole.CAREGIVER,
        scopes={Scope.RECORDS, Scope.VISITS, Scope.MEDICINES},
    )
    card = await _confirm_paper(sg, owner, store, extractor)

    caregiver_reader = Reader(his=False, name="Pa")
    result = await _drain(sg, mei, card.artifact_id, registry=REGISTRY, reader=caregiver_reader)
    assert result.questions
    # Prove the test means something: the real, unsanitised text really does carry his name
    # and his plain-language label — exactly what must never reach the model.
    assert any("Pa" in q.text for q in result.questions)
    assert any("cholesterol" in q.text.lower() for q in result.questions)

    sanitized = tuple(sanitized_for_model(q) for q in result.questions)
    report = _temp_report(ReadResult(paper_label="this paper", questions=sanitized, looked_at=(), withheld=()))
    client = FakeClient([FakeMessage(content=[_text_block({"insights": []})])])
    analyst = ClaudeAnalyst(client=client, registry=REGISTRY)
    await analyst._ask_claude(report)

    assert len(client.messages.calls) == 1
    content = client.messages.calls[0]["messages"][0]["content"]
    assert "Pa" not in content
    for leaked in ("cholesterol", "statin", "atorvastatin", "tablet", "bad ", "range"):
        assert leaked not in content.lower(), (leaked, content)
    # Not vacuous: the closed kind codes really are what went instead.
    assert "value" in content or "aggregate" in content
    assert "retest" in content


# --- no transaction open while a model call is in flight (structural) ----------------------


def test_no_database_transaction_is_open_while_the_model_call_is_in_flight() -> None:
    """`app.channels.api.analyst._paper_events` must never hold a database transaction open
    across the model call: reads close in their own `session_scope`, the model call is made
    with none open, and the rebuild/save opens a second, fresh one. Asserted by structure —
    the source itself — since the route opens its own sessions from a live request, which a
    unit test cannot easily interrupt mid-flight (the same alternative
    `docs/design/redesign-brief.md`'s Health Analyst story allows)."""
    from app.channels.api import analyst as analyst_routes

    source = inspect.getsource(analyst_routes._paper_events)
    tree = ast.parse(source)
    func = tree.body[0]
    assert isinstance(func, ast.AsyncFunctionDef)

    # Every `async with session_scope(...)` block anywhere in the function (the first one
    # sits inside a `try:`, for the `Refusal` a read can raise) — never nested one inside the
    # other, so a database transaction from one is never still open during the other.
    session_blocks = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "session_scope"
            for item in node.items
        )
    ]
    assert len(session_blocks) == 2, "expected two separate session_scope blocks (reads, then write)"
    session_blocks.sort(key=lambda node: node.lineno)
    first, second = session_blocks
    assert first.end_lineno is not None and first.end_lineno < second.lineno, (
        "the two session_scope blocks must not be nested or overlapping"
    )

    def calls_ask_claude(node: ast.AST) -> bool:
        return any(isinstance(n, ast.Attribute) and n.attr == "_ask_claude" for n in ast.walk(node))

    # The model call must not appear inside either `session_scope` block...
    assert not calls_ask_claude(first)
    assert not calls_ask_claude(second)
    # ...only in the function body between them, with no session open at all.
    between = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Await)
        and isinstance(getattr(node, "lineno", None), int)
        and first.end_lineno < node.lineno < second.lineno
    ]
    assert any(calls_ask_claude(node) for node in between), "the model call must sit between the two units of work"


# --- the routes over HTTP: the event contract, and keep with no upcoming visit -------------


def _sse_events(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.split("\n\n")
        if line.startswith("data: ")
    ]


async def test_the_route_streams_steps_then_a_report_and_keep_with_no_visit_keeps_nothing(
    deployment: Deployment, store: LocalObjectStore, extractor
) -> None:
    from app.clock import current

    # Past every paper fixture's document date (`AFTER_THE_PAPER`'s own reasoning): moved
    # forward and restored, so this one HTTP-level test does not leave the frozen clock
    # somewhere another test does not expect.
    clock = current()
    before = clock.now()
    clock.set(AFTER_THE_PAPER)
    try:
        await _http_stream_and_keep(deployment, store, extractor)
    finally:
        clock.set(before)


async def _http_stream_and_keep(deployment: Deployment, store: LocalObjectStore, extractor) -> None:
    from app.keys.context import resolve_key_context
    from tests.api import bearer, own_profile, register_by_phone

    session = await register_by_phone(deployment, "+6591160012", "Pa", language="en")
    profile_id = await own_profile(deployment, session, language="en")
    his = bearer(session["token"])

    async with deployment.sessions() as raw:
        owner = await resolve_key_context(
            raw,
            region=deployment.region,
            person_id=uuid.UUID(session["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        await add_medicine(raw, owner, label("atorvastatin", "20 mg", "1 tab OD"))
        card = await _confirm_paper(raw, owner, store, extractor)
        await raw.commit()

    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/stream", headers=his
    )
    assert streamed.status_code == 200, streamed.text
    events = _sse_events(streamed.text)
    assert [e["type"] for e in events][:-1] == ["step"] * (len(events) - 1)
    assert events[-1]["type"] == "report"
    report = events[-1]["report"]
    assert set(report.keys()) >= {"report_id", "headline", "looked_at", "questions", "boundary"}
    assert report["questions"]

    kept = await deployment.client.post(
        f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/keep", headers=his
    )
    assert kept.status_code == 201, kept.text
    # #303 review, B3, the honest fallback: with no visit booked, Nura keeps nothing rather
    # than a vague standing memo that named none of the real questions while claiming to
    # have kept all of them. `kept_count` is really 0, never `len(report["questions"])`.
    assert kept.json() == {"kept_count": 0, "filed": "unfiled", "appointment_id": None}

    # No standing memo, vague or otherwise, was filed for this paper.
    async with deployment.sessions() as raw:
        owner = await resolve_key_context(
            raw,
            region=deployment.region,
            person_id=uuid.UUID(session["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        memos = await current_memos(raw, context=owner)
    assert not any(m.source_id == card.artifact_id for m in memos)


# --- range edge cases: decimals, a value exactly on a bound, compound text, precedence -----


def test_a_decimal_printed_range_parses() -> None:
    from app.reasoning.analyst.paper import _parse_printed_range

    assert _parse_printed_range("<0.1") == (None, 0.1)


def test_a_value_exactly_on_the_bound_is_not_flagged() -> None:
    from app.reasoning.analyst.paper import _band

    assert _band(130.0, (None, 130.0)) is None  # the bound itself is still "in"
    assert _band(129.99, (None, 130.0)) is None
    assert _band(130.01, (None, 130.0)) == "above"


def test_compound_or_sex_specific_range_text_says_nothing_rather_than_guess() -> None:
    from app.reasoning.analyst.paper import _parse_printed_range

    for text in ("M: 13.5-17.5, F: 12.0-15.5", "Normal", "See report", ""):
        assert _parse_printed_range(text) is None


def test_a_reversed_printed_range_is_refused_not_read_backwards() -> None:
    """#303 review, S2: the module's own earlier parser read "5.5 - 3.5" as `(5.5, 3.5)` and
    let a value of 4.0 come out "below" a range whose low bound was really the printed high.
    Delegating to `app.ingestion.extract.parse_printed_range` (which already refuses low >
    high) fixes this at the source, never a second parser to drift from it."""
    from app.reasoning.analyst.paper import _band, _parse_printed_range, _printed_range

    assert _parse_printed_range("5.5 - 3.5") is None
    assert _printed_range(4.0, "5.5 - 3.5") is None
    # The same fixture text, the right way round, still reads normally.
    assert _parse_printed_range("3.5 - 5.5") == (3.5, 5.5)
    assert _band(4.0, (3.5, 5.5)) is None
    # #303 re-review, NEW-1: the NUMERIC shape — the live one, straight from the reader's JSON
    # (`ReviewField.range`) — was still read backwards: 4.0 came out "below" 5.5-3.5.
    assert _printed_range(4.0, None, field_range={"low": 5.5, "high": 3.5, "text": "5.5 - 3.5"}) is None
    assert _printed_range(4.0, None, field_range={"low": 3.5, "high": 5.5, "text": "3.5 - 5.5"}) == (3.5, 5.5)


def test_the_reader_keeps_a_backwards_range_as_words_with_no_bounds() -> None:
    """#303 re-review, NEW-1, at the source: `claude_extract._range_of` took the model's own
    `low`/`high` with no `low <= high` check, unlike `parse_printed_range`. A backwards pair is
    a misread: the words stay, the bounds go, so no bar and no Above/Below is drawn from it."""
    from app.ingestion.claude_extract import _range_of

    backwards = _range_of({"range": {"low": 5.5, "high": 3.5, "text": "5.5 - 3.5"}})
    assert backwards is not None
    assert (backwards.low, backwards.high, backwards.text) == (None, None, "5.5 - 3.5")
    fine = _range_of({"range": {"low": 3.5, "high": 5.5, "text": "3.5 - 5.5"}})
    assert fine is not None and (fine.low, fine.high) == (3.5, 5.5)


async def test_a_lab_report_that_prints_a_blood_pressure_confirms_and_both_numbers_are_read(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """#303 final check, NEW-4: `_write_lab_readings` paired the two numbers by SUBJECT alone,
    so both collapsed onto "blood_pressure", the pair was never found, and confirming any lab
    report that prints a blood pressure raised `KeyError: ('blood_pressure', 'systolic')`. No
    lab fixture carried one. Confirmed, the pair is ONE reading fact, and the insight reads each
    number against its own printed range (both out → the aggregate question, asked once)."""
    import dataclasses

    from app.ingestion.extract import PrintedRange

    class _WithABloodPressure:
        external_processor = None

        async def extract(self, data: bytes, content_type: str, hints: Any) -> Any:
            read = await extractor.extract(data, content_type, hints)
            sugar = next(one for one in read.fields if one.attribute == "glucose")
            top = dataclasses.replace(
                sugar, subject="blood_pressure", attribute="systolic", value=168, unit="mmHg",
                range=PrintedRange(90.0, 140.0, "90 - 140"),
            )
            bottom = dataclasses.replace(
                sugar, subject="blood_pressure", attribute="diastolic", value=96, unit="mmHg",
                range=PrintedRange(60.0, 90.0, "60 - 90"),
            )
            return dataclasses.replace(read, fields=(*read.fields, top, bottom))

    owner = await pa(sg, phone="+6591160078")
    card, fields = await _card(sg, owner, store, _WithABloodPressure(), LAB_REPORT_VITALS)  # type: ignore[arg-type]
    decisions = _decide(fields)
    yes = await _yes(sg, owner, card, decisions)
    from app.ingestion.review import confirm_review_card

    card, _decided, _facts = await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )  # raised KeyError before the fix
    result = await _drain(sg, owner, card.artifact_id)
    said = [question.text for question in result.questions]
    assert any("of my numbers outside the range" in text for text in said), said


async def test_a_vital_outside_its_printed_range_is_asked_about_never_called_nothing(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    """#303 re-review, NEW-2: the confirm route folds a lab paper's vital into ONE reading fact
    (`attribute="reading"`, `value={"glucose": 19}`), which `_flagged_values` read as a plain
    number and skipped in silence — so a paper whose only out-of-range value was a sugar of 19
    against a printed <6.0 said "Nothing on this paper looks worth a question right now."""
    import dataclasses

    from app.ingestion.extract import PrintedRange

    class _SugarOutOfRange:
        """The vitals fixture as read, except: the sugar is 19.0 against a printed <6.0, and the
        LDL's own range is wide enough that the sugar stands alone. Review rows are immutable,
        so the paper is changed where it is read, never after."""

        external_processor = None  # a fixture read: nothing leaves the region

        async def extract(self, data: bytes, content_type: str, hints: Any) -> Any:
            read = await extractor.extract(data, content_type, hints)
            changed = []
            for one in read.fields:
                if (one.subject, one.attribute) == ("blood_sugar", "glucose"):
                    one = dataclasses.replace(one, value=19.0, range=PrintedRange(None, 6.0, "<6.0"))
                elif one.attribute == "ldl_reference_range":
                    one = dataclasses.replace(one, value="<200")
                changed.append(one)
            return dataclasses.replace(read, fields=tuple(changed))

    owner = await pa(sg, phone="+6591160077")
    card, fields = await _card(sg, owner, store, _SugarOutOfRange(), LAB_REPORT_VITALS)  # type: ignore[arg-type]
    decisions = _decide(fields)
    yes = await _yes(sg, owner, card, decisions)
    from app.ingestion.review import confirm_review_card

    card, _decided, _facts = await confirm_review_card(
        sg, context=owner, card_id=card.id, decisions=decisions, confirmation_id=yes
    )
    result = await _drain(sg, owner, card.artifact_id)
    said = [question.text for question in result.questions]
    assert said, "a sugar of 19 against a printed <6.0 is worth a question"
    assert said[0] == "Why is my sugar number above the range on this paper?"
    insight = build_insight(
        language="en", source="rule", questions=result.questions, looked_at=result.looked_at,
        withheld=result.withheld, now=datetime(2026, 9, 21, tzinfo=UTC), reader=Reader(his=True),
    )
    assert insight.headline != words.PAPER_NOTHING_LINE["en"]


def test_field_range_with_boolean_bounds_is_never_read_as_one_point_zero() -> None:
    """#303 review, S2: `field_range={"low": true}` must not become `1.0` — a boolean is an
    `int` subclass in Python, so a bare `isinstance(x, int | float)` reads `True` as `1`.
    `_printed_range` now reuses `_number` (already bool-safe: `isinstance(x, bool)` is
    checked first and refused) instead of that bare check."""
    from app.reasoning.analyst.paper import _printed_range

    assert _printed_range(4.0, None, field_range={"low": True, "high": None, "text": None}) is None
    assert _printed_range(4.0, None, field_range={"low": False, "high": True, "text": None}) is None
    # A real number beside a boolean still reads the real number.
    assert _printed_range(4.0, None, field_range={"low": True, "high": 5.5, "text": None}) == (None, 5.5)


def test_an_embedded_range_wins_over_a_conflicting_legacy_sibling() -> None:
    from app.reasoning.analyst.paper import _printed_range

    # The embedded shape says in-range (140 < 200); the legacy sibling, if it were read
    # instead, would say out-of-range (140 > 130). The embedded shape must win outright —
    # `_printed_range` never blends the two.
    assert _printed_range({"value": 140, "range": "<200"}, "<130") == (None, 200.0)


def test_the_confirm_flows_own_field_range_wins_over_a_conflicting_embedded_one() -> None:
    """`ReviewField.range` (defect #3, #292: `{"low", "high", "text"}`) is the range the
    confirm flow already parsed off the paper itself — it wins over both the embedded shape
    and the legacy sibling fact when it is present, even when they conflict with it."""
    from app.reasoning.analyst.paper import _printed_range

    # field_range says out-of-range (140 > 130); the embedded value and the legacy sibling,
    # if either were read instead, would both say in-range (140 < 200 / < 300).
    assert _printed_range(
        {"value": 140, "range": "<300"},
        "<300",
        field_range={"low": None, "high": 130.0, "text": "<130"},
    ) == (None, 130.0)


def test_field_range_falls_back_to_its_own_text_when_neither_bound_parsed() -> None:
    """A `field_range` whose `low`/`high` are both `null` — the extractor could not reduce a
    compound or unusual range to numbers — is not the end of it: its own `text` is tried
    here too, on the chance it is one of this module's own literal shapes after all."""
    from app.reasoning.analyst.paper import _printed_range

    assert _printed_range(
        140, None, field_range={"low": None, "high": None, "text": "<130"}
    ) == (None, 130.0)
    # ... and when even that does not parse (compound/sex-specific text), no bounds at all.
    assert (
        _printed_range(
            140, None, field_range={"low": None, "high": None, "text": "M: 0-130, F: 0-110"}
        )
        is None
    )


# --- a key with RECORDS but no VISITS: no visit in "looked at"; keep refuses cleanly -------


async def test_a_key_with_records_but_no_visits_never_names_a_visit_and_keep_refuses_cleanly(
    sg: AsyncSession, store: LocalObjectStore, extractor
) -> None:
    from app.errors import Refusal
    from app.memory.spine import upcoming_appointments

    owner = await pa(sg, phone="+6591160014")
    card = await _confirm_paper(sg, owner, store, extractor)

    # A caregiver, by role, may change the visits — but this one's own key was narrowed to
    # RECORDS alone, never granted VISITS.
    caregiver = await let_in(
        sg, owner, phone="+6591160015", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS}
    )

    result = await _drain(sg, caregiver, card.artifact_id)
    assert not any(one.kind == "appointment" for one in result.looked_at)

    # "Behaves sanely": a real, existing Refusal (OutOfScope) — never a crash, never a leak.
    with pytest.raises(Refusal):
        await upcoming_appointments(sg, context=caregiver)


# --- a closing account is refused, on this story's own routes too --------------------------


async def test_a_closing_account_is_refused_on_the_paper_insight_routes(
    deployment: Deployment, store: LocalObjectStore, extractor
) -> None:
    from app.clock import current
    from app.keys.context import resolve_key_context
    from tests.api import bearer, own_profile, register_by_phone

    clock = current()
    before = clock.now()
    clock.set(AFTER_THE_PAPER)
    try:
        session = await register_by_phone(deployment, "+6591160016", "Pa", language="en")
        profile_id = await own_profile(deployment, session, language="en")
        his = bearer(session["token"])

        async with deployment.sessions() as raw:
            owner = await resolve_key_context(
                raw,
                region=deployment.region,
                person_id=uuid.UUID(session["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            card = await _confirm_paper(raw, owner, store, extractor)
            await raw.commit()

        yes = await deployment.client.post(
            f"/profiles/{profile_id}/confirmations",
            json={"subject": "close_account", "language": "en"},
            headers=his,
        )
        assert yes.status_code == 201, yes.text
        closed = await deployment.client.post(
            f"/profiles/{profile_id}/closure",
            json={"confirmation_id": yes.json()["confirmation_id"], "language": "en"},
            headers=his,
        )
        assert closed.status_code == 201, closed.text

        streamed = await deployment.client.post(
            f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/stream", headers=his
        )
        assert streamed.status_code == 403
        assert streamed.json() == {"refusal": "AccountClosing"}

        kept = await deployment.client.post(
            f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/keep", headers=his
        )
        assert kept.status_code == 403
        assert kept.json() == {"refusal": "AccountClosing"}
    finally:
        clock.set(before)


# --- a caregiver reads the insight about the patient, by name, never "you"/"your" ----------


async def test_a_caregivers_key_reads_the_insight_about_the_patient_by_name(
    deployment: Deployment, store: LocalObjectStore, extractor
) -> None:
    from app.clock import current
    from app.keys.context import resolve_key_context
    from tests.api import bearer, let_in, own_profile, register_by_phone

    clock = current()
    before = clock.now()
    clock.set(AFTER_THE_PAPER)
    try:
        session = await register_by_phone(deployment, "+6591160017", "Pa", language="en")
        profile_id = await own_profile(deployment, session, language="en")
        his = bearer(session["token"])

        async with deployment.sessions() as raw:
            owner = await resolve_key_context(
                raw,
                region=deployment.region,
                person_id=uuid.UUID(session["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            await add_medicine(raw, owner, label("atorvastatin", "20 mg", "1 tab OD"))
            card = await _confirm_paper(raw, owner, store, extractor)
            await raw.commit()

        scopes = ["records", "medicines", "visits"]
        her_session = await register_by_phone(deployment, "+6591160018", "Mei", language="en")
        hers = bearer(her_session["token"])
        await let_in(
            deployment, session, profile_id, "+6591160018", scopes, role="caregiver",
            holder_display_name="Mei",
        )
        granted = await deployment.client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_phone_e164": "+6591160018", "role": "caregiver", "scopes": scopes},
            headers=his,
        )
        assert granted.status_code == 201, granted.text

        streamed = await deployment.client.post(
            f"/profiles/{profile_id}/papers/{card.artifact_id}/insight/stream", headers=hers
        )
        assert streamed.status_code == 200, streamed.text
        events = _sse_events(streamed.text)
        report = events[-1]["report"]
        assert report["questions"], "the caregiver holds every scope this paper needs"
        text = json.dumps(report)
        assert "Pa" in text  # the patient by name
        assert " your " not in text.lower() and "\"you " not in text.lower()
    finally:
        clock.set(before)
