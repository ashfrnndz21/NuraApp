"""The Health Analyst's weekly job: one report per profile, Monday, on the region's own clock
(`app.clock`, never `datetime.now()` — the frozen clock in a dev run or a test, the real one
otherwise). `POST /profiles/{id}/insights/stream` generates and saves on demand the same way;
this is the unattended path, run once a week by whatever scheduler a deployment already uses
for its other periodic work (the same "acting as the system" reach `app.delivery.triggers.
deliver.open_run` already uses for a profile's own delivery run).

A profile with nobody to act for it yet (no owner, no steward) is skipped, not refused: there
is no key to read its record with. A single profile's failure is logged and does not stop the
rest — the same resilience `app.delivery.feed.search._file_question` already keeps for one
filing among many.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.drugs.registry import DrugRegistry
from app.identity.models import Profile, Stewardship
from app.keys.context import KeyContext, as_the_system, resolve_key_context
from app.onboarding.settings import his_language
from app.reasoning.analyst.port import Report
from app.reasoning.analyst.provider import analyst_for
from app.reasoning.analyst.service import save_report
from app.regions import Region
from app.settings import Settings

log = logging.getLogger("nura.reasoning.analyst.weekly_job")


async def _acting_context(
    session: AsyncSession, *, region: Region, profile: Profile
) -> KeyContext | None:
    if profile.owner_person_id is not None:
        acting_id = profile.owner_person_id
    else:
        steward = await session.scalar(
            select(Stewardship).where(
                Stewardship.profile_id == profile.id, Stewardship.closed_at.is_(None)
            )
        )
        if steward is None:
            return None
        acting_id = steward.steward_person_id
    return as_the_system(
        await resolve_key_context(
            session, region=region, person_id=acting_id, profile_id=profile.id, while_closing=True
        )
    )


async def run_weekly(
    session: AsyncSession, *, settings: Settings, registry: DrugRegistry | None = None
) -> list[uuid.UUID]:
    """One report, saved, per profile in this deployment's region. Returns the ids of the
    reports written, for the caller (a scheduler, a test) to log or assert against."""
    moment = utcnow()
    profile_ids = (
        await session.scalars(select(Profile.id).where(Profile.region == settings.region))
    ).all()
    written: list[uuid.UUID] = []
    for profile_id in profile_ids:
        try:
            profile = await session.get(Profile, profile_id)
            assert profile is not None
            context = await _acting_context(session, region=settings.region, profile=profile)
            if context is None:
                continue
            language = await his_language(session, context=context)
            analyst = analyst_for(settings, registry=registry)
            report: Report | None = None
            async for event in analyst.report_stream(
                session, context=context, language=language, now=moment
            ):
                if isinstance(event, Report):
                    report = event
            assert report is not None
            row = await save_report(session, context=context, report=report)
            written.append(row.id)
        except Exception:
            log.warning("analyst weekly job: profile %s failed", profile_id, exc_info=True)
    return written


__all__ = ["run_weekly"]
