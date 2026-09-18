"""ClipMaker (RE-07, item 1): a Nura-made explainer clip, 20-30s, captions timed line by
line, over one of the kit's warm scenes. `RuleClipMaker` is pure — no model, no network — and
is what this file holds to the same gates the module doc promises: every line passes plain
words, the treatment-change check and the conclusion-or-advice blocklist; the boundary is
appended last and is never itself checked against that blocklist; a script left with too
little safe material is not made at all, not padded and not shipped short.

`ClaudeClipMaker` is tested the way every other Claude-backed adapter in this codebase is
(`tests/test_claude_feed_adapters.py`): a mocked `anthropic` client, never a live call, and
the same demo/dev-run/key gate every adapter behind `app.llm.residency.allow_external_model`
already holds.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import now
from app.delivery.feed.clipmaker import (
    MAX_LINES,
    MIN_LINES,
    ClaudeClipMaker,
    ClipTopic,
    RuleClipMaker,
    cite_of,
    clip_length_ok,
    explainer_clip_item,
    scene_for,
)
from app.delivery.feed.compress import Found
from app.delivery.feed.days import today_for
from app.delivery.feed.items import Why, create_item
from app.delivery.feed.models import CardType, DeliverTo
from app.delivery.strings import Lines
from app.keys.scopes import Scope
from app.medicines.dose import parse_dose_text
from app.medicines.models import ChangeKind
from app.medicines.story import medication_story
from app.state.service import current_state
from tests.family_support import household
from tests.medicines_support import REGISTRY


def _bp_topic(**overrides: Any) -> ClipTopic:
    story = medication_story(
        generic="amlodipine",
        strength="5 mg",
        dose=parse_dose_text("1 tab OD"),
        prescriber="Dr Tan",
        change_kind=ChangeKind.NEW_LINE,
        monograph=REGISTRY.monograph("amlodipine"),
        language="en",
    )
    fields: dict[str, Any] = {
        "why_topic": story.name,
        "headline": story.name[:1].upper() + story.name[1:] + ", explained",
        "evidence": "a new medicine: amlodipine 5 mg",
        "catalogue_lines": tuple(story.purpose) + tuple(story.how_to_take),
        "doctor": "Dr Tan",
    }
    fields.update(overrides)
    return ClipTopic(**fields)


# --- scene_for -------------------------------------------------------------------------------


def test_scene_for_matches_a_medicine_topic_to_the_clinic_scene() -> None:
    assert scene_for("your blood pressure tablet") == "clinic"


def test_scene_for_matches_food_and_activity_and_family_topics() -> None:
    assert scene_for("your afternoon meal") == "food"
    assert scene_for("your weekly walk") == "walk"
    assert scene_for("your family and your caregiver") == "family"


def test_scene_for_falls_back_to_the_calm_default() -> None:
    assert scene_for("something this list has no keyword for") == "morning"


def test_scene_for_prefers_the_clinic_match_when_a_topic_names_both() -> None:
    # A topic naming a tablet and a meal reads as the clinic scene, the module's own docstring.
    assert scene_for("your blood pressure tablet and your food") == "clinic"


# --- the script gates --------------------------------------------------------------------------


def test_rule_clip_maker_returns_none_with_no_catalogue_lines() -> None:
    topic = _bp_topic(catalogue_lines=())
    assert RuleClipMaker().make(topic, "en") is None


def test_rule_clip_maker_drops_a_treatment_change_line_and_keeps_the_safe_ones() -> None:
    topic = _bp_topic(
        catalogue_lines=(
            "This is your blood pressure tablet.",
            "It keeps your blood pressure down.",
            "Stop the tablet if you feel unwell.",  # a treatment-change line: dropped
            "Take it with breakfast.",
            "Food does not matter for this one.",
        )
    )
    script = RuleClipMaker().make(topic, "en")
    assert script is not None
    assert "Stop the tablet if you feel unwell." not in script.lines
    assert "This is your blood pressure tablet." in script.lines
    assert "Take it with breakfast." in script.lines


def test_rule_clip_maker_drops_a_conclusion_language_line() -> None:
    topic = _bp_topic(
        catalogue_lines=(
            "This is your blood pressure tablet.",
            "It keeps your blood pressure down.",
            "Your number looks high today.",  # conclusion language: dropped
            "Take it with breakfast.",
            "Food does not matter for this one.",
        )
    )
    script = RuleClipMaker().make(topic, "en")
    assert script is not None
    assert "Your number looks high today." not in script.lines


def test_rule_clip_maker_refuses_a_script_under_min_lines() -> None:
    # Purpose alone is two lines for amlodipine (docs fixture): below MIN_LINES, so no clip —
    # a real regression this test pins: the demo used to write a card this short (17.5s).
    story = medication_story(
        generic="amlodipine",
        strength="5 mg",
        dose=parse_dose_text("1 tab OD"),
        prescriber="Dr Tan",
        change_kind=ChangeKind.NEW_LINE,
        monograph=REGISTRY.monograph("amlodipine"),
        language="en",
    )
    assert len(story.purpose) < MIN_LINES
    topic = _bp_topic(catalogue_lines=tuple(story.purpose))
    assert RuleClipMaker().make(topic, "en") is None


def test_rule_clip_maker_caps_the_script_at_max_lines() -> None:
    topics = ("tablet", "morning", "water", "breakfast", "pharmacy", "clinic", "doctor", "family", "walk", "dinner")
    topic = _bp_topic(
        catalogue_lines=tuple(f"This line talks about your {word}." for word in topics)
    )
    script = RuleClipMaker().make(topic, "en")
    assert script is not None
    kept = [line for line in script.lines if line.startswith("This line talks about")]
    assert len(kept) == MAX_LINES


def test_rule_clip_maker_builds_a_script_in_the_20_to_30_second_window() -> None:
    # The real demo topic: purpose + how_to_take together (RE-07, item 1's own fix over
    # purpose alone) reliably falls in the clip window.
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    assert clip_length_ok(script)
    assert 20 <= script.duration_ms / 1000 <= 30


def test_the_boundary_is_last_and_never_itself_gated() -> None:
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    boundary_lines = script.boundary.splitlines()
    assert boundary_lines
    assert list(script.lines[-len(boundary_lines) :]) == boundary_lines
    assert [c.text for c in script.captions[-len(boundary_lines) :]] == boundary_lines


def test_captions_are_timed_from_the_clip_start_in_order() -> None:
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    assert script.captions[0].at_ms == 0
    ats = [c.at_ms for c in script.captions]
    assert ats == sorted(ats)
    assert [c.text for c in script.captions] == list(script.lines)


def test_rule_clip_maker_names_nura_as_the_source_never_a_publisher() -> None:
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    assert script.source == "Nura"
    assert script.cite_url is None


def test_cite_of_shape_carries_the_same_caption_timing() -> None:
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    cite = cite_of(script)
    assert cite["kind"] == "nura_made"
    assert cite["scene"] == "clinic"
    assert cite["source"] == "Nura"
    assert cite["duration_ms"] == script.duration_ms
    assert cite["captions"] == [{"at_ms": c.at_ms, "text": c.text} for c in script.captions]
    assert cite["cite_url"] is None


# --- ClaudeClipMaker: gate, then the grounded, structured call ----------------------------------


@dataclass
class FakeBlock:
    text: str


@dataclass
class FakeResponse:
    content: Sequence[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"


class FakeMessages:
    def __init__(self, responses: Sequence[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages.create called more times than responses queued")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: Sequence[FakeResponse]) -> None:
        self.messages = FakeMessages(responses)


class FakeSearcher:
    def __init__(self, found: Sequence[Found]) -> None:
        self._found = list(found)
        self.calls: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        self.calls.append((kind, tuple(terms), tuple(domains)))
        return self._found

    def find(self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None) -> Sequence[Found]:
        raise AssertionError("the clip maker never uses find(); it only ever searches")


ALLOWLIST = ["healthhub.sg"]
PAGE = Found(
    domain="healthhub.sg",
    url="https://healthhub.sg/live-healthy/bp",
    title="Managing high blood pressure",
    published_at="2026-01-01",
    text="Taking your tablet at the same time each day helps it work steadily.",
)


def test_claude_clip_maker_refuses_without_demo_mode_or_dev_run() -> None:
    from app.delivery.feed.claude_adapters import ClaudeAdapterNotAvailable

    with pytest.raises(ClaudeAdapterNotAvailable, match="declared demo"):
        ClaudeClipMaker(
            searcher=FakeSearcher([]), domains=ALLOWLIST, api_key="sk-test", demo_mode=False, dev_run=False
        )


def test_claude_clip_maker_refuses_without_an_api_key() -> None:
    from app.delivery.feed.claude_adapters import ClaudeAdapterNotAvailable

    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeClipMaker(searcher=FakeSearcher([]), domains=ALLOWLIST, api_key=None, demo_mode=True)


def test_claude_clip_maker_returns_none_when_no_allowlisted_page_is_found() -> None:
    maker = ClaudeClipMaker(
        searcher=FakeSearcher([]), domains=ALLOWLIST, api_key="sk-test", demo_mode=True, client=FakeClient([])
    )
    assert maker.make(_bp_topic(), "en") is None


def test_claude_clip_maker_returns_none_on_a_refusal_stop_reason() -> None:
    client = FakeClient([FakeResponse(content=[], stop_reason="refusal")])
    maker = ClaudeClipMaker(
        searcher=FakeSearcher([PAGE]), domains=ALLOWLIST, api_key="sk-test", demo_mode=True, client=client
    )
    assert maker.make(_bp_topic(), "en") is None


def test_claude_clip_maker_returns_none_when_the_model_answers_no_usable_lines() -> None:
    import json

    client = FakeClient([FakeResponse(content=[FakeBlock(json.dumps({"lines": []}))])])
    maker = ClaudeClipMaker(
        searcher=FakeSearcher([PAGE]), domains=ALLOWLIST, api_key="sk-test", demo_mode=True, client=client
    )
    assert maker.make(_bp_topic(), "en") is None


def test_claude_clip_maker_builds_a_script_citing_the_page_it_read() -> None:
    import json

    lines = [
        "This is your blood pressure tablet.",
        "It keeps your blood pressure down.",
        "Taking it at the same time each day helps it work steadily.",
        "Take it with breakfast.",
    ]
    client = FakeClient([FakeResponse(content=[FakeBlock(json.dumps({"lines": lines}))])])
    maker = ClaudeClipMaker(
        searcher=FakeSearcher([PAGE]), domains=ALLOWLIST, api_key="sk-test", demo_mode=True, client=client
    )
    script = maker.make(_bp_topic(), "en")
    assert script is not None
    assert script.source == PAGE.domain
    assert script.cite_url == PAGE.url
    for line in lines:
        assert line in script.lines
    call = client.messages.calls[0]
    # The SDK's `JSONOutputFormatParam` reads `schema`, not `json_schema` — the shape a
    # 400 was hit live on (2026-09-18) until this was fixed.
    assert "schema" in call["output_config"]["format"]
    assert "json_schema" not in call["output_config"]["format"]


def test_claude_clip_maker_never_asks_a_domain_off_its_own_allowlist() -> None:
    """The searcher is the existing `Searcher` port: whatever domains it is given, never any
    the clip maker invents — `search()` is called with exactly `domains`."""
    searcher = FakeSearcher([PAGE])
    client = FakeClient([])
    maker = ClaudeClipMaker(
        searcher=searcher, domains=ALLOWLIST, api_key="sk-test", demo_mode=True, client=client
    )
    maker.make(_bp_topic(), "en")
    assert searcher.calls
    for _, _, domains in searcher.calls:
        assert list(domains) == ALLOWLIST


# --- writing the card: self_made, and only ever a clip -----------------------------------------


async def test_explainer_clip_item_writes_a_self_made_clip_card(sg: AsyncSession) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    state = await current_state(sg, context=owner)
    day = today_for(owner)
    item = await explainer_clip_item(
        sg,
        context=owner,
        state=state,
        script=script,
        fact_ids=("medication:1",),
        scope=Scope.MEDICINES,
        day_key=day.key,
        dedupe_key="explainer_clip:amlodipine",
        expires_at=day.now + timedelta(days=90),
        gap="amlodipine",
    )
    assert item.type is CardType.CLIP
    assert item.cite is not None
    assert item.cite["kind"] == "nura_made"
    assert item.cite["source"] == "Nura"
    assert "publisher" not in item.cite


async def test_a_self_made_card_names_no_publisher_because_it_read_no_page(sg: AsyncSession) -> None:
    """`items.SOURCED` requires an allowlisted `source` for a CLIP card — except a self-made
    one, which names none because it read none (`items.py`'s own docstring)."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    state = await current_state(sg, context=owner)
    day = today_for(owner)
    script = RuleClipMaker().make(_bp_topic(), "en")
    assert script is not None
    lines = Lines(
        language=script.language,
        headline=script.headline,
        body=script.lines,
        voice=script.lines,
        why=script.why_topic,
        boundary=script.boundary,
    )
    item = await create_item(
        sg,
        context=owner,
        state=state,
        type=CardType.CLIP,
        lines=lines,
        why=Why(kind="explainer_clip", plain=script.why_topic),
        scope=Scope.MEDICINES,
        deliver_to=DeliverTo.PATIENT,
        day=day.key,
        dedupe_key="explainer_clip:no_source",
        expires_at=now() + timedelta(days=90),
        cite=cite_of(script),
        self_made=True,
    )
    assert item.type is CardType.CLIP
    assert item.cite is not None and item.cite.get("source") == "Nura"
    assert "publisher" not in (item.cite or {})


async def test_self_made_is_refused_on_every_card_type_but_clip(sg: AsyncSession) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    state = await current_state(sg, context=owner)
    day = today_for(owner)
    lines = Lines(
        language="en",
        headline="Your blood pressure tablet, explained",
        body=("This is your blood pressure tablet.",),
        voice=("This is your blood pressure tablet.",),
        why="This explains a new medicine.",
    )
    with pytest.raises(ValueError, match="only a clip"):
        await create_item(
            sg,
            context=owner,
            state=state,
            type=CardType.STORY,
            lines=lines,
            why=Why(kind="test", plain="This explains a new medicine."),
            scope=Scope.MEDICINES,
            deliver_to=DeliverTo.PATIENT,
            day=day.key,
            dedupe_key="not_a_clip",
            expires_at=now() + timedelta(days=90),
            self_made=True,
        )


def _every_schema(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _every_schema(value)
    elif isinstance(node, list):
        for value in node:
            yield from _every_schema(value)


def test_the_structured_output_schema_is_one_the_api_accepts() -> None:
    """Hit live on the owner's key (2026-09-18): the same class of bug as the extractor's own
    lint (`tests/test_claude_extractor.py`) and the feed adapters' own
    (`tests/test_claude_feed_adapters.py`) — a property without a `type`, and `minimum`/
    `maximum` on a number, are both refused by the API's structured output. Every property
    carries a type; no numeric bounds ride in the schema."""
    from app.delivery.feed.clipmaker import _LINES_SCHEMA

    for node in _every_schema(_LINES_SCHEMA):
        if not (isinstance(node, dict) and "properties" in node):
            continue
        for name, prop in node["properties"].items():
            assert "type" in prop, name
            assert "minimum" not in prop and "maximum" not in prop, name
