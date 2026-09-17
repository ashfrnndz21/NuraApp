"""E13-01: the emergency card.

    Conditions, medicines, allergies, blood type, contacts, insurer in two languages; works
    with no data.

The card is gated by EMERGENCY (a key narrowed past it is refused and written down); it is
rendered from a State snapshot and the row names it; an emergency-only key reads it from the
last snapshot and is refused when the record has moved past it; every line is verified;
Singapore says 995 and Malaysia 999.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.channels.printable import emergency_card_html
from app.clock import FrozenClock
from app.db import utcnow
from app.drugs.registry import UnknownDrug
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import EventKind, ProviderKind, SourceChannel
from app.memory.spine import add_provider
from app.regions import Region
from app.safety.emergency_card import (
    CARD_TARGET,
    Medicine,
    _medicine_label,
    _medicines,
    compose_lines,
    emergency_card,
)
from app.safety.models import CardFormat, EmergencyCard
from app.state.service import StaleState, current_state
from tests.medicines_support import add, label
from tests.safety_support import (
    REGISTRY,
    assert_plain,
    clinic,
    fact,
    let_in,
    pa,
    trail,
    water_pill,
)


async def _ready(session: AsyncSession, *, region: Region = Region.SG):
    """Pa with a condition, an allergy, a blood type, a birth year, the water pill, a
    doctor, a reading, and Mei as chief."""
    owner = await pa(
        session, region=region, phone="+6591110031" if region is Region.SG else "+60121110031"
    )
    await fact(session, owner, subject="heart_failure", attribute="control", value="watch")
    await fact(session, owner, subject="penicillin", attribute="allergy", value="rash")
    await fact(session, owner, subject="blood_type", attribute="group", value="O+")
    await fact(session, owner, subject="person", attribute="birth_year", value=1952)
    await water_pill(session, owner)
    await clinic(session, owner)
    await record_event(
        session,
        context=owner,
        kind=EventKind.READING,
        occurred_at=utcnow(),
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    mei = await let_in(
        session,
        owner,
        phone="+6592220031" if region is Region.SG else "+60122220031",
        name="Mei",
        role=KeyRole.CHIEF,
    )
    return owner, mei


_clean = assert_plain


async def test_the_card_holds_what_a_stranger_needs_and_every_line_is_verified(
    sg: AsyncSession,
) -> None:
    owner, _mei = await _ready(sg)
    card = await emergency_card(sg, context=owner, registry=REGISTRY)

    assert card.name == "Pa" and card.language == "en" and card.emergency_number == "995"
    assert card.age_band == "70 to 79"
    assert [c.words for c in card.conditions] == ["a weak heart"]
    assert [a.words for a in card.allergies] == ["Penicillin"]
    assert card.blood_type == "O+"
    medicine = card.medicines[0]
    assert (medicine.generic, medicine.strength, medicine.amount, medicine.when) == (
        "frusemide",
        "40 mg",
        "1 tablet",
        "every morning",
    )
    # `plain_name` is his word alone, data (module doc); the register's name is `generic`,
    # separate data beside it — the parenthetical below is the *sentence*'s own doing
    # (`_medicine_label`), attempted only where the whole line still passes plain-words (#222).
    assert medicine.plain_name == "the water pill" and medicine.has_plain_name
    assert card.contacts[0].name == "Mei" and card.contacts[0].phone_e164 == "+6592220031"
    assert card.clinic is not None and card.clinic.name == "Dr Tan"
    assert card.last_reading_at is not None
    texts = [line.text for line in card.lines]
    assert texts[0] == "This is Pa's emergency card."
    assert "Pa takes the water pill (frusemide)." in texts
    assert "Pa takes 1 tablet every morning." in texts
    assert "The ambulance number is 995." in texts
    assert "Pa's blood pressure was last written down on Thursday 3 September." in texts
    assert "Pa has a weak heart." in texts
    assert "Pa is allergic to Penicillin." in texts
    assert "Pa's blood type is O positive." in texts
    assert "Mei looks after Pa." in texts and "Call Mei first." in texts
    assert "Pa sees Dr Tan." in texts
    assert texts[-1] == "This card is not a doctor's advice."
    _clean(card.lines)
    # The number and the strength are data beside the lines, never in a sentence.
    assert not any("+65" in text or "40 mg" in text for text in texts)


async def test_the_card_is_rendered_from_state_and_the_row_names_it(sg: AsyncSession) -> None:
    owner, _ = await _ready(sg)
    card = await emergency_card(sg, context=owner, registry=REGISTRY, format=CardFormat.HTML)
    state = await current_state(sg, context=owner)
    assert card.state_id == state.id
    row = await sg.get(EmergencyCard, card.card_id)
    assert row is not None and row.state_id == state.id and row.format is CardFormat.HTML
    assert row.rendered_for_person_id == owner.person_id
    assert set(row.line_ids) >= {"ec.title", "ec.medicine", "ec.chief", "ec.boundary"}
    assert row.fact_ids and all(len(one) == 36 for one in row.fact_ids)


async def test_the_card_is_gated_by_emergency_and_a_refusal_is_written_down(
    sg: AsyncSession,
) -> None:
    owner, _ = await _ready(sg)
    narrow = await let_in(
        sg, owner, phone="+6593330031", name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.MEDICINES}
    )
    assert Scope.EMERGENCY not in narrow.scopes
    with pytest.raises(OutOfScope):
        await emergency_card(sg, context=narrow, registry=REGISTRY)
    refused = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.outcome is Outcome.REFUSED and line.target == CARD_TARGET
    ]
    assert refused and refused[-1].actor_person_id == narrow.person_id
    assert refused[-1].scope is Scope.EMERGENCY


async def test_an_emergency_only_key_reads_the_card_from_the_last_snapshot(
    sg: AsyncSession,
) -> None:
    owner, _ = await _ready(sg)
    mine = await emergency_card(sg, context=owner, registry=REGISTRY)
    lin = await let_in(sg, owner, phone="+6594440031", name="Lin", role=KeyRole.EMERGENCY)
    assert lin.scopes == {Scope.PROFILE, Scope.EMERGENCY}
    theirs = await emergency_card(sg, context=lin, registry=REGISTRY)
    assert theirs.state_id == mine.state_id
    assert [line.text for line in theirs.lines] == [line.text for line in mine.lines]
    assert theirs.contacts[0].phone_e164 == "+6592220031"
    # The chief's account was read for her name and number, and the trail says so: a READ
    # of `person` under EMERGENCY by Lin's key (ADR 0002).
    reads = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.actor_person_id == lin.person_id and line.target == "person"
    ]
    assert reads and all(line.scope is Scope.EMERGENCY for line in reads)
    rows = (
        await sg.scalars(select(EmergencyCard).where(EmergencyCard.profile_id == owner.profile_id))
    ).all()
    assert {row.rendered_for_person_id for row in rows} == {owner.person_id, lin.person_id}


async def test_a_stale_card_is_refused_rather_than_shown(sg: AsyncSession) -> None:
    """A caregiver key writes a control word but cannot recompute State, so the last snapshot
    is behind the record. The emergency-only key is refused the card until a key that can
    recompute reads it; then both read the same, current, State."""
    owner, mei = await _ready(sg)
    await emergency_card(sg, context=owner, registry=REGISTRY)
    lin = await let_in(sg, owner, phone="+6594440032", name="Lin", role=KeyRole.EMERGENCY)
    caregiver = await let_in(sg, owner, phone="+6595550031", name="Ana", role=KeyRole.CAREGIVER)
    await fact(sg, caregiver, subject="diabetes", attribute="control", value="watch")

    with pytest.raises(StaleState):
        await emergency_card(sg, context=lin, registry=REGISTRY)

    fresh = await emergency_card(sg, context=mei, registry=REGISTRY)
    assert [c.code for c in fresh.conditions] == ["diabetes", "heart_failure"]
    again = await emergency_card(sg, context=lin, registry=REGISTRY)
    assert again.state_id == fresh.state_id
    assert "Pa has sugar sickness." in [line.text for line in again.lines]


async def test_malaysia_says_999_and_singapore_995(sg: AsyncSession, my: AsyncSession) -> None:
    here, _ = await _ready(sg)
    there, _ = await _ready(my, region=Region.MY)
    assert (await emergency_card(sg, context=here, registry=REGISTRY)).emergency_number == "995"
    assert (await emergency_card(my, context=there, registry=REGISTRY)).emergency_number == "999"


async def test_the_card_in_malay_and_chinese_is_verified_too(sg: AsyncSession) -> None:
    owner, _ = await _ready(sg)
    for language in ("ms", "zh"):
        card = await emergency_card(sg, context=owner, registry=REGISTRY, language=language)
        assert card.language == language
        assert_plain(card.lines, language)
    malay = await emergency_card(sg, context=owner, registry=REGISTRY, language="ms")
    # In Malay his name for it stands alone; the register's name is in the table beside it.
    assert "Pa makan pil air." in [line.text for line in malay.lines]


async def test_a_bare_profile_still_has_a_card(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110039")
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    texts = [line.text for line in card.lines]
    assert "Nura has no note of a medicine for Pa." in texts
    assert "Nura has no note of a condition for Pa." in texts
    assert "No family number is written down yet." in texts
    assert "The ambulance number is 995." in texts
    assert card.medicines == [] and card.contacts == [] and card.age_band is None


async def test_a_clinic_is_a_place_he_goes_to_and_an_old_reading_is_not_the_last(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg, phone="+6591110038")
    await add_provider(
        sg, context=owner, name="Bedok Clinic", kind=ProviderKind.CLINIC, region=Region.SG
    )
    long_ago = utcnow() - timedelta(days=400)
    await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=long_ago,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=utcnow(),
        label="weight",
        source_channel=SourceChannel.APP,
    )
    card = await emergency_card(sg, context=owner, registry=REGISTRY)
    texts = [line.text for line in card.lines]
    assert "Pa goes to Bedok Clinic." in texts
    assert card.last_reading_at is None
    assert not any("blood pressure was last" in text for text in texts)


# --- #222: no active medicine is ever withheld ----------------------------------------------


def _synthetic_line(generic: str, *, drug_class: str = "", high_risk: bool = False):
    """A `MedicationLine`-shaped stand-in with just what `_medicines` reads: enough to test
    the card's naming of a medicine without the full ingestion pipeline — irrelevant here,
    since #222 is about the sentence, not how the line got onto the record."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        fact_id=uuid.uuid4(),
        generic=generic,
        brand=None,
        strength="",
        form="tablet",
        dose={"amount": 1.0, "unit": "tablet", "frequency": "od", "anchors": ["breakfast"]},
        drug_class=drug_class,
        high_risk=high_risk,
    )


