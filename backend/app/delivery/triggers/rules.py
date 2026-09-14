"""What each trigger is, and the clock of his day it runs on (E00-05, E11-05, E11-10).

A trigger is one of three kinds: a rule (an hour or a date reached — breakfast, the end of a
dose's window, the reorder date), a pattern (arithmetic on events over a window — three
untapped doses in seven days, a count and never a diagnosis) or an event (something new — a
red flag, a paper waiting for a yes, a visit tomorrow, a family message come due). Each has a
type, and the type says what it speaks of (`scope`: a recipient's key must cover it), where
it goes first (`channels`: app push, then WhatsApp, then the caregiver, by default), how many
a person may have of it in his day (`cap`) and whether it waits out the quiet hours. An
alert — a red flag — has no cap and no quiet hours, and no setting can give it either.

The clock of his day is E10-01's routine (`app.routines`), not a second one kept here, with
the one breakfast time (`app.routines.breakfast`: his settings, else the routine's anchor,
else 07:30): the morning card goes at breakfast (E11-10), with the first week's prompt due at
the same moment; a tablet hangs on its anchor's time; and a tablet's window runs from
an hour before its anchor to the end of the routine's own "due" for that anchor (`DUE_FOR`,
or the next anchor if that comes sooner) — untapped then, the ladder starts. A profile changes
the delivery defaults with `DeliverySettings` (E11-05): the list and the cap per type, the
quiet hours, and whether a quiet day's morning card is skipped. `Config` is those settings
and the routine's day read over the defaults.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.delivery.feed.rank import QUIET_FROM, QUIET_UNTIL
from app.delivery.triggers.models import (
    Category,
    DeliveryChannel,
    DeliverySettings,
    TriggerKind,
    TriggerType,
)
from app.errors import Refusal
from app.keys.scopes import Scope
from app.medicines.dose import Anchor
from app.routines.models import Routine
from app.routines.service import ANCHORS, DUE_FOR, Day, day_of

EVERYWHERE: tuple[DeliveryChannel, ...] = (
    DeliveryChannel.APP_PUSH,
    DeliveryChannel.WHATSAPP,
    DeliveryChannel.CAREGIVER,
)
"""The default list: his phone's app first, then the WhatsApp template, then the caregiver."""


@dataclass(frozen=True, slots=True)
class Rule:
    type: TriggerType
    kind: TriggerKind
    category: Category
    scope: Scope
    rule: str
    """The rule's own name, written on every delivery it makes."""
    cap: int | None
    """Deliveries of this type a person may have in his day; None is never capped."""
    quiet: bool
    """Whether the quiet hours hold it."""
    channels: tuple[DeliveryChannel, ...] = EVERYWHERE


RULES: Mapping[TriggerType, Rule] = {
    rule.type: rule
    for rule in (
        Rule(
            TriggerType.MORNING,
            TriggerKind.RULE,
            Category.REMINDER,
            Scope.MEDICINES,
            "breakfast_anchor_reached",
            cap=1,
            quiet=True,
        ),
        Rule(
            TriggerType.DOSE,
            TriggerKind.RULE,
            Category.REMINDER,
            Scope.MEDICINES,
            "dose_window_closed_untapped",
            cap=4,
            quiet=True,
        ),
        Rule(
            TriggerType.REORDER,
            TriggerKind.RULE,
            Category.REMINDER,
            Scope.MEDICINES,
            "reorder_date_reached",
            cap=1,
            quiet=True,
        ),
        Rule(
            TriggerType.DOSES_UNTAPPED,
            TriggerKind.PATTERN,
            Category.CONTEXT,
            Scope.MEDICINES,
            "three_untapped_doses_in_seven_days",
            cap=1,
            quiet=True,
        ),
        Rule(
            TriggerType.FLAG,
            TriggerKind.EVENT,
            Category.ALERT,
            Scope.EMERGENCY,
            "red_flag_raised",
            cap=None,
            quiet=False,
            channels=(DeliveryChannel.WHATSAPP, DeliveryChannel.APP_PUSH),
        ),
        Rule(
            TriggerType.VISIT_TOMORROW,
            TriggerKind.EVENT,
            Category.REMINDER,
            Scope.VISITS,
            "visit_tomorrow",
            cap=1,
            quiet=True,
        ),
        Rule(
            TriggerType.PAPERS,
            TriggerKind.EVENT,
            Category.CONTEXT,
            Scope.RECORDS,
            "paper_waiting_for_a_yes",
            cap=1,
            quiet=True,
        ),
        Rule(
            TriggerType.FIRST_WEEK_PROMPT,
            TriggerKind.EVENT,
            Category.REMINDER,
            Scope.RECORDS,
            "first_week_prompt_due",
            cap=1,
            quiet=True,
        ),
        Rule(
            TriggerType.FAMILY_MESSAGE,
            TriggerKind.EVENT,
            Category.CONTEXT,
            Scope.SEND,
            "family_message_due",
            cap=2,
            quiet=True,
        ),
        Rule(
            TriggerType.NUDGE,
            TriggerKind.EVENT,
            Category.CONTEXT,
            Scope.PROFILE,
            "nudge_handed_over",
            cap=1,
            quiet=True,
            channels=(DeliveryChannel.APP_PUSH, DeliveryChannel.WHATSAPP),
        ),
    )
}

