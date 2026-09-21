"""`app.insurance.policy.policy_period_state` (E13-04, package 12a — the insurance passport):
the passport's own quiet state chip, a pure function of `status`, `renewal_date` and the
profile's own wall-clock day — never inferred on the client, never read off a free-text field,
never the device's own clock (CLAUDE.md, "Frozen clock only")."""

from __future__ import annotations

from datetime import date

import pytest

from app.insurance.policy import PolicyPeriodState, PolicyStatus, policy_period_state

TODAY = date(2026, 9, 21)


@pytest.mark.parametrize(
    ("status", "renewal_date", "expected"),
    [
        # Active, nothing on file to say when it ends: in force.
        (PolicyStatus.ACTIVE, None, PolicyPeriodState.IN_FORCE),
        # Active, a renewal date still ahead: said with the date.
        (PolicyStatus.ACTIVE, date(2027, 3, 3), PolicyPeriodState.ENDS_ON),
        # Active, the renewal date is today: still covers today, so still said with the date,
        # not yet ended — the day itself is the last day it covers.
        (PolicyStatus.ACTIVE, TODAY, PolicyPeriodState.ENDS_ON),
        # Active, but the renewal date already passed and nobody re-typed the status: ended.
        (PolicyStatus.ACTIVE, date(2026, 1, 1), PolicyPeriodState.ENDED),
        # A person's own word always wins, whatever the dates say.
        (PolicyStatus.LAPSED, None, PolicyPeriodState.ENDED),
        (PolicyStatus.LAPSED, date(2027, 3, 3), PolicyPeriodState.ENDED),
        (PolicyStatus.CANCELLED, None, PolicyPeriodState.ENDED),
        (PolicyStatus.CANCELLED, date(2020, 1, 1), PolicyPeriodState.ENDED),
    ],
)
def test_the_chip_follows_status_then_the_renewal_date(
    status: PolicyStatus, renewal_date: date | None, expected: PolicyPeriodState
) -> None:
    assert policy_period_state(status=status, renewal_date=renewal_date, today=TODAY) is expected


def test_the_boundary_moves_with_today_not_a_fixed_offset() -> None:
    """The same policy, read a day later on the frozen clock, moves from `ends_on` to `ended`
    without anything about the policy itself changing — proves the day compared against is a
    parameter, never a `datetime.now()`/`Date.now()` baked into the function."""
    renewal_date = date(2026, 9, 20)
    still_covers = policy_period_state(
        status=PolicyStatus.ACTIVE, renewal_date=renewal_date, today=date(2026, 9, 20)
    )
    assert still_covers is PolicyPeriodState.ENDS_ON
    a_day_later = policy_period_state(
        status=PolicyStatus.ACTIVE, renewal_date=renewal_date, today=date(2026, 9, 21)
    )
    assert a_day_later is PolicyPeriodState.ENDED