def _card_lines(medicines, language: str):
    return compose_lines(
        name="Pa",
        language=language,
        spoken_language=language,
        age=None,
        conditions=(),
        medicines=medicines,
        allergies=(),
        blood_type=None,
        contacts=(),
        clinic=None,
        last_reading_at=None,
        region=Region.SG,
    )


def test_every_active_medicine_on_the_whole_register_appears_on_the_card_in_every_language() -> (
    None
):
    """#222: asserted over the entire register, not a hand-picked drug (the #186/#215
    lesson) — a product added to the register later cannot fall outside this check.

    Measured on `main` before the fix: 26 of the register's 50 generics vanished from the
    English card (0 in Malay and Chinese, which never carry the register's chemical name in
    the sentence) — every one of them a generic #202 added that `app.safety.plain_words`'s
    glossary does not cover, so the sentence naming it failed rule 3 and was silently
    withheld (`emergency_card.py`'s old `say`, log-and-drop). None do now."""
    generics = sorted(REGISTRY.generics)
    assert len(generics) >= 50, "the fixture registry shrank; the measurement above is stale"
    lines = [_synthetic_line(generic) for generic in generics]
    for language in ("en", "ms", "zh"):
        medicines = _medicines(REGISTRY, lines, language)
        assert len(medicines) == len(generics)
        card_lines = _card_lines(medicines, language)
        assert_plain(card_lines, language)
        named = [one for one in card_lines if one.id == "ec.medicine"]
        missing = len(generics) - len(named)
        assert missing == 0, f"{language}: {missing} of {len(generics)} medicines vanished"
        # The safety net (#222) never had to fire: every medicine's own sentence rendered.
        assert not any(one.id.startswith("ec.render_issue") for one in card_lines)


