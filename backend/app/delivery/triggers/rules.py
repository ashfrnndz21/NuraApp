"""What each trigger is, and the clock of his day it runs on (E00-05, E11-05, E11-10).

A trigger is one of three kinds: a rule (an hour or a date reached — breakfast, the end of a
dose's window, the reorder date), a pattern (arithmetic on events over a window — three
untapped doses in seven days, a count and never a diagnosis) or an event (something new — a
red flag, a paper waiting for a yes, a visit tomorrow, a family message come due). Each has a
type, and the type says what it speaks of (`scope`: a recipient's key must cover it), where
it goes first (`channels`: app push, then WhatsApp, then the caregiver, by default), how many
a person may have of it in his day (`cap`) and whether it waits out the quiet hours. An
alert — a red flag — has no cap and no quiet hours, and no setting can give it either.

A profile changes the defaults with `DeliverySettings` (E11-05): the list and the cap per
type, the quiet hours, the breakfast time the morning card and the breakfast tablet hang on
(07:30 on his wall clock until a routine says otherwise, E11-10), and whether a quiet day's
morning card is skipped. `Config` is those settings read over the defaults.
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
            TriggerType.FAMILY_MESSAGE,
            TriggerKind.EVENT,
            Category.CONTEXT,
            Scope.SEND,
            "family_message_due",
            cap=2,
            quiet=True,
        ),
    )
}

BREAKFAST_AT = time(7, 30)
"""The breakfast anchor on his wall clock until the family or a routine says otherwise."""
ANCHOR_AT: Mapping[Anchor, time] = {
    Anchor.BREAKFAST: BREAKFAST_AT,
    Anchor.LUNCH: time(12, 30),
    Anchor.DINNER: time(18, 30),
    Anchor.BED: time(21, 0),
}
WINDOW_BEFORE = timedelta(hours=1)
WINDOW_AFTER = timedelta(hours=2)
"""A dose's window: an hour before its anchor to two hours after. Untapped at the end of it,
the ladder starts."""
MORNING_LATEST = timedelta(hours=3)
"""A morning card not sent by three hours after breakfast is dropped, never sent late."""


class AlertsAreNeverHeld(Refusal):
    """An alert has no cap and no quiet hours, and no setting can give it either."""


class NotASetting(Refusal):
    """A setting names a trigger type, a channel on its list at most once, and a cap from 1 to 12."""


@dataclass(frozen=True, slots=True)
class Config:
    breakfast_at: time = BREAKFAST_AT
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
        if anchor == Anchor.BREAKFAST.value:
            return self.breakfast_at
        return ANCHOR_AT[Anchor(anchor)]

    def window(self, day: date, anchor: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
        """When a dose at this anchor on this day of his may be tapped: opens, closes."""
        at = datetime.combine(day, self.anchor_at(anchor), tz)
        return at - WINDOW_BEFORE, at + WINDOW_AFTER

    def breakfast(self, day: date, tz: ZoneInfo) -> datetime:
        return datetime.combine(day, self.breakfast_at, tz)


def config_of(row: DeliverySettings | None) -> Config:
    if row is None:
        return Config()
    return Config(
        breakfast_at=row.breakfast_at or BREAKFAST_AT,
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
