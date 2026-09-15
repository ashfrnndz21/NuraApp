"""The feeling cloud's fixed tables: which words, why they matter this week, what to ask back.

Nothing here is a finding. A word is on the cloud because it is one of the everyday base
words, or because something on the record makes it worth offering first: a medicine started
in the last fortnight whose licensed monograph lists it as a watch-out, the week after a
discharge, an open episode, or a direction the arithmetic shows in his own blood pressure.
The link from a monograph to a word is a table from the registry's own rule ids
(`WATCH_OUT_WORDS`) — the registry says "dizzy_standing" for amlodipine, and the cloud offers
"Dizzy"; no word is ever tied to a medicine any other way.

A tap is answered with exactly one question from `FollowUp`. For the three words that have a
red variant (short of breath, swollen ankles, a headache) the one question is the one that
tells them apart, and a yes goes straight to the red word (`red_answer`) and the red-flag
path, never to an inference.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from enum import IntEnum, StrEnum

from app.memory.models import EpisodeKind
from app.safety.red_flags import Feeling, is_red
from app.safety.symptoms import Symptom

BASE: tuple[Feeling, ...] = (
    Feeling.TIRED,
    Feeling.PAIN,
    Feeling.DIZZY,
    Feeling.BREATHLESS,
    Feeling.LOW,
    Feeling.WORRIED,
    Feeling.CANT_SLEEP,
    Feeling.CHEST_TIGHTNESS,
    Feeling.FINE,
)
"""On every cloud. "Fine today" is always there, and so is chest pain: the one we never
wait for is always within reach, whatever else the week brings."""

WATCH_OUT_WORDS: Mapping[str, Feeling] = {
    "dizzy_standing": Feeling.DIZZY,
    "swollen_ankles": Feeling.SWOLLEN_ANKLES,
    "muscle_ache": Feeling.ACHES,
    "cramps": Feeling.CRAMPS,
    "tummy_upset": Feeling.STOMACH_UPSET,
    "shaky_sweaty": Feeling.SHAKY_SWEATY,
}
"""A monograph's watch-out rule id (`app.drugs.registry.Monograph.watch_out_ids`) → the cloud
word for it. The ids are the licensed registry's; a watch-out with no word here (bleeding
signs, black stools) is not a feeling he taps and is left to the medicine's own story."""

SYMPTOM_FEELINGS: Mapping[Symptom, Feeling] = {
    Symptom.TIRED: Feeling.TIRED,
    Symptom.WEAK: Feeling.TIRED,
    Symptom.DIZZY: Feeling.DIZZY,
    Symptom.HEADACHE: Feeling.HEADACHE,
    Symptom.NAUSEA: Feeling.STOMACH_UPSET,
    Symptom.VOMITING: Feeling.STOMACH_UPSET,
    Symptom.STOMACH_PAIN: Feeling.STOMACH_UPSET,
    Symptom.DIARRHOEA: Feeling.STOMACH_UPSET,
    Symptom.CANNOT_SLEEP: Feeling.CANT_SLEEP,
    Symptom.LEG_SWELLING: Feeling.SWOLLEN_ANKLES,
    Symptom.JOINT_PAIN: Feeling.ACHES,
}
"""A symptom said in words (`app.safety.symptoms`, the button and the log) → the cloud word for
it, so a symptom is read against a new medicine's monograph by the same rule a tap is
(`WATCH_OUT_WORDS`, `NEW_MEDICINE_WINDOW`): the not-feeling-well card's call-the-clinic row
(E13-02). A symptom with no cloud word here is read against no monograph."""

AFTER_DISCHARGE_WORDS: tuple[Feeling, ...] = (
    Feeling.BREATHLESS,
    Feeling.SWOLLEN_ANKLES,
    Feeling.WEIGHT_GAIN,
    Feeling.CONFUSION,
)
"""The first week home (docs/smart-nudges.md §2, "home from hospital"). Two of them are red
words, offered so that a tap on them reaches the red-flag path at once."""

EPISODE_WORDS: Mapping[EpisodeKind, tuple[Feeling, ...]] = {
    EpisodeKind.ILLNESS: (Feeling.TIRED, Feeling.PAIN),
    EpisodeKind.RECOVERY: (Feeling.TIRED, Feeling.BREATHLESS),
}
"""An open episode of these kinds, as State holds it, brings these words forward."""

TREND_WORDS: tuple[Feeling, ...] = (Feeling.HEADACHE, Feeling.DIZZY)
"""His own blood pressure going up, reading after reading (docs/smart-nudges.md §2,
"pressure rising"). A direction, never a threshold."""