def test_a_high_risk_medicine_with_no_story_still_appears_with_its_marker() -> None:
    """#222: a high-risk drug the register carries no plain-name story for (a future
    addition — this fixture's register happens to have a story for every one it lists
    today) is still named, by the register's own name, and still carries its marker."""
    generic = "oxymorphone"
    with pytest.raises(UnknownDrug):
        REGISTRY.monograph(generic)
    line = _synthetic_line(generic, drug_class="opioid", high_risk=True)
    for language in ("en", "ms", "zh"):
        medicines = _medicines(REGISTRY, [line], language)
        medicine = medicines[0]
        assert medicine.plain_name == "Oxymorphone" and not medicine.has_plain_name
        assert medicine.high_risk
        card_lines = _card_lines(medicines, language)
        assert_plain(card_lines, language)
        ids = [one.id for one in card_lines]
        assert "ec.medicine" in ids and "ec.high_risk" in ids
        named = next(one.text for one in card_lines if one.id == "ec.medicine")
        assert "Oxymorphone" in named


def test_ec_high_risk_is_probed_too_not_only_ec_medicine() -> None:
    """#229 (review on #222's own PR): `_medicine_label` must probe every template the label
    fills, not only `ec.medicine` — `ec.high_risk` wraps the same label in more words
    ("{name}'s doctor watches {medicine} closely.") and sits closer to rule 3's 15-word hard
    fail. The enriched label below passes `ec.medicine`'s probe (12 words: under it) but fails
    `ec.high_risk`'s (16 words: over it) on word count alone — nothing to do with the chemical
    name or the glossary. Before this was fixed, `ec.high_risk` — the marker a paramedic most
    needs — could fail silently while `ec.medicine` still rendered, with no trace in
    `withheld` and so no `ec.render_issue` either.

    A long, realistic (multi-word Malaysian) patient name is used throughout, deliberately:
    `theirs()` runs on it and the label before the probe now (not after, as it used to), and
    the probe itself always checks word-count against a short stand-in name (`NAME_STAND_IN`,
    "Ash") — a repo-wide property of `render()`, not specific to this fix — so the fallback
    label (plain name alone, no parenthetical) is sized here to still pass both templates with
    the *real* long name substituted in, not just the stand-in: that's what "never dropped"
    means when a real person's card is actually rendered, not just when it's probed."""
    plain = "the special morning tablet for weak tired hearts"
    generic = "abc def ghi jkl"  # a synthetic multi-word "chemical name": only its word
    # count matters here, not any real drug — it exists purely to push the *enriched* label
    # over ec.high_risk's threshold without a single long word tripping rule 3 for the wrong
    # reason (a real long generic name would trigger the same collision differently).
    medicine = Medicine(
        line_id=uuid.uuid4(),
        fact_id=uuid.uuid4(),
        generic=generic,
        brand=None,
        strength="5 mg",
        form="tablet",
        plain_name=plain,
        has_plain_name=True,
        amount="1 tablet",
        when="every morning",
        high_risk=True,
        high_risk_class="anticoagulant",
    )
    long_name = "Muhammad Firdaus Abdullah"
    label = _medicine_label(medicine, "en", long_name)
    assert label == plain, "the enriched label must fail ec.high_risk for this test to mean anything"
    card_lines = compose_lines(
        name=long_name,
        language="en",
        spoken_language="en",
        age=None,
        conditions=(),
        medicines=[medicine],
        allergies=(),
        blood_type=None,
        contacts=(),
        clinic=None,
        last_reading_at=None,
        region=Region.SG,
    )
    assert_plain(card_lines)
    ids = [one.id for one in card_lines]
    # The point of the fix: ec.high_risk is never dropped, and the general safety net never
    # had to fire for it — the label was chosen so both sentences always pass, real name and
    # all, not just the "Ash" stand-in the probe itself checks against.
    assert "ec.medicine" in ids and "ec.high_risk" in ids
    assert not any(one.id.startswith("ec.render_issue") for one in card_lines)
    medicine_text = next(one.text for one in card_lines if one.id == "ec.medicine")
    high_risk_text = next(one.text for one in card_lines if one.id == "ec.high_risk")
    assert medicine_text == f"{long_name} takes {plain}."
    assert high_risk_text == f"{long_name}'s doctor watches {plain} closely."


