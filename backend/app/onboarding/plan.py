"""The first week (E01-04): what to snap next, one prompt a day, from tomorrow at breakfast.

When a biography closes, the gaps it left open (`app.onboarding.gaps`) become the plan: seven
at most, tier first, one a day from the next morning at his breakfast time on his own wall
clock (`REGION_TZ` of the profile's region), 08:00 when he has not said. A prompt is pending
until what it asks for arrives — by any route: the paper it asks for, a fact from any card, a
reading he types, a visit booked — and is then done, naming the fact that closed it when a
fact did; or he says Later and it is skipped. He can say Later once and be asked
again at the back of the week; a second Later retires it. The whole plan stops once the
record holds his medicines, his last visit and his next visit (the story's acceptance line): nothing is due
after that, whatever is still pending.

`due_prompts(session, context=, at=)` is what a surface that delivers — Today, WhatsApp —
asks for the prompt due at `at`: never more than one a day (docs/gaps-and-unlocks.md §4),
the earliest pending one whose morning has come. `at` says which moment is being asked
about, the way the timeline's `at` does; every timestamp written here reads the clock.

Closing is eager and lazy. The memory store's `after_fact_write` hook (registered by
`app.onboarding`) closes a prompt the moment a fact that can close one lands, in the same
unit of work, and names that fact. Every read of the plan reconciles first, so a visit booked
or a key cut — which write no fact — closes its prompt the next time the plan is read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext, OutOfScope
from app.keys.scopes import Scope, scope_for_subject
from app.memory.models import ConfidenceState, Fact
from app.onboarding.gaps import (
    BY_CODE,
    MEDICINE_SUBJECTS,
    STOP_PARTS,
    Gap,
    Known,
    closes_a_gap,
    what_is_known,
    what_stops,
)
from app.onboarding.models import (
    PLAN_IN_PROGRESS,
    ActivationPlan,
    PlanPrompt,
    PromptStatus,
)
from app.onboarding.settings import BREAKFAST, CONDITION, a_setter, clock_time
from app.regions import REGION_TZ

PLAN_LENGTH = 7
"""One prompt a day for the first week."""

DEFAULT_BREAKFAST = time(8, 0)
"""When he has not said when he has breakfast: eight on his clock, until he does."""

PLAN_SCOPE = Scope.RECORDS
"""The plan is about what the record holds and does not: read and written under the record."""

PLAN = ActivationPlan.__tablename__
PROMPT = PlanPrompt.__tablename__


class NoPlan(Refusal):
    """No first-week plan on this profile yet: one is made when a biography closes."""


class NoSuchPrompt(Refusal):
    """The plan has no prompt for that gap."""


class PromptAlreadySettled(Refusal):
    """This prompt is done or skipped already."""


@dataclass(frozen=True, slots=True)
class PlanView:
    """The latest plan, its prompts in day order, and which of the three things that stop it
    the record holds."""

    plan: ActivationPlan
    prompts: Sequence[PlanPrompt]
    stopped_because: tuple[str, ...]

    @property
    def stopped(self) -> bool:
        return len(self.stopped_because) == len(STOP_PARTS)


async def make_plan(
    session: AsyncSession,
    *,
    context: KeyContext,
    session_id: object,
    gaps: Sequence[Gap],
    breakfast: time | None,
) -> tuple[ActivationPlan, list[PlanPrompt]]:
    """The plan for the gaps left open, one a day from tomorrow at breakfast, his clock."""
    tz = REGION_TZ[context.region]
    moment = utcnow()
    first_day = moment.astimezone(tz).date() + timedelta(days=1)
    at = breakfast or DEFAULT_BREAKFAST
    plan = await audited_write(
        session,
        ActivationPlan,
        context,
        PLAN_SCOPE,
        session_id=session_id,
        breakfast_time=clock_time(at),
        first_day=first_day,
        created_by_person_id=context.person_id,
        created_at=moment,
    )
    prompts: list[PlanPrompt] = []
    for day, gap in enumerate(gaps[:PLAN_LENGTH], start=1):
        local = datetime.combine(first_day + timedelta(days=day - 1), at, tzinfo=tz)
        prompts.append(
            await audited_write(
                session,
                PlanPrompt,
                context,
                PLAN_SCOPE,
                plan_id=plan.id,
                day=day,
                gap=gap.code,
                due_at=local.astimezone(UTC),
                status=PromptStatus.PENDING,
            )
        )
    return plan, prompts


async def latest_plan(session: AsyncSession, *, context: KeyContext) -> ActivationPlan | None:
    found = await audited_read(session, ActivationPlan, context, PLAN_SCOPE)
    return max(found, key=lambda plan: as_utc(plan.created_at)) if found else None


async def _prompts(
    session: AsyncSession, *, context: KeyContext, plan: ActivationPlan
) -> list[PlanPrompt]:
    found = await audited_read(
        session, PlanPrompt, context, PLAN_SCOPE, where=(PlanPrompt.plan_id == plan.id,)
    )
    return sorted(found, key=lambda prompt: (as_utc(prompt.due_at), prompt.day))


def _known_from(fact: Fact) -> Known:
    """What this one fact alone would tell the gap rules: whether it is the one that closed a
    prompt, and so the one the prompt names."""
    key = (fact.subject, fact.attribute)
    return Known(
        conditions=frozenset({fact.attribute})
        if fact.subject == CONDITION and fact.value is True
        else frozenset(),
        subjects=frozenset({fact.subject}),
        attributes=frozenset({fact.attribute}),
        medicines=fact.subject in MEDICINE_SUBJECTS,
        breakfast_set=key == BREAKFAST and bool(fact.value),
    )


async def _settle(
    session: AsyncSession,
    *,
    context: KeyContext,
    plan: ActivationPlan,
    prompts: Sequence[PlanPrompt],
    known: Known,
    fact: Fact | None = None,
) -> None:
    """Mark done every pending prompt whose gap the record has now closed; name `fact` on the
    ones that fact closed by itself."""
    moment = utcnow()
    alone = None if fact is None else _known_from(fact)
    session.info[PLAN_IN_PROGRESS] = plan.id
    try:
        for prompt in prompts:
            gap = BY_CODE.get(prompt.gap)
            if prompt.status is not PromptStatus.PENDING or gap is None or not gap.closed(known):
                continue
            prompt.status = PromptStatus.DONE
            prompt.done_at = moment
            if fact is not None and alone is not None and gap.closed(alone):
                prompt.done_by_fact_id = fact.id
            await session.flush()
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=PLAN_SCOPE,
                target=PROMPT,
                target_id=prompt.id,
                rows=1,
            )
    finally:
        session.info.pop(PLAN_IN_PROGRESS, None)


async def _view(session: AsyncSession, *, context: KeyContext, plan: ActivationPlan) -> PlanView:
    prompts = await _prompts(session, context=context, plan=plan)
    known = await what_is_known(session, context=context)
    await _settle(session, context=context, plan=plan, prompts=prompts, known=known)
    return PlanView(plan=plan, prompts=prompts, stopped_because=what_stops(known))


@audited(Action.READ, PLAN_SCOPE, PLAN)
async def current_plan(session: AsyncSession, *, context: KeyContext) -> PlanView:
    """The latest plan, reconciled against the record first."""
    plan = await latest_plan(session, context=context)
    if plan is None:
        raise NoPlan(f"no first-week plan on profile {context.profile_id}")
    return await _view(session, context=context, plan=plan)


@audited(Action.READ, PLAN_SCOPE, PROMPT)
async def due_prompts(
    session: AsyncSession, *, context: KeyContext, at: datetime
) -> list[PlanPrompt]:
    """The prompt due at `at`: the earliest pending one whose morning has come — one, never
    more — or none: none before the first morning, none once every prompt is settled, and
    none at all once the plan has stopped. A profile with no plan has nothing due."""
    plan = await latest_plan(session, context=context)
    if plan is None:
        return []
    return due_in(await _view(session, context=context, plan=plan), at)


def due_in(view: PlanView, at: datetime) -> list[PlanPrompt]:
    """The prompt of this plan due at `at`, by the rule `due_prompts` states."""
    if view.stopped:
        return []
    moment = as_utc(at)
    ready = [
        prompt
        for prompt in view.prompts
        if prompt.status is PromptStatus.PENDING and as_utc(prompt.due_at) <= moment
    ]
    return sorted(ready, key=lambda prompt: (as_utc(prompt.due_at), prompt.day))[:1]


@audited(Action.WRITE, PLAN_SCOPE, PROMPT)
async def skip_prompt(session: AsyncSession, *, context: KeyContext, gap: str) -> PlanPrompt:
    """He said Later: the prompt is skipped. It stays in the plan, for the caregiver's list."""
    a_setter(context)
    plan = await latest_plan(session, context=context)
    if plan is None:
        raise NoPlan(f"no first-week plan on profile {context.profile_id}")
    view = await _view(session, context=context, plan=plan)
    found = next((prompt for prompt in view.prompts if prompt.gap == gap), None)
    if found is None:
        raise NoSuchPrompt(f"the plan has no prompt {gap!r}")
    if found.status is not PromptStatus.PENDING:
        raise PromptAlreadySettled(f"prompt {gap!r} is {found.status}")
    session.info[PLAN_IN_PROGRESS] = plan.id
    try:
        found.status = PromptStatus.SKIPPED
        found.skipped_at = utcnow()
        found.skipped_by_person_id = context.person_id
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=PLAN_SCOPE,
            target=PROMPT,
            target_id=found.id,
            rows=1,
        )
    finally:
        session.info.pop(PLAN_IN_PROGRESS, None)
    return found


