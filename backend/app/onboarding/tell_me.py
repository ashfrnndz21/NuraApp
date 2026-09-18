"""Free text, tagged into cloud pills ("Or just tell me", docs/onboarding.html).

The words he types are run through RE-04's `TopicTagger` and mapped back onto the condition
codes of the word cloud's own graph — the topic catalogue's `condition.<code>` topics are
built straight from that graph (`app.delivery.recommend.topics._condition_topics`), so every
code this returns is already one of the cloud's own words; nothing here invents a pill the
graph does not have, and nothing here diagnoses.

A red word — one of RE-04's six sensitive families (mental-health crisis, abuse and the rest,
`app.delivery.recommend.topics`, §3.5) — never becomes a pill. `tell_me` checks for one first,
with `sensitive_hit`, before it ever calls a tagger: on a hit it names no conditions at all,
and the caller sends him to the safety path instead of tagging his own words. Nothing he typed
is stored here or echoed back — the answer is codes and a flag, never the text.

Public, the way the cloud itself is (`GET /onboarding/conditions`): nothing is read from or
written to a profile, so no key context is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.delivery.recommend.topics import KeywordTagger, TopicTagger, sensitive_hit
from app.onboarding.conditions import graph

CONDITION_TOPIC_PREFIX = "condition."


@dataclass(frozen=True, slots=True)
class ToldFreely:
    """What free text told the cloud: the conditions it tagged (his own graph's codes only),
    and whether a red word means it told nothing at all."""

    conditions: tuple[str, ...]
    red_flag: bool


def tell_me(text: str, *, tagger: TopicTagger | None = None) -> ToldFreely:
    """"Or just tell me": `text`, tagged into the cloud's own condition codes, sensitive words
    turned away before a tagger ever sees them. `tagger` defaults to `KeywordTagger`, as every
    other caller of the port that needs no heavier adapter does (`app.delivery.recommend.
    broker.slate`); tests pass a `FixtureTagger` the same way."""
    if sensitive_hit(text):
        return ToldFreely(conditions=(), red_flag=True)
    tag = tagger if tagger is not None else KeywordTagger()
    known = graph().conditions
    found = tuple(
        code
        for topic_code in tag.tag(text)
        if topic_code.startswith(CONDITION_TOPIC_PREFIX)
        and (code := topic_code[len(CONDITION_TOPIC_PREFIX) :]) in known
    )
    return ToldFreely(conditions=found, red_flag=False)


__all__ = ["ToldFreely", "tell_me"]