async def test_the_printable_page_and_the_live_card_show_the_same_medicines(
    sg: AsyncSession,
) -> None:
    """#222: a generic #202 added — not covered by the plain-words glossary, so its sentence
    used to be withheld — is on the live card, the printable page's sentences, and its data
    table, the register's own name included there whether or not the sentence could carry it."""
    owner = await pa(sg, phone="+6591110040")
    await water_pill(sg, owner)  # frusemide: glossary-safe, the parenthetical still shows
    await add(sg, owner, label("bisoprolol", "5 mg", "1 tab OD morning"))
    card = await emergency_card(sg, context=owner, registry=REGISTRY, format=CardFormat.HTML)
    assert {m.generic for m in card.medicines} == {"frusemide", "bisoprolol"}
    texts = [line.text for line in card.lines]
    assert "Pa takes the water pill (frusemide)." in texts
    # bisoprolol is not one of the glossary's few chemical names: the sentence carries his
    # plain name alone, never withheld for it.
    assert "Pa takes Pa's blood pressure tablet." in texts
    assert_plain(card.lines)
    page = emergency_card_html(card)
    assert "the water pill" in page and "(frusemide)" in page
    assert "your blood pressure tablet" in page
    # The register's own name for bisoprolol is on the page as data even though the sentence
    # could not carry it (module doc: `generic` is data for the stranger).
    assert "(bisoprolol)" in page
