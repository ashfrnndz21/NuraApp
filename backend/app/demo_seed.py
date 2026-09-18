"""Pa and Mei, seeded so a fresh sign-in on a demo or dev deployment opens onto a living
record (docs/deploy-demo.md), never an empty one.

`seed_demo` runs at startup — after the demo's own night-wipe check, and again whenever the
night's wipe actually empties the tables (`app.demo.wipe_if_due`) — and only on a declared
demo (`NURA_DEMO_MODE=1`) or a declared dev run (`NURA_DEV_CODE_SENDER=1`); `require_seedable`
refuses it anywhere else, the same gate every other fixture is held to (`app.fixtures`).

Every write goes through the same services every surface writes through — `grant_consent`,
`grant_key`, the medicines service (`plan`/`reconcile`/`record_dose_taken`), the memory
services (`record_event`, `assert_fact`, `store_artifact`), `write_memo`, `record_tap` — under
Pa's own `KeyContext`, never a raw insert, so his audit trail, consents and scopes are exactly
what a real sign-up and a real fortnight would leave. Nothing clinical is invented: the
medicine names and strengths come from the fixture drug registry
(`tests/fixtures/drugs/registry.json`) the same way a real add does, and the two papers carry
the values labelled by hand in `tests/fixtures/paper/*.expected.json` for the discharge letter
and the warfarin label already used across the test suite and `scripts/checkpoint.py`.

Idempotent: if Pa's own phone number already owns a profile here, this returns at once and
writes nothing more — the ordinary case on every start but the first after a night's wipe.
The one thing that can backdate a tap — the past days of `DoseTaken` behind the week's count —
uses `audited_write` directly, the same primitive `record_dose_taken` itself writes through,
because `record_dose_taken` only ever accepts today's own tap (`TapNotToday`): a seeded
history is not a phone catching up on a held tap, so it is written at the day it is dated for
rather than asked to pretend it just happened.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_write
from app.audit.models import Channel
from app.channels.api.deps import Providers
from app.clock import now
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import RecordConsent, Sharing, grant_consent
from app.consent.texts import current_version
from app.db import unit_of_work
from app.delivery.feed.area import area_draft_for, set_area
from app.delivery.triggers.deliver import Via
from app.demo_numbers import DEMO_NUMBERS
from app.drafts import AppointmentDraft, AreaDraft, FactDraft, StatusChange
from app.drugs.registry import DrugRegistry
from app.identity.models import Person
from app.identity.service import create_own_profile, find_person_by_phone, register_person
from app.keys.confirm import confirm
from app.keys.context import KeyContext, owned_profile, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import ALL_SCOPES, KeyRole, KeyWindow, Scope
from app.medicines.dose import Dose, parse_dose_text
from app.medicines.models import DoseTaken, MedicationLine
from app.medicines.service import Label, Reconciled, plan, reconcile, record_dose_taken
from app.memory.episodic import record_event, store_artifact
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    ConfidenceState,
    Event,
    EventKind,
    Fact,
    HomeCareCategory,
    Provider,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment, change_appointment_status
from app.reasoning.feelings.service import answer_tap, record_tap
from app.reasoning.feelings.words import Answer
from app.reasoning.visits.memos import write_memo
from app.reasoning.visits.models import MemoKind, MemoSource
from app.regions import REGION_TZ, Region
from app.safety.red_flags import Feeling
from app.settings import Settings

log = logging.getLogger("nura.demo_seed")

AREA: dict[Region, str] = {Region.SG: "Ang Mo Kio", Region.MY: "George Town"}
DOCTOR = "Dr Tan"

# Two real-looking providers per category, near Pa's own area (`AREA`, above) — Services'
# "Help at home" grid (board-fidelity-round-2). `address` says plainly where it is, in the
# words a directory listing would use, never an invented distance Nura has no way to check.
HOME_CARE: dict[Region, list[tuple[HomeCareCategory, str, str]]] = {
    Region.SG: [
        (HomeCareCategory.NURSING, "Amanah Home Nursing", "Serves Ang Mo Kio and nearby"),
        (HomeCareCategory.NURSING, "CareBridge Nursing Services", "Based in Ang Mo Kio"),
        (HomeCareCategory.PHYSIO, "MoveWell Physiotherapy", "Home visits around Ang Mo Kio"),
        (HomeCareCategory.PHYSIO, "Golden Years Physio Clinic", "Clinic in Ang Mo Kio"),
        (HomeCareCategory.MEALS, "Wholesome Meals on Wheels", "Delivers to Ang Mo Kio daily"),
        (HomeCareCategory.MEALS, "Kampung Kitchen Delivery", "Kitchen based in Ang Mo Kio"),
        (HomeCareCategory.TRANSPORT, "SafeRide Elder Transport", "Pickups across Ang Mo Kio"),
        (HomeCareCategory.TRANSPORT, "CityLink Medical Transport", "Serves Ang Mo Kio and nearby"),
    ],
    Region.MY: [
        (HomeCareCategory.NURSING, "Amanah Home Nursing", "Serves George Town and nearby"),
        (HomeCareCategory.NURSING, "CareBridge Nursing Services", "Based in George Town"),
        (HomeCareCategory.PHYSIO, "MoveWell Physiotherapy", "Home visits around George Town"),
        (HomeCareCategory.PHYSIO, "Golden Years Physio Clinic", "Clinic in George Town"),
        (HomeCareCategory.MEALS, "Wholesome Meals on Wheels", "Delivers to George Town daily"),
        (HomeCareCategory.MEALS, "Kampung Kitchen Delivery", "Kitchen based in George Town"),
        (HomeCareCategory.TRANSPORT, "SafeRide Elder Transport", "Pickups across George Town"),
        (HomeCareCategory.TRANSPORT, "CityLink Medical Transport", "Serves George Town and nearby"),
    ],
}


class DemoSeedOutsideDevOrDemo(RuntimeError):
    """NURA_DEMO_SEED=1 was given to a process that is neither a declared dev run nor a
    declared demo. The same gate every other fixture is held to (`app.fixtures`)."""


def require_seedable(settings: Settings) -> None:
    if not settings.fixtures_allowed:
        raise DemoSeedOutsideDevOrDemo(
            "NURA_DEMO_SEED=1 runs only on a declared dev run (NURA_DEV_CODE_SENDER=1) "
            "or demo (NURA_DEMO_MODE=1)"
        )


async def seed_demo(session: AsyncSession, settings: Settings, providers: Providers) -> None:
    """Pa's profile and Mei as his chief, idempotently. Refuses outside demo/dev."""
    require_seedable(settings)
    region = settings.region
    pa_phone, mei_phone = DEMO_NUMBERS[region]
    existing = await find_person_by_phone(session, pa_phone)
    if existing is not None and await owned_profile(
        session, region=region, owner_person_id=existing.id
    ):
        return
    log.info("demo: seeding Pa (%s) and Mei (%s)", pa_phone, mei_phone)
    async with unit_of_work(session):
        owner = await _seed_pa(session, settings, pa_phone)
        await _seed_mei(session, owner, mei_phone)
        await _seed_area(session, owner)
        medicine_lines = await _seed_medicines(session, owner, providers.drug_registry)
        blood_pressure = next(r for r in medicine_lines if r.line.generic == "amlodipine")
        await _seed_explainer_clip(session, owner, providers.drug_registry, blood_pressure)
        await _seed_readings(session, owner)
        await _seed_visits(session, owner)
        await _seed_home_care(session, owner)
        await _seed_feeling(session, owner, providers, settings)
        await _seed_papers(session, owner)
    await session.commit()