WINDOW_BEFORE = timedelta(hours=1)
"""A tablet may be tapped from an hour before its anchor; its window closes at the end of the
routine's "due" for that anchor (`app.routines.service.DUE_FOR`). Untapped then, the ladder
starts."""
MORNING_LATEST = timedelta(hours=3)
"""A morning card not sent by three hours after breakfast is dropped, never sent late."""


class AlertsAreNeverHeld(Refusal):
    """An alert has no cap and no quiet hours, and no setting can give it either."""


class NotASetting(Refusal):
    """A setting names a trigger type, a channel on its list at most once, and a cap from 1 to 12."""


@dataclass(frozen=True, slots=True)
class Config:
    day: Day = field(default_factory=lambda: day_of(None))
    """His day as E10-01's routine sets it: the anchors' times and the morning card's."""
    skip_quiet_days: bool = False
    quiet_from: time = QUIET_FROM
    quiet_until: time = QUIET_UNTIL
    channels: Mapping[TriggerType, tuple[DeliveryChannel, ...]] = field(default_factory=dict)
    caps: Mapping[TriggerType, int] = field(default_factory=dict)

    def channels_for(self, type: TriggerType) -> tuple[DeliveryChannel, ...]:
        return self.channels.get(type) or RULES[type].channels

    def cap_for(self, type: TriggerType) -> int | None:
        rule = RULES[type]
        if rule.cap is None:
            return None
        return self.caps.get(type, rule.cap)

    def is_quiet(self, local: datetime) -> bool:
        """Whether this moment on his wall clock is inside the quiet hours."""
        at = local.time().replace(tzinfo=None)
        if self.quiet_from > self.quiet_until:
            return at >= self.quiet_from or at < self.quiet_until
        return self.quiet_from <= at < self.quiet_until

    def anchor_at(self, anchor: str) -> time:
        return self.day.anchors[Anchor(anchor).value]

    def window(self, day: date, anchor: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
        """When a tablet at this anchor on this day of his may be tapped: opens, closes. It
        closes where the routine stops calling the anchor due: `DUE_FOR` after it, or at the
        next anchor if that comes sooner (`app.routines.service.due_at`)."""
        at = datetime.combine(day, self.anchor_at(anchor), tz)
        closes = at + DUE_FOR
        order = list(ANCHORS)
        after = order.index(Anchor(anchor).value) + 1
        if after < len(order):
            closes = min(closes, datetime.combine(day, self.day.anchors[order[after]], tz))
        return at - WINDOW_BEFORE, closes

    def morning(self, day: date, tz: ZoneInfo) -> datetime:
        """When the morning card goes: at his breakfast on this day of his — the one
        breakfast time the first week's prompt and the breakfast tablet share."""
        return datetime.combine(day, self.day.anchors["breakfast"], tz)


def config_of(
    row: DeliverySettings | None, routine: Routine | None = None, breakfast: time | None = None
) -> Config:
    day = day_of(routine, breakfast)
    if row is None:
        return Config(day=day)
    return Config(
        day=day,
        skip_quiet_days=row.skip_quiet_days,
        quiet_from=row.quiet_from or QUIET_FROM,
        quiet_until=row.quiet_until or QUIET_UNTIL,
        channels={
            TriggerType(name): tuple(DeliveryChannel(one) for one in listed)
            for name, listed in row.channels.items()
        },
        caps={TriggerType(name): int(cap) for name, cap in row.caps.items()},
    )


def check_settings(
    channels: Mapping[str, Sequence[str]], caps: Mapping[str, int]
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """The settings as they will be kept, or a refusal naming what is wrong with them."""
    kept_channels: dict[str, list[str]] = {}
    for name, listed in channels.items():
        try:
            kind = TriggerType(name)
            chosen = [DeliveryChannel(one) for one in listed]
        except ValueError as unknown:
            raise NotASetting(str(unknown)) from unknown
        if not chosen or len(set(chosen)) != len(chosen):
            raise NotASetting(f"the list for {kind.value} names each channel once, at least one")
        kept_channels[kind.value] = [one.value for one in chosen]
    kept_caps: dict[str, int] = {}
    for name, cap in caps.items():
        try:
            kind = TriggerType(name)
        except ValueError as unknown:
            raise NotASetting(str(unknown)) from unknown
        if RULES[kind].cap is None:
            raise AlertsAreNeverHeld(f"{kind.value} is an alert: it is never capped")
        if not 1 <= int(cap) <= 12:
            raise NotASetting(f"a cap for {kind.value} is from 1 to 12 a day")
        kept_caps[kind.value] = int(cap)
    return kept_channels, kept_caps
