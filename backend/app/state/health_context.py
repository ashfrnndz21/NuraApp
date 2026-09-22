"""Health Graph step one (ADR 0019 point 3; `docs/design/audit-2026-09-22.md` §7.2): the one
assembly Ask, the Analyst and intake read for the handful of things every one of them has
until now worked out its own way — active medicines (13 divergent readers, per the audit),
the person's age band (4 incompatible rules), conditions (4 implementations across 2 tables)
and language (6 definitions, 2 semantics).

This module does not fold these into the six-dimension `StateSnapshot` itself (`app.state.
dimensions.derive`) — that is a larger, riskier change (a new recompute input, a new scope in
`RECOMPUTE_SCOPES`, a migration) than "Day 1" allows, and `app.state.service`'s own module doc
already says a snapshot is "the record folded", not a cache of every reader a caller might
want. What this module gives instead is the one place those readers now live: a caller that
used to run its own query runs this function instead, so a second caller reads the exact same
rows, the exact same way, under the exact same scope — the property "one reader replaces
thirteen" needs, without touching what any route returns to the web app.

**A concrete divergence this closes**, found while wiring Ask: `app/search/ask.py` and
`app/llm/ask_agent.py` both read `MedicationLine` filtered only by `superseded_at IS NULL`,
never checking `status` — so a line a person marked stopped or held (`LineStatus.STOPPED`,
`LineStatus.HELD`), which is not superseded (no later line replaces it), was still read as
current. `app/reasoning/analyst/rule.py`, `app/safety/emergency_card.py`, `app/ingestion/
review.py` and `app/reasoning/visits/planner.py` all also require `status == ACTIVE`. Ask's
own two readers were the odd ones out; `active_medicines` below is the `status == ACTIVE`
definition, the one four of the six existing readers already agree on.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, audited_read
from app.db import as_utc, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import LineStatus, MedicationLine
from app.memory.semantic import current_facts

_SETTING_BIRTH_DECADE = ("setting", "birth_decade")
_PERSON_BIRTH_YEAR = ("person", "birth_year")
"""The two facts `app.reasoning.visits.planner._age` and `app.reasoning.analyst.rule.
_read_settings` already read, in the same order (settings first, the person fact as a
fallback) — `age_band` below is that same order, named once."""


async def active_medicines(
    session: AsyncSession, *, context: KeyContext
) -> Sequence[MedicationLine]:
    """The medicine lines that are actually current: not superseded by a later line, and not
    marked stopped or held. Replaces the ad-hoc `superseded_at IS NULL` reads in `app.search.
    ask` and `app.llm.ask_agent` (module doc) with the `status == ACTIVE` definition
    `app.reasoning.analyst.rule`, `app.safety.emergency_card`, `app.ingestion.review` and
    `app.reasoning.visits.planner` already use."""
    return await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(
            MedicationLine.superseded_at.is_(None),
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )


@dataclass(frozen=True, slots=True)
class AgeBand:
    """His age, two ways: the exact figure a range or a screening rule compares against, and
    the decade band ("70 to 79") a stranger-facing surface like the emergency card may show.
    `fact_id` is the fact either was read from, or `None` when nothing is written down —
    every caller that used to compute an age inline now gets `None` back the same way, never
    a guess."""

    exact: int | None
    band: str | None
    fact_id: uuid.UUID | None


def _band_of(exact: int) -> str | None:
    if exact < 0 or exact > 120:
        return None
    low = (exact // 10) * 10
    return f"{low} to {low + 9}"


async def age_band(
    session: AsyncSession, *, context: KeyContext, on: datetime | None = None
) -> AgeBand:
    """One age rule, replacing the four the audit counted (`app.reasoning.ranges.
    age_from_decade`, `app.reasoning.analyst.rule._read_settings`, `app.reasoning.visits.
    planner._age`, `app.safety.emergency_card.age_band`): his settings' own birth decade
    first (the decade's middle year stands for the year — "born in the 1950s" reads as 1955,
    the convention every one of the four already used for a decade), the person's exact birth
    year as a fallback when no decade was ever said. Never both read as if they agreed; the
    first one found wins, as every existing caller's own fallback order already does."""
    moment = as_utc(on or utcnow())
    said = await current_facts(
        session, context=context, subject=_SETTING_BIRTH_DECADE[0], attribute=_SETTING_BIRTH_DECADE[1]
    )
    if said:
        fact = said[-1]
        try:
            decade = int(fact.value)
        except (TypeError, ValueError):
            decade = None
        if decade is not None:
            exact = moment.year - (decade + 5)
            return AgeBand(exact=exact, band=_band_of(exact), fact_id=fact.id)
    born = await current_facts(session, context=context, subject=_PERSON_BIRTH_YEAR[0], attribute=_PERSON_BIRTH_YEAR[1])
    if born:
        fact = born[-1]
        try:
            year = int(fact.value)
        except (TypeError, ValueError):
            year = None
        if year is not None:
            # `app.reasoning.visits.planner._age`'s own fallback: the year is rounded to its
            # decade before the same "middle of the decade" arithmetic runs, the way a
            # `person.birth_year` fact this codebase writes is itself a decade estimate, not
            # a confirmed exact year (`app.safety.emergency_card.age_band` reads a different,
            # curated `held.birth_year` for the one surface that does treat it as exact — not
            # reconciled here; see this module's own doc on what "step one" does and does not
            # cover).
            decade = year // 10 * 10
            exact = moment.year - (decade + 5)
            return AgeBand(exact=exact, band=_band_of(exact), fact_id=fact.id)
    return AgeBand(exact=None, band=None, fact_id=None)


async def profile_language(session: AsyncSession, *, context: KeyContext) -> str:
    """The profile's own language, read the way `app.channels.api.capture._language` already
    reads it (the settings row every key may read) — one of the six definitions the audit
    counted, named here so a caller that only wants the profile default (not his personal
    "who this message is said to" twin, `app.onboarding.settings.his_language`) has one
    function to call instead of its own `audited_profile_read(...).language`."""
    return (await audited_profile_read(session, context)).language


__all__ = ["AgeBand", "active_medicines", "age_band", "profile_language"]