async def _seed_pa(session: AsyncSession, settings: Settings, phone: str) -> KeyContext:
    person = await register_person(
        session, region=settings.region, display_name="Pa", phone_e164=phone, language="en"
    )
    consent = RecordConsent(
        text_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
        language="en",
        captured_via=ConsentChannel.APP,
    )
    profile = await create_own_profile(
        session, region=settings.region, owner=person, consent=consent, language="en"
    )
    return await resolve_key_context(
        session, region=settings.region, person_id=person.id, profile_id=profile.id
    )


async def _seed_mei(session: AsyncSession, owner: KeyContext, phone: str) -> Person:
    mei = await register_person(
        session, region=owner.region, display_name="Mei", phone_e164=phone, language="en"
    )
    await grant_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_PERSON,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="en",
        sharing=Sharing(
            holder=mei,
            scopes=frozenset(ALL_SCOPES) - {Scope.PROFILE},
            role=KeyRole.CHIEF,
            window=KeyWindow.ALWAYS,
            relationship="daughter",
        ),
    )
    await grant_key(session, context=owner, holder=mei, role=KeyRole.CHIEF, window=KeyWindow.ALWAYS)
    return mei


async def _seed_area(session: AsyncSession, owner: KeyContext) -> None:
    area = AREA[owner.region]
    _kept, draft = await area_draft_for(session, context=owner, area=area)
    yes = await confirm(session, owner, AreaDraft(area=draft.area))
    await set_area(session, context=owner, area=area, confirmation_id=yes.id)


