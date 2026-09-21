"""`app.insurance.policy.policy_period_state` (E13-04, package 12a — the insurance passport):
the passport's own quiet state chip, a pure function of `status`, `ends_on`, `renewal_date`
and the profile's own wall-clock day — never inferred on the client, never read off a
free-text field, never the device's own clock (CLAUDE.md, "Frozen clock only").

Independent review (package 12a fix round, item 1): the first pass read only `renewal_date`,
so a paper-loaded policy — which always writes `renewal_date` as `None` and puts the printed
end date in `ends_on` (`ProposePolicy.tsx`) — showed `IN_FORCE` forever, a chip claiming
validity years past the policy's own printed end date. `policy_period_state` now reads
`ends_on` first, then `renewal_date` (`policy_period_date`), and never claims cover is
currently valid — only that a date is on file, or that it has passed."""

from __future__ import annotations

from datetime import date

import pytest

from app.insurance.policy import (
    PolicyPeriodState,
    PolicyStatus,
    policy_period_date,
    policy_period_state,
)

TODAY = date(2026, 9, 21)


@pytest.mark.parametrize(
    ("status", "renewal_date", "ends_on", "expected"),
    [
        # Active, nothing on file to say when it ends: no chip at all — Nura has nothing to
        # say a date about, never "in force" as if it knew cover was current.
        (PolicyStatus.ACTIVE, None, None, PolicyPeriodState.UNDATED),
        # Active, a renewal date still ahead, no printed end date: said with that date.
        (PolicyStatus.ACTIVE, date(2027, 3, 3), None, PolicyPeriodState.RUNS_TO),
        # Active, the renewal date is today: still covers today, so still said with the date,
        # not yet ended — the day itself is the last day it covers.
        (PolicyStatus.ACTIVE, TODAY, None, PolicyPeriodState.RUNS_TO),
        # Active, but the renewal date already passed and nobody re-typed the status: ended.
        (PolicyStatus.ACTIVE, date(2026, 1, 1), None, PolicyPeriodState.ENDED),
        # The reviewer's own probe: a paper-loaded policy, `renewal_date=None`,
        # `ends_on` years in the past — must read as ended, never "in force" forever.
        (PolicyStatus.ACTIVE, None, date(2021, 12, 31), PolicyPeriodState.ENDED),
        # `ends_on` wins over `renewal_date` when both are on file (`policy_period_date`) —
        # here `ends_on` is still ahead even though `renewal_date` already passed, and the
        # policy is read as running, never ended on a date it does not actually use.
        (PolicyStatus.ACTIVE, date(2026, 1, 1), date(2027, 3, 3), PolicyPeriodState.RUNS_TO),
        # A person's own word always wins, whatever the dates say.
        (PolicyStatus.LAPSED, None, None, PolicyPeriodState.ENDED),
        (PolicyStatus.LAPSED, date(2027, 3, 3), None, PolicyPeriodState.ENDED),
        (PolicyStatus.CANCELLED, None, None, PolicyPeriodState.ENDED),
        (PolicyStatus.CANCELLED, date(2020, 1, 1), None, PolicyPeriodState.ENDED),
    ],
)
def test_the_chip_reads_ends_on_first_then_renewal_date(
    status: PolicyStatus,
    renewal_date: date | None,
    ends_on: date | None,
    expected: PolicyPeriodState,
) -> None:
    assert (
        policy_period_state(status=status, renewal_date=renewal_date, ends_on=ends_on, today=TODAY)
        is expected
    )


def test_the_boundary_moves_with_today_not_a_fixed_offset() -> None:
    """The same policy, read a day later on the frozen clock, moves from `runs_to` to `ended`
    without anything about the policy itself changing — proves the day compared against is a
    parameter, never a `datetime.now()`/`Date.now()` baked into the function."""
    ends_on = date(2026, 9, 20)
    still_runs = policy_period_state(
        status=PolicyStatus.ACTIVE, renewal_date=None, ends_on=ends_on, today=date(2026, 9, 20)
    )
    assert still_runs is PolicyPeriodState.RUNS_TO
    a_day_later = policy_period_state(
        status=PolicyStatus.ACTIVE, renewal_date=None, ends_on=ends_on, today=date(2026, 9, 21)
    )
    assert a_day_later is PolicyPeriodState.ENDED


def test_policy_period_date_reads_ends_on_first_then_renewal_date() -> None:
    """The one function both the chip and the passport's own period line are built from
    (independent review, note 9) — a caller must never read `ends_on`/`renewal_date` apart."""
    assert policy_period_date(renewal_date=None, ends_on=None) is None
    assert policy_period_date(renewal_date=date(2027, 1, 1), ends_on=None) == date(2027, 1, 1)
    assert policy_period_date(renewal_date=None, ends_on=date(2026, 12, 31)) == date(2026, 12, 31)
    # Both on file: `ends_on` (the policy's own printed end date) wins.
    assert policy_period_date(renewal_date=date(2026, 1, 1), ends_on=date(2027, 3, 3)) == date(2027, 3, 3)
