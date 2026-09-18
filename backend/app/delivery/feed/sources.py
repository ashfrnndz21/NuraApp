"""The allowlist: which publishers a learning card may come from.

The list is data, reviewed by the pharmacist (docs/health-feed-spec.md §7); the seed below
is the first review's outcome and `ensure_sources` puts it in the table once. A source is
usable when it is allowlisted *and* approved *and* covers the profile's region; everything
else — a search result naming another domain, a source still pending — is refused by name
and written down. Sources are global, so listing them costs no scope, but only the owner
and the chief he named may see what the engine is allowed to read for him.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.db import utcnow
from app.delivery.feed.models import ReviewStatus, Source, SourceKind
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.regions import Region

SOURCE_TARGET = Source.__tablename__


class SourceNotAllowlisted(Refusal):
    """A card cites only a source on the allowlist. This one is not, or is not approved."""


class NotTheirsToManage(Refusal):
    """The engine's sources and its search jobs are the owner's and his chief's to see."""


@dataclass(frozen=True, slots=True)
class Seed:
    name: str
    domain: str
    kind: SourceKind
    regions: tuple[str, ...]
    languages: tuple[str, ...]


SEED: tuple[Seed, ...] = (
    Seed("Health Sciences Authority", "hsa.gov.sg", SourceKind.REGULATOR, ("SG",), ("en",)),
    Seed(
        "National Pharmaceutical Regulatory Agency",
        "npra.gov.my",
        SourceKind.REGULATOR,
        ("MY",),
        ("en", "ms"),
    ),
    Seed("HealthHub", "healthhub.sg", SourceKind.MINISTRY, ("SG",), ("en", "ms", "zh", "ta")),
    Seed("Ministry of Health Singapore", "moh.gov.sg", SourceKind.MINISTRY, ("SG",), ("en",)),
    Seed(
        "MyHEALTH Kementerian Kesihatan",
        "myhealth.gov.my",
        SourceKind.MINISTRY,
        ("MY",),
        ("ms", "en"),
    ),
    Seed("SingHealth", "singhealth.com.sg", SourceKind.HOSPITAL, ("SG",), ("en", "zh")),
    Seed("National Heart Centre Singapore", "nhcs.com.sg", SourceKind.HOSPITAL, ("SG",), ("en",)),
    Seed("Institut Jantung Negara", "ijn.com.my", SourceKind.HOSPITAL, ("MY",), ("ms", "en")),
    Seed("Singapore Heart Foundation", "myheart.org.sg", SourceKind.SOCIETY, ("SG",), ("en", "zh")),
    # T3, cost expectation (`app.insurance.cost_expectation`): MOH Malaysia's own domain,
    # distinct from MyHEALTH above, publishes the Fees Act 1951 schedule the fee-benchmark
    # estimator cites for a Malaysian visit. `moh.gov.sg` (Ministry of Health Singapore,
    # seeded above) already covers the Singapore side — it is where the MOH fee-benchmark
    # comparison portal and the hospital bill browser both live, so no new Singapore domain
    # is needed.
    Seed(
        "Ministry of Health Malaysia",
        "moh.gov.my",
        SourceKind.MINISTRY,
        ("MY",),
        ("ms", "en"),
    ),
)
"""The first allowlist: regulators, ministries, hospital groups and one society, both
countries. Adding to it is a pharmacist's review, not a code change made in passing."""


async def ensure_sources(session: AsyncSession) -> None:
    """Put the seed in the table, once. Idempotent by domain."""
    present = set((await session.scalars(select(Source.domain))).all())
    moment = utcnow()
    for seed in SEED:
        if seed.domain in present:
            continue
        session.add(
            Source(
                name=seed.name,
                domain=seed.domain,
                kind=seed.kind,
                regions=list(seed.regions),
                languages=list(seed.languages),
                allowlisted=True,
                review_status=ReviewStatus.APPROVED,
                added_at=moment,
            )
        )
    await session.flush()


def usable(source: Source, region: Region) -> bool:
    """Allowlisted, approved, and covering this region."""
    return (
        source.allowlisted
        and source.review_status is ReviewStatus.APPROVED
        and region.value in source.regions
    )


async def require_manager(session: AsyncSession, *, context: KeyContext, target: str) -> None:
    """The owner, the steward holding the graph for him, or a chief with the family scope.
    Anyone else is refused by name and written down under the family scope."""
    if context.is_owner or context.is_steward:
        return
    if context.role is KeyRole.CHIEF and context.allows(Scope.FAMILY):
        return
    refusal = NotTheirsToManage(f"a {context.role} key does not manage the engine")
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.FAMILY,
        target=target,
        outcome=Outcome.REFUSED,
        refused_because=type(refusal).__name__,
    )
    refusal.written_down = True
    raise refusal


async def list_sources(session: AsyncSession, *, context: KeyContext) -> Sequence[Source]:
    """The allowlist as it stands for this profile's region, for its owner or chief."""
    await require_manager(session, context=context, target=SOURCE_TARGET)
    await ensure_sources(session)
    found = (await session.scalars(select(Source).order_by(Source.name))).all()
    return [source for source in found if context.region.value in source.regions]


async def usable_sources(
    session: AsyncSession, *, region: Region, source_ids: Sequence[uuid.UUID] | None = None
) -> Sequence[Source]:
    """The sources a job may search: every usable one here, or the named ones if each is
    usable. A named source that is not is `SourceNotAllowlisted`."""
    await ensure_sources(session)
    found = (await session.scalars(select(Source))).all()
    if source_ids is None:
        return [source for source in found if usable(source, region)]
    by_id = {source.id: source for source in found}
    chosen: list[Source] = []
    for wanted in source_ids:
        source = by_id.get(wanted)
        if source is None or not usable(source, region):
            raise SourceNotAllowlisted(f"source {wanted} is not on the allowlist for {region}")
        chosen.append(source)
    return chosen


async def require_usable_source(session: AsyncSession, *, region: Region, domain: str) -> Source:
    """The allowlisted, approved source with this domain, in this region, or a refusal."""
    source = await session.scalar(select(Source).where(Source.domain == domain))
    if source is None or not usable(source, region):
        raise SourceNotAllowlisted(f"{domain} is not on the allowlist for {region}")
    return source