# --- medicines -------------------------------------------------------------------------------

MEDICINES: tuple[tuple[str, str, str, int, str], ...] = (
    # generic, strength, dose text, quantity, prescriber — from the fixture drug registry
    # (tests/fixtures/drugs/registry.json) the way a real label is read.
    ("amlodipine", "5 mg", "1 tab OD", 30, DOCTOR),
    ("atorvastatin", "20 mg", "1 tab ON", 30, DOCTOR),
    ("metformin", "500 mg", "1 tab BD", 60, DOCTOR),
)
HIGH_RISK = ("warfarin", "3 mg", "1 tab ON", 28, "Dr Lim")
"""The dispensing label the test suite already reads this medicine off of
(`tests/medicines_support.py`, `tests/safety_support.py`): warfarin at the strength the
fixture drug registry (`tests/fixtures/drugs/registry.json`) actually carries, so `plan`
resolves it to one product rather than refusing an ambiguous strength
(`app.drugs.registry.StrengthNotRead`). The prescriber is the one on the label photo's own
fixture, `tests/fixtures/paper/warfarin-label-2024-03-12.expected.json`."""


def _label(generic: str, strength: str, dose: str, quantity: int, prescriber: str) -> Label:
    return Label(
        dose=parse_dose_text(dose),
        generic=generic,
        strength=strength,
        quantity=quantity,
        prescriber=prescriber,
    )


async def _photo(session: AsyncSession, owner: KeyContext, label: str, kind: ArtifactKind) -> Artifact:
    digest = hashlib.sha256(f"nura-demo-seed:{label}".encode()).hexdigest()
    return await store_artifact(
        session,
        context=owner,
        kind=kind,
        storage_key=f"{owner.region.value.lower()}/profiles/{owner.profile_id}/{digest}",
        content_type="application/pdf" if kind is ArtifactKind.PDF else "image/jpeg",
        sha256=digest,
        captured_at=now(),
        source_channel=SourceChannel.APP,
        region=owner.region,
    )


async def _add_medicine(
    session: AsyncSession,
    owner: KeyContext,
    providers_registry: DrugRegistry,
    item: tuple[str, str, str, int, str],
) -> Reconciled:
    generic, strength, dose, quantity, prescriber = item
    photo = await _photo(session, owner, f"label-{generic}", ArtifactKind.PHOTO)
    what = _label(generic, strength, dose, quantity, prescriber)
    shown = await plan(
        session, context=owner, registry=providers_registry, label=what, source_artifact_id=photo.id
    )
    assert shown.draft is not None, shown.outcome
    yes = await confirm(session, owner, shown.draft)
    return await reconcile(
        session,
        context=owner,
        registry=providers_registry,
        label=what,
        source_artifact_id=photo.id,
        confirmation_id=yes.id,
    )


