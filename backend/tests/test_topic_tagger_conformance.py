"""The `TopicTagger` port's conformance suite (RE-04): what ANY adapter must answer.

`app.delivery.recommend.topics.TopicTagger` is a port; `KeywordTagger` is the default adapter
and `FixtureTagger` is the one this build uses in tests and dev runs. `assert_tagger_conforms`
is the suite either must pass, in the pattern of `test_drug_registry_conformance.py`: it names
the shape and the invariants a caller is entitled to rely on, so a later `ModelTagger` (module
doc, §2.8 of the design) drops in with no change to a caller.

The suite takes its sample from the caller, exactly as the drug registry suite does: a keyword
adapter and a fixture adapter answer the same text by different means, so nothing here is
specific to either beyond the shared shape.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.delivery.recommend.topics import (
    FixtureTagger,
    KeywordTagger,
    TopicTagger,
    catalogue,
)

CATALOGUE = catalogue()


def assert_tagger_conforms(
    tagger: TopicTagger,
    *,
    sample: Sequence[tuple[str, Sequence[str]]],
    sensitive_only: str,
    unknown: str,
) -> None:
    """The contract every `TopicTagger` adapter must meet.

    `sample` pairs a text with the topic codes it is known to tag, exactly (order does not
    matter, `tag()` need not be a superset of anything else). `sensitive_only` is text known
    to tag nothing but `sensitive` topics. `unknown` is text the adapter is known to tag
    nothing for at all.
    """
    assert sample, "a sample of nothing conforms to nothing useful"

    # Empty and blank text tags nothing — there is no topic in silence.
    assert tagger.tag("") == ()
    assert tagger.tag("   ") == ()

    # Every code an adapter returns is a real topic, and never a sensitive one (module doc):
    # the port's own invariant, not a filter a caller must remember to apply.
    for text, expected in sample:
        result = tagger.tag(text)
        assert set(result) == set(expected), f"{text!r}: got {result}, expected {expected}"
        for code in result:
            assert code in CATALOGUE, f"{code!r} is not in the catalogue"
            assert not CATALOGUE[code].sensitive, f"{code!r} is sensitive and must never surface"
        # No code repeats, and the answer is deterministic across calls.
        assert len(result) == len(set(result))
        assert tagger.tag(text) == result

    # A text that tags only sensitive topics returns nothing at all (§3.5, decision D3) —
    # not a shorter list, the same empty shape as text about nothing this catalogue knows.
    assert tagger.tag(sensitive_only) == ()

    # Text this adapter has no reason to tag anything for tags nothing, never a nearest guess.
    assert tagger.tag(unknown) == ()


KEYWORD_SAMPLE: Sequence[tuple[str, Sequence[str]]] = (
    ("High blood pressure", ("condition.high_blood_pressure",)),
    ("Sugar, diabetes", ("condition.diabetes",)),
    ("amlodipine", ("medicine.blood_pressure_tablet",)),
    ("metformin", ("medicine.sugar_tablet",)),
    (
        "my blood pressure is high and I take amlodipine",
        ("condition.high_blood_pressure", "medicine.blood_pressure_tablet"),
    ),
)


def test_the_keyword_tagger_conforms() -> None:
    assert_tagger_conforms(
        KeywordTagger(),
        sample=KEYWORD_SAMPLE,
        sensitive_only="am I pregnant",
        unknown="the weather is nice today",
    )


FIXTURE_SAMPLE: Sequence[tuple[str, Sequence[str]]] = (
    ("my blood pressure is high", ("condition.high_blood_pressure",)),
    ("I take amlodipine every morning", ("medicine.blood_pressure_tablet",)),
    ("I'm pregnant and my blood pressure is high", ("condition.high_blood_pressure",)),
)


def test_the_fixture_tagger_conforms() -> None:
    assert_tagger_conforms(
        FixtureTagger.load(),
        sample=FIXTURE_SAMPLE,
        sensitive_only="am I pregnant",
        unknown="a text with no fixture at all",
    )
