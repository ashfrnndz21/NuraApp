"""RE-04 acceptance: every condition and every medicine generic on the demo fixtures maps to a
topic code with a plain name in en, ms and zh.

The list is never hand-typed: conditions come from `app.onboarding.conditions.graph()` — the
same word cloud a demo (and a real) onboarding shows — and medicine generics come from the
fixture drug registry's own file, `tests/fixtures/drugs/registry.json`, the registry a demo or
dev deployment runs on (`app.demo`, `app.drugs.client`). Both are read fresh here, so a
condition or a generic added to either source is covered the day it lands, with no list in
this file to fall out of date.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.delivery.recommend.topics import KeywordTagger, catalogue
from app.onboarding.conditions import graph as conditions_graph

LANGUAGES = ("en", "ms", "zh")

REGISTRY_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "drugs" / "registry.json"
)


def _demo_generics() -> dict[str, str]:
    """Every generic on the fixture registry, to the `plain_name_id` its monograph gives it —
    the same registry a demo deployment runs on (`app.demo`, ADR 0008)."""
    raw = json.loads(REGISTRY_FIXTURE.read_text(encoding="utf-8"))
    return {generic: mono["plain_name_id"] for generic, mono in raw["monographs"].items()}


def test_every_demo_condition_maps_to_a_topic_with_a_plain_name_in_three_languages() -> None:
    tagger = KeywordTagger()
    cat = catalogue()
    conditions = conditions_graph().conditions
    assert conditions, "the conditions graph is the source of truth and must not be empty"
    for code, condition in conditions.items():
        topic_code = f"condition.{code}"
        assert topic_code in cat, f"{code} has no topic in the catalogue"
        topic = cat[topic_code]
        for language in LANGUAGES:
            assert topic.name(language).strip(), f"{topic_code} has no {language} name"
            # His own name for the condition, in every language, tags its own topic.
            result = tagger.tag(condition.names[language])
            assert topic_code in result, (
                f"{topic_code}: {condition.names[language]!r} ({language}) did not tag it"
            )


def test_every_demo_medicine_generic_maps_to_a_topic_with_a_plain_name_in_three_languages() -> None:
    tagger = KeywordTagger()
    cat = catalogue()
    generics = _demo_generics()
    assert generics, "the fixture registry is the source of truth and must not be empty"
    for generic, family_id in generics.items():
        topic_code = f"medicine.{family_id}"
        assert topic_code in cat, f"{generic} ({family_id}) has no topic in the catalogue"
        topic = cat[topic_code]
        for language in LANGUAGES:
            assert topic.name(language).strip(), f"{topic_code} has no {language} name"
        # His name for the medicine he takes tags its topic.
        assert topic_code in tagger.tag(generic), f"{generic} did not tag {topic_code}"
