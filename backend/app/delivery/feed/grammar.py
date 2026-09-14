"""Card grammar (E11-03): one number, one direction, one colour, one action.

docs/00-MASTER-BUILD-SPEC.md §9 and docs/design-system.md: a card shows at most one number —
one measurement; "138 over 84" is one reading — and at most one direction beside it (up, down,
the same); one colour, which is the State wash it was rendered under — stable, watch or act,
never red and never an alarm fill; and one action. `Grammar` is the four, and they are
columns on the row. `check` is the rule, and `items.create_item` runs it before a card is
written, so a card that breaks it is refused (`NotCardGrammar`) the way a card with a failing
line is. The headline carries no more than one number (the day, "Monday 14 September", is a
day and not a number), and a card that names a number says it in its words.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.delivery.feed.models import CardType, DeliverTo
from app.errors import Refusal
from app.keys.scopes import Scope
from app.medicines.strings import DAY_NAMES, MONTH_NAMES
from app.state.models import Posture


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    SAME = "same"


class Colour(StrEnum):
    """The wash the card sits on: State's, and nothing else. There is no red here."""

    STABLE = "stable"
    WATCH = "watch"
    ACT = "act"


class Action(StrEnum):
    """The one thing a card asks of the person holding it."""

    TAKEN = "taken"
    HEAR = "hear"
    KEEP_GOING = "keep_going"
    CALL = "call"
    ASK_TO_ORDER = "ask_to_order"
    OPEN = "open"
    ASK_THE_DOCTOR = "ask_the_doctor"


COLOUR_OF: dict[Posture, Colour] = {
    Posture.STABLE: Colour.STABLE,
    Posture.WATCH: Colour.WATCH,
    Posture.ACT: Colour.ACT,
}
"""State's posture is the wash (docs/design-system.md: the background is the status)."""


class NotCardGrammar(Refusal):
    """The card breaks its grammar: one number, one direction, one colour, one action."""


@dataclass(frozen=True, slots=True)
class Grammar:
    colour: Colour
    action: Action
    number: str | None = None
    """One measurement, as digits: `7`, `62.5`, or one reading `138/84`."""
    direction: Direction | None = None


ONE_NUMBER = re.compile(r"^\d{1,4}(?:[.,]\d{1,2})?(?:/\d{1,4})?$")
DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
_DAYS = re.compile(
    r"(?:"
    + "|".join(sorted({name for names in DAY_NAMES.values() for name in names if name.isascii()}))
    + r")\s+\d{1,2}\s+(?:"
    + "|".join(sorted({name for names in MONTH_NAMES.values() for name in names if name.isascii()}))
    + r")"
    + r"|\d{1,2}月\d{1,2}日(?:星期[一二三四五六日天])?"
)


def numbers_in(text: str) -> list[str]:
    """The numbers a line says, the spoken day and date left out."""
    return DIGITS.findall(_DAYS.sub(" ", text))


def check(grammar: Grammar, *, headline: str, body: Sequence[str]) -> None:
    """Refuse a card that breaks the grammar. Every problem is named in the refusal."""
    problems: list[str] = []
    if not isinstance(grammar.colour, Colour):
        problems.append(f"the colour is the State wash, never {grammar.colour!r}")
    if not isinstance(grammar.action, Action):
        problems.append("a card has exactly one action")
    if grammar.direction is not None and grammar.number is None:
        problems.append("a direction sits beside a number")
    if grammar.number is not None:
        if not ONE_NUMBER.match(grammar.number):
            problems.append("a card shows one number: one value or one reading")
        else:
            said = {part.replace(",", ".") for part in numbers_in(" ".join((headline, *body)))}
            parts = {part.replace(",", ".") for part in grammar.number.split("/")}
            if not parts <= said:
                problems.append("a card says the number it shows")
    if len(numbers_in(headline)) > 1:
        problems.append("a headline carries one number at most")
    if problems:
        raise NotCardGrammar("; ".join(problems))


def action_for(type: CardType, scope: Scope, deliver_to: DeliverTo) -> Action:
    """The one action each kind of card has."""
    if type is CardType.FLAG:
        return Action.CALL if deliver_to is DeliverTo.PATIENT else Action.OPEN
    if type is CardType.NOW:
        if scope is Scope.MEDICINES:
            return Action.TAKEN
        return Action.HEAR if scope is Scope.VISITS else Action.KEEP_GOING
    if type is CardType.REORDER:
        return Action.ASK_TO_ORDER
    if type is CardType.GATE:
        return Action.KEEP_GOING
    if type is CardType.DUTY:
        return Action.OPEN
    if type is CardType.QUESTION:
        return Action.ASK_THE_DOCTOR
    return Action.HEAR


def colour_for(posture: Posture) -> Colour:
    return COLOUR_OF[posture]
