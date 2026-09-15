"""The feeling cloud (E17-01): the base words, weighted by State, with a reason for each.

`weigh` is the rule, and it is arithmetic over what `record.read_situation` read: every base
word at the base weight; a medicine started in the last fortnight brings forward the words its
licensed monograph lists as watch-outs (`WATCH_OUT_WORDS`, by the registry's rule ids — never
a word the registry did not name); a medicine the register classes as dropping his sugar keeps
the red word for a low sugar within reach for as long as he takes it; the first week after a discharge, an open episode and a
direction in his own blood pressure bring forward theirs; and his own words from the last
month come back. Each word keeps every reason it has, by code and id; the reasons are on the
answer and on the tap for the audit and the metrics, and never on the screen.

`when_shown` is when the strip is on Today: only after a change he has not answered yet, and
at most once a day — gone after a tap or "Fine today" until something changes again, and on
each of the first seven days after a discharge (docs/smart-nudges.md §2). The cloud is worked
out on every read from the State and the record as they are, so it re-ranks the moment State
moves; there is no stored cloud to go stale.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read
from app.audit.models import Action
from app.db import as_utc
from app.drugs.registry import DrugRegistry
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.strings import PLAIN_NAME, say_date
from app.reasoning.feelings.models import FeelingTap
from app.reasoning.feelings.record import Situation, local_date, read_situation, rising
from app.reasoning.feelings.strings import LEADS, PROMPT, WORDS, language_of
from app.reasoning.feelings.words import (
    AFTER_DISCHARGE_DAYS,
    AFTER_DISCHARGE_WORDS,
    BASE,
    CHANGES,
    EPISODE_WORDS,
    NEW_MEDICINE_WINDOW,
    PAST_WORDS_WINDOW,
    TREND_WORDS,
    WATCH_OUT_WORDS,
    ReasonCode,
    Weight,
)
from app.safety.plain_words import verify
from app.safety.red_flags import HYPOGLYCAEMIC_CLASSES, Feeling, is_red


@dataclass(frozen=True, slots=True)
class Reason:
    """Why a word is on the cloud: a code, since when, and the ids it rests on."""

    code: ReasonCode
    since: datetime | None
    ids: Mapping[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "since": None if self.since is None else as_utc(self.since).isoformat(),
            **self.ids,
        }


@dataclass(frozen=True, slots=True)
class Weighed:
    word: Feeling
    weight: Weight
    reasons: tuple[Reason, ...]

    @property
    def emphasised(self) -> bool:
        return self.weight >= Weight.EMPHASISED


def weigh(situation: Situation) -> list[Weighed]:
    """Every word for the cloud, biggest first, each with every reason it is there.

    Words of the same weight come newest change first, then in the order they were brought
    in by; "Fine today" is always last and always there.
    """
    now = situation.now
    weights: dict[Feeling, Weight] = {}
    reasons: dict[Feeling, list[Reason]] = {}
    order: list[Feeling] = []

    def put(word: Feeling, weight: Weight, reason: Reason) -> None:
        if word not in weights:
            order.append(word)
            weights[word] = weight
            reasons[word] = []
        weights[word] = max(weights[word], weight)
        reasons[word].append(reason)

    for word in BASE:
        put(word, Weight.BASE, Reason(ReasonCode.BASE, None))
    # Shaky and sweaty is a red flag on a medicine that can drop his sugar, by the red-flag
    # module's own classes. It is his word for a low sugar, so while he takes one it is always
    # within reach, as chest pain is — not only in the medicine's first fortnight (#157).
    for line in situation.lines:
        if line.drug_class in HYPOGLYCAEMIC_CLASSES:
            ids = {"line_id": str(line.line_id), "generic": line.generic}
            put(Feeling.SHAKY_SWEATY, Weight.BASE, Reason(ReasonCode.SUGAR_MEDICINE, None, ids))
    for line in sorted(situation.lines, key=lambda one: one.started_at, reverse=True):
        if now - line.started_at > NEW_MEDICINE_WINDOW:
            continue
        for rule in line.watch_out_ids:
            brought = WATCH_OUT_WORDS.get(rule)
            if brought is not None:
                ids: dict[str, Any] = {
                    "line_id": str(line.line_id),
                    "generic": line.generic,
                    "watch_out": rule,
                }
                put(
                    brought,
                    Weight.EMPHASISED,
                    Reason(ReasonCode.NEW_MEDICINE, line.started_at, ids),
                )
    if (
        situation.discharged_at is not None
        and now - situation.discharged_at <= AFTER_DISCHARGE_DAYS
    ):
        for word in AFTER_DISCHARGE_WORDS:
            put(
                word, Weight.EMPHASISED, Reason(ReasonCode.AFTER_DISCHARGE, situation.discharged_at)
            )
    for episode in situation.episodes:
        for word in EPISODE_WORDS.get(episode.kind, ()):
            ids = {"episode_id": episode.id, "episode_kind": episode.kind.value}
            put(word, Weight.ADDED, Reason(ReasonCode.EPISODE, episode.since, ids))
    trend = rising(situation.readings, now)
    if trend:
        ids = {"fact_ids": [str(reading.fact_id) for reading in trend]}
        for word in TREND_WORDS:
            put(word, Weight.EMPHASISED, Reason(ReasonCode.READING_TREND, trend[-1].taken_at, ids))
    seen: set[Feeling] = set()
    for said in situation.said:  # newest first
        if said.word in seen or said.word is Feeling.FINE or is_red(said.word):
            continue
        if now - said.at > PAST_WORDS_WINDOW:
            continue
        seen.add(said.word)
        put(
            said.word,
            Weight.ADDED,
            Reason(ReasonCode.SAID_BEFORE, said.at, {"tap_id": str(said.tap_id)}),
        )

    def newest_change(word: Feeling) -> float:
        moments = [
            as_utc(r.since).timestamp() for r in reasons[word] if r.code in CHANGES and r.since
        ]
        return max(moments, default=0.0)

    # Biggest first; among the same size, the newest change first (a medicine started today
    # before one started last week); then the order the words were brought in by.
    ranked: list[Feeling] = sorted(
        (word for word in order if word is not Feeling.FINE),
        key=lambda word: (-weights[word], -newest_change(word), order.index(word)),
    )
    ranked.append(Feeling.FINE)
    return [Weighed(word, weights[word], tuple(reasons[word])) for word in ranked]


def when_shown(
    weighed: list[Weighed], situation: Situation, context: KeyContext
) -> tuple[bool, str]:
    """Whether the strip is on Today now, and why, in a code."""
    today = local_date(situation.now, context)
    last = situation.last_tap_at
    if last is not None and local_date(last, context) == today:
        return False, "tapped_today"
    changes = [
        reason
        for item in weighed
        for reason in item.reasons
        if reason.code in CHANGES and reason.since
    ]
    if any(reason.code is ReasonCode.AFTER_DISCHARGE for reason in changes):
        return True, "after_discharge"
    newest = max((as_utc(reason.since) for reason in changes if reason.since), default=None)
    if newest is None:
        return False, "no_change"
    if last is None or newest > last:
        return True, "changed"
    return False, "no_change_since_last_tap"


def lead_for(
    weighed: list[Weighed], situation: Situation, context: KeyContext, code: str
) -> str | None:
    """What changed, in one line, for the newest change behind the cloud; or nothing."""
    changes = [
        reason
        for item in weighed
        for reason in item.reasons
        if reason.code in CHANGES and reason.since
    ]
    if not changes:
        return None
    newest = max(changes, key=lambda reason: as_utc(reason.since or situation.now))
    template = LEADS[code].get(newest.code.value)
    if template is None:
        return None
    if newest.code is ReasonCode.NEW_MEDICINE:
        line = next(
            (one for one in situation.lines if str(one.line_id) == newest.ids.get("line_id")), None
        )
        if line is None or line.plain_name_id is None:
            return None
        text = template.format(
            medicine=PLAIN_NAME[code][line.plain_name_id],
            date=say_date(local_date(line.started_at, context), code),
        )
    elif newest.code is ReasonCode.AFTER_DISCHARGE and newest.since is not None:
        text = template.format(date=say_date(local_date(newest.since, context), code))
    else:
        text = template.format(count=len(newest.ids.get("fact_ids", ())))
    text = text[:1].upper() + text[1:]
    failing = [f for f in verify(text, code, "line") if f.severity == "fail"]
    return None if failing else text


@dataclass(frozen=True, slots=True)
class CloudWord:
    word: Feeling
    label: str
    weight: int
    red: bool
    reasons: tuple[Reason, ...]


@dataclass(frozen=True, slots=True)
class Cloud:
    """The strip as it stands now: whether it shows, the question, the words, and the State
    it was read from."""

    state_id: uuid.UUID | None
    language: str
    show: bool
    because: str
    prompt: tuple[str, ...]
    words: tuple[CloudWord, ...]


@audited(Action.READ, Scope.RECORDS, FeelingTap.__tablename__)
async def compose_cloud(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    language: str | None = None,
) -> Cloud:
    """The cloud for this profile now, in `language` or the profile's own."""
    if language is None:
        language = (await audited_profile_read(session, context)).language
    code = language_of(language)
    situation = await read_situation(session, context=context, registry=registry)
    weighed = weigh(situation)
    show, because = when_shown(weighed, situation, context)
    lead = lead_for(weighed, situation, context, code)
    return Cloud(
        state_id=None if situation.state is None else situation.state.id,
        language=code,
        show=show,
        because=because,
        prompt=((lead,) if lead else ()) + (PROMPT[code],),
        words=tuple(
            CloudWord(
                item.word, WORDS[code][item.word], int(item.weight), is_red(item.word), item.reasons
            )
            for item in weighed
        ),
    )