RETIRED_AFTER = 2
"""A second Later retires the prompt (docs/gaps-and-unlocks.md §4)."""


@audited(Action.WRITE, PLAN_SCOPE, PROMPT)
async def later_prompt(session: AsyncSession, *, context: KeyContext, gap: str) -> PlanPrompt:
    """He said Later (docs/gaps-and-unlocks.md §4). The first Later sends the prompt to the
    back of the week — the morning after the last one still pending — so it is asked once
    more; a second Later retires it (skipped), and it stays in the plan for the caregiver's
    list."""
    a_setter(context)
    plan = await latest_plan(session, context=context)
    if plan is None:
        raise NoPlan(f"no first-week plan on profile {context.profile_id}")
    view = await _view(session, context=context, plan=plan)
    found = next((prompt for prompt in view.prompts if prompt.gap == gap), None)
    if found is None:
        raise NoSuchPrompt(f"the plan has no prompt {gap!r}")
    if found.status is not PromptStatus.PENDING:
        raise PromptAlreadySettled(f"prompt {gap!r} is {found.status}")
    moment = utcnow()
    last = max(
        as_utc(prompt.due_at) for prompt in view.prompts if prompt.status is PromptStatus.PENDING
    )
    session.info[PLAN_IN_PROGRESS] = plan.id
    try:
        found.deferred = found.deferred + 1
        if found.deferred >= RETIRED_AFTER:
            found.status = PromptStatus.SKIPPED
            found.skipped_at = moment
            found.skipped_by_person_id = context.person_id
        else:
            found.due_at = max(last, as_utc(found.due_at)) + timedelta(days=1)
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=PLAN_SCOPE,
            target=PROMPT,
            target_id=found.id,
            rows=1,
        )
    finally:
        session.info.pop(PLAN_IN_PROGRESS, None)
    return found


async def close_prompts_on_fact(session: AsyncSession, context: KeyContext, fact: Fact) -> None:
    """The eager half of "a gap closes itself the moment its fact arrives": registered on
    `app.memory.semantic.after_fact_write`. A dispute closes nothing. A fact that cannot close
    any gap costs nothing; a writer whose key does not open the plan leaves it to the next
    read, and the fact lands either way."""
    if fact.confidence_state is ConfidenceState.DISPUTED or not closes_a_gap(fact):
        return
    if not context.allows(PLAN_SCOPE) or not context.allows(scope_for_subject(fact.subject)):
        return
    try:
        plan = await latest_plan(session, context=context)
        if plan is None:
            return
        pending = [
            prompt
            for prompt in await _prompts(session, context=context, plan=plan)
            if prompt.status is PromptStatus.PENDING
        ]
        if not pending:
            return
        known = await what_is_known(session, context=context)
        await _settle(session, context=context, plan=plan, prompts=pending, known=known, fact=fact)
    except OutOfScope:
        return