BREAKFAST = "breakfast"
DINNER = "dinner"


async def _write_past_dose(
    session: AsyncSession, owner: KeyContext, line: MedicationLine, anchor: str, taken_at: datetime
) -> DoseTaken:
    """A dose taken on a day that is not today: `record_dose_taken` only ever accepts today's
    own tap (`TapNotToday`), so a seeded day of history is written the same way it writes —
    an audited DOSE_TAKEN event, then the tap that rests on it — rather than asked to pretend
    it happened now."""
    dose = Dose.from_json(line.dose)
    event = await audited_write(
        session,
        Event,
        owner,
        Scope.MEDICINES,
        channel=Channel.APP,
        kind=EventKind.DOSE_TAKEN,
        occurred_at=taken_at,
        source_channel=SourceChannel.APP,
        label=f"taken: {line.generic}",
        artifact_id=None,
        episode_id=None,
        recorded_at=taken_at,
    )
    return await audited_write(
        session,
        DoseTaken,
        owner,
        Scope.MEDICINES,
        channel=Channel.APP,
        line_id=line.id,
        event_id=event.id,
        anchor=anchor,
        amount=dose.amount,
        taken_at=taken_at,
        late=False,
        by_person_id=owner.person_id,
    )


async def _seed_medicines(
    session: AsyncSession, owner: KeyContext, registry: DrugRegistry
) -> list[Reconciled]:
    lines: list[Reconciled] = []
    for item in MEDICINES:
        lines.append(await _add_medicine(session, owner, registry, item))
    high_risk_photo = await _photo(session, owner, "label-warfarin", ArtifactKind.PHOTO)
    what = _label(*HIGH_RISK)
    shown = await plan(
        session, context=owner, registry=registry, label=what, source_artifact_id=high_risk_photo.id
    )
    assert shown.draft is not None, shown.outcome
    yes = await confirm(session, owner, shown.draft)
    warfarin = await reconcile(
        session,
        context=owner,
        registry=registry,
        label=what,
        source_artifact_id=high_risk_photo.id,
        confirmation_id=yes.id,
    )
    lines.append(warfarin)

    # Doses today, on the real tap the app writes: every line, at its own first anchor.
    for reconciled in lines:
        dose = Dose.from_json(reconciled.line.dose)
        first_anchor = dose.scheduled_anchors[0].value if dose.scheduled_anchors else None
        await record_dose_taken(
            session, context=owner, line_id=reconciled.line.id, anchor=first_anchor
        )

    # The past week's history on the twice-daily one (metformin), so the week's count reads
    # 12 of 14: both anchors on every day but one skipped dose three days ago, and today's
    # dinner still to come.
    metformin = next(r.line for r in lines if r.line.generic == "metformin")
    today = now()
    for days_ago in range(1, 7):
        day = today - timedelta(days=days_ago)
        for anchor, hour in ((BREAKFAST, 8), (DINNER, 19)):
            if days_ago == 3 and anchor == DINNER:
                continue  # the one skipped dose
            taken_at = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            await _write_past_dose(session, owner, metformin, anchor, taken_at)
    return lines