NEW_MEDICINE_WINDOW = timedelta(days=14)
"""A medicine is new for its first fortnight: "the feeling words for the first fortnight"
(docs/design-for-the-absent-user.md §4)."""
AFTER_DISCHARGE_DAYS = timedelta(days=7)
"""Day one to seven after a discharge, the cloud comes forward (docs/smart-nudges.md §2)."""
TIMELINE_WINDOW = timedelta(days=7)
"""A visit or a discharge this week is part of what a tap is read against (E17-02)."""
PAST_WORDS_WINDOW = timedelta(days=30)
"""His own words from the last month come back onto the cloud."""
TREND_READINGS = 3
"""How many blood pressure numbers, each higher than the one before, make a direction."""
TREND_WINDOW = timedelta(days=14)
"""The numbers a direction is read from are this recent."""


class Weight(IntEnum):
    """How big a word sits on the cloud. Larger words come first."""

    BASE = 1
    ADDED = 2
    EMPHASISED = 3


class ReasonCode(StrEnum):
    """Why a word is on the cloud, or bigger. Kept on the answer and on the tap for the audit
    and the metrics; never shown to him."""

    BASE = "base"
    NEW_MEDICINE = "new_medicine"
    AFTER_DISCHARGE = "after_discharge"
    EPISODE = "episode"
    READING_TREND = "reading_trend"
    SAID_BEFORE = "said_before"


CHANGES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.NEW_MEDICINE,
        ReasonCode.AFTER_DISCHARGE,
        ReasonCode.EPISODE,
        ReasonCode.READING_TREND,
    }
)
"""The reasons that are a change in State. The cloud shows itself only after one of these,
and not again once he has tapped since (docs/smart-nudges.md §2, "When it appears")."""


class FollowUp(StrEnum):
    """The one thing a tap asks back. A fixed table; nothing is composed."""

    SINCE_WHEN = "since_when"
    MORE_THAN_YESTERDAY = "more_than_yesterday"
    AT_REST = "at_rest"
    ONE_SIDE = "one_side"
    WORST_EVER = "worst_ever"


class Answer(StrEnum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    FEW_DAYS = "few_days"
    WEEK_OR_MORE = "week_or_more"
    MORE = "more"
    SAME = "same"
    LESS = "less"
    YES = "yes"
    NO = "no"


ANSWERS: Mapping[FollowUp, tuple[Answer, ...]] = {
    FollowUp.SINCE_WHEN: (Answer.TODAY, Answer.YESTERDAY, Answer.FEW_DAYS, Answer.WEEK_OR_MORE),
    FollowUp.MORE_THAN_YESTERDAY: (Answer.MORE, Answer.SAME, Answer.LESS),
    FollowUp.AT_REST: (Answer.YES, Answer.NO),
    FollowUp.ONE_SIDE: (Answer.YES, Answer.NO),
    FollowUp.WORST_EVER: (Answer.YES, Answer.NO),
}

SAFETY: Mapping[Feeling, tuple[FollowUp, Feeling]] = {
    Feeling.BREATHLESS: (FollowUp.AT_REST, Feeling.BREATHLESS_AT_REST),
    Feeling.SWOLLEN_ANKLES: (FollowUp.ONE_SIDE, Feeling.ONE_SIDED_SWELLING),
    Feeling.HEADACHE: (FollowUp.WORST_EVER, Feeling.WORST_HEADACHE),
}
"""A word with a red variant, the question that tells them apart, and the red word a yes is.
The rule's own words (`.claude/rules/safety.md`): breathlessness at rest, one-sided swelling,
worst-ever headache."""


def follow_up_for(word: Feeling, *, said_yesterday: bool) -> FollowUp | None:
    """The one question a tap on `word` asks back, or None: "Fine today" asks nothing, and a
    red word goes to the red-flag path and asks nothing either. A word with a red variant
    asks the question that tells them apart; a word he said yesterday too asks whether it is
    more; anything else asks when it began."""
    if word is Feeling.FINE or is_red(word):
        return None
    if word in SAFETY:
        return SAFETY[word][0]
    return FollowUp.MORE_THAN_YESTERDAY if said_yesterday else FollowUp.SINCE_WHEN


def red_answer(word: Feeling, follow_up: FollowUp | None, answer: Answer) -> Feeling | None:
    """The red word an answer makes of a tap, or None. Only a yes to the question that tells
    the red variant apart does."""
    safety = SAFETY.get(word)
    if safety is not None and safety[0] is follow_up and answer is Answer.YES:
        return safety[1]
    return None


def cloud_words() -> tuple[Feeling, ...]:
    """Every word that can reach a cloud, in the order the tables name them."""
    seen: list[Feeling] = []
    for word in (
        *BASE,
        *WATCH_OUT_WORDS.values(),
        *AFTER_DISCHARGE_WORDS,
        *(w for words in EPISODE_WORDS.values() for w in words),
        *TREND_WORDS,
    ):
        if word not in seen:
            seen.append(word)
    return tuple(seen)


def inferable_words() -> tuple[Feeling, ...]:
    """The words a tap can lead to a note on: every word that is not red and not "Fine today".
    A tap may name any word of the set, on the cloud today or not."""
    return tuple(w for w in Feeling if not is_red(w) and w is not Feeling.FINE)