async def _seed_explainer_clip(
    session: AsyncSession, owner: KeyContext, registry: DrugRegistry, medicine: Reconciled
) -> None:
    """A Nura-made explainer clip for Pa's new blood-pressure tablet (RE-07, item 1), so the
    demo shows the clip card and not only the publisher's kind. `RuleClipMaker` — no model,
    no network — composes the script from the same catalogue lines his medicine's own story
    already says (`app.medicines.story.medication_story`'s `purpose`), the way a real "new
    medicine" gap would once the planner offers this alongside its search job (deliberately
    not wired there yet, `app.delivery.feed.clipmaker`'s own module doc)."""
    from app.delivery.feed.clipmaker import ClipTopic, RuleClipMaker, explainer_clip_item
    from app.delivery.feed.days import today_for
    from app.medicines.story import medication_story
    from app.state.service import current_state

    line = medicine.line
    monograph = registry.monograph(line.generic)
    story = medication_story(
        generic=line.generic,
        strength=line.strength,
        dose=Dose.from_json(line.dose),
        prescriber=line.prescriber,
        change_kind=line.change_kind,
        monograph=monograph,
        language="en",  # Pa is seeded in English (`_seed_pa`)
    )
    # `story.name` is already his own words for it, "your blood pressure tablet"
    # (`app.medicines.strings.PLAIN_NAME`) — the why line names it as it is; the headline
    # capitalises it, the way every other card's headline starts a sentence.
    topic = ClipTopic(
        why_topic=story.name,
        headline=story.name[:1].upper() + story.name[1:] + ", explained",
        evidence=f"a new medicine: {line.generic} {line.strength}",
        # `story.purpose` alone (2 lines for amlodipine) makes a script under 20s: too short
        # to be the clip the card claims to be (`clipmaker.clip_length_ok`). `how_to_take`
        # says the one more thing that is genuinely his to hear before the boundary — what
        # to do with the tablet, not only what it is for — and together they land in the
        # 20-30s window (`MIN_LINES`/`MAX_LINES`, `clipmaker.py`'s own module doc).
        catalogue_lines=tuple(story.purpose) + tuple(story.how_to_take),
        doctor=DOCTOR,
    )
    script = RuleClipMaker().make(topic, "en")
    if script is None:
        return
    state = await current_state(session, context=owner)
    day = today_for(owner)
    await explainer_clip_item(
        session,
        context=owner,
        state=state,
        script=script,
        fact_ids=(str(line.fact_id),),
        scope=Scope.MEDICINES,
        day_key=day.key,
        dedupe_key=f"explainer_clip:{line.generic}",
        expires_at=day.now + timedelta(days=90),
        gap=line.generic,
    )


# --- readings ----------------------------------------------------------------------------

BP_SERIES: tuple[tuple[int, int], ...] = (
    # Fourteen days, systolic/diastolic; the most recent matches the machine's own reading
    # in `tests/fixtures/paper/bp-cuff-2026-09-14.expected.json` (138/84).
    (146, 90), (142, 88), (139, 86), (150, 92), (144, 87), (137, 84), (141, 89),
    (148, 91), (136, 83), (145, 88), (140, 85), (143, 87), (138, 84), (138, 84),
)


async def _reading(
    session: AsyncSession, owner: KeyContext, top: int, bottom: int, at: datetime
) -> Fact:
    event = await record_event(
        session,
        context=owner,
        kind=EventKind.READING,
        occurred_at=at,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    value = {"systolic": top, "diastolic": bottom}
    draft = FactDraft(
        subject="blood_pressure",
        attribute="reading",
        value=value,
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, owner, draft)
    return await assert_fact(
        session,
        context=owner,
        subject="blood_pressure",
        attribute="reading",
        value=value,
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=yes.id,
        event_id=event.id,
        valid_from=at,
    )


async def _seed_readings(session: AsyncSession, owner: KeyContext) -> None:
    today = now()
    for index, (top, bottom) in enumerate(BP_SERIES):
        days_ago = len(BP_SERIES) - 1 - index
        await _reading(session, owner, top, bottom, today - timedelta(days=days_ago))


# --- visits ------------------------------------------------------------------------------


async def _book(
    session: AsyncSession,
    owner: KeyContext,
    provider: Provider,
    at: datetime,
    purpose: str,
    steps: tuple[AppointmentStatus, ...] = (),
) -> Appointment:
    draft = AppointmentDraft(provider_id=provider.id, scheduled_at=at, purpose=purpose)
    yes = await confirm(session, owner, draft)
    visit = await book_appointment(
        session,
        context=owner,
        provider_id=provider.id,
        scheduled_at=at,
        purpose=purpose,
        confirmation_id=yes.id,
    )
    for status in steps:
        step_yes = await confirm(
            session, owner, StatusChange(appointment_id=visit.id, status=status)
        )
        visit = await change_appointment_status(
            session, context=owner, appointment_id=visit.id, status=status, confirmation_id=step_yes.id
        )
    return visit


async def _seed_visits(session: AsyncSession, owner: KeyContext) -> None:
    tan = await add_provider(
        session, context=owner, name=DOCTOR, kind=ProviderKind.DOCTOR, region=owner.region
    )
    today = now()
    checkup = await _book(
        session,
        owner,
        tan,
        today - timedelta(days=10),
        "check-up",
        steps=(AppointmentStatus.CONFIRMED, AppointmentStatus.ATTENDED),
    )
    await write_memo(
        session,
        context=owner,
        kind=MemoKind.ACTION,
        key="lighter_dinners",
        slots={},
        source=MemoSource.VISIT,
        appointment_id=checkup.id,
    )
    await _book(session, owner, tan, today + timedelta(days=7), "see Dr Tan again")


async def _seed_home_care(session: AsyncSession, owner: KeyContext) -> None:
    """Two real-looking providers per category, near his own area — Services' "Help at home"
    grid reads the same directory his doctors and clinics do, told apart by `category`."""
    for category, name, address in HOME_CARE[owner.region]:
        await add_provider(
            session,
            context=owner,
            name=name,
            kind=ProviderKind.OTHER,
            region=owner.region,
            address=address,
            category=category,
        )


# --- a feeling note -----------------------------------------------------------------------


async def _seed_feeling(
    session: AsyncSession, owner: KeyContext, providers: Providers, settings: Settings
) -> None:
    tapped = await record_tap(
        session,
        context=owner,
        word=Feeling.TIRED,
        registry=providers.drug_registry,
        store=providers.object_store,
        transcriber=providers.transcriber,
        via=Via.of(settings, providers),
    )
    if tapped.question is not None:
        await answer_tap(
            session,
            context=owner,
            tap_id=tapped.tap.id,
            answer=Answer.YESTERDAY,
            registry=providers.drug_registry,
            store=providers.object_store,
            transcriber=providers.transcriber,
            via=Via.of(settings, providers),
        )


# --- papers -----------------------------------------------------------------------------


async def _seed_papers(session: AsyncSession, owner: KeyContext) -> None:
    """A PDF report and a label photo — the discharge letter and the warfarin label, valued
    from `tests/fixtures/paper/discharge-letter-2026-08-20.expected.json` and
    `warfarin-label-2024-03-12.expected.json`, the same two the checkpoint and the paper
    accuracy harness already read."""
    report = await _photo(session, owner, "discharge-letter-2026-08-20", ArtifactKind.PDF)
    discharged_on = now().astimezone(REGION_TZ[owner.region]).replace(
        year=2026, month=8, day=20, hour=9, minute=0, second=0, microsecond=0
    )
    admitted_on = discharged_on - timedelta(days=4)
    for attribute, value, unit in (
        ("admitted_on", admitted_on.date().isoformat(), None),
        ("discharged_on", discharged_on.date().isoformat(), None),
        ("reason", "heart failure", None),
        ("weight_at_discharge", 68.5, "kg"),
    ):
        await assert_fact(
            session,
            context=owner,
            subject="discharge",
            attribute=attribute,
            value=value,
            unit=unit,
            confidence=0.9,
            artifact_id=report.id,
            valid_from=discharged_on,
        )
    # The warfarin label photo is already on his record as the high-risk medicine's own
    # source artefact (`_seed_medicines`); it is his second paper without a second write.
