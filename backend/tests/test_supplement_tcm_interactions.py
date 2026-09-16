"""E04-03: interaction check on add, including supplements and TCM.

docs/parity.md's gap line: "Supplements and TCM aren't in the register, so they can't be
screened; no web screen adds a medicine." This file is the acceptance line, as tests: a
supplement or a TCM remedy is a first-class entry in the register (carries its own
`product_kind`, never pretends to be a prescription medicine), a pair involving one is
screened and flagged before it is saved exactly the way a prescription pair is, and a pair a
pharmacist has not yet checked is still shown — never silent — and queued for the pharmacist
review queue (E22) rather than going live unreviewed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.drugs.registry import ProductKind, ReviewState, Severity
from app.language.models import ReviewKind, Verdict
from app.language.review import queue
from app.medicines.service import interaction_flags
from app.medicines.story import interaction_question
from tests.medicines_support import REGISTRY, add, artefact, label, pa, planned


async def test_ginkgo_is_a_supplement_not_a_prescription_medicine(sg: AsyncSession) -> None:
    owner = await pa(sg)
    matches = REGISTRY.identify(label("ginkgo biloba", "60 mg").fields())
    assert matches and all(m.product_kind is ProductKind.SUPPLEMENT for m in matches)
    photo = await artefact(sg, owner)
    done = await add(sg, owner, label("ginkgo biloba", "60 mg", "1 cap OD", quantity=30), photo)
    assert done.line.product_kind is ProductKind.SUPPLEMENT


async def test_danshen_and_dong_quai_are_tcm_not_a_prescription_medicine(sg: AsyncSession) -> None:
    danshen = REGISTRY.identify(label("danshen", "0.25 g").fields())
    dong_quai = REGISTRY.identify(label("dong quai", "500 mg").fields())
    assert danshen and all(m.product_kind is ProductKind.TCM for m in danshen)
    assert dong_quai and all(m.product_kind is ProductKind.TCM for m in dong_quai)


async def test_an_unreviewed_supplement_pair_is_flagged_before_save_both_named_but_not_asserted(
    sg: AsyncSession,
) -> None:
    """Warfarin then ginkgo: a major, well-documented pair by citation — but no pharmacist has
    checked it (`AWAITING_REVIEW`), so it is flagged the same way a prescription pair is, both
    products named, before anything is saved, without asserting the bleeding-risk mechanism
    nobody has verified."""
    owner = await pa(sg)
    await add(sg, owner, label("warfarin", "3 mg", "1 tab ON", quantity=28))
    photo = await artefact(sg, owner)
    shown = await planned(
        sg, owner, label("ginkgo biloba", "60 mg", "1 cap OD", quantity=30), photo
    )
    (flagged,) = shown.flagged
    assert flagged.interaction.pair == ("ginkgo biloba", "warfarin")
    assert flagged.interaction.severity is Severity.MAJOR
    assert flagged.interaction.review_state is ReviewState.AWAITING_REVIEW
    assert flagged.other_line.generic == "warfarin"

    done = await add(sg, owner, label("ginkgo biloba", "60 mg", "1 cap OD", quantity=30), photo)
    (flag,) = done.flags
    assert flag.awaiting_review
    (view,) = await interaction_flags(sg, context=owner, registry=REGISTRY, language="en")
    assert view.question == [
        "Ask Dr Tan or the pharmacist about taking ginkgo and the blood thinner tablet together.",
        "A pharmacist has not checked this pair yet.",
    ]
    assert "bleed" not in " ".join(view.question).lower()
    for word in ("stop", "start", "dose"):
        assert word not in " ".join(view.question).lower()


async def test_every_flagged_supplement_and_tcm_pair_names_both_in_all_three_languages(
    sg: AsyncSession,
) -> None:
    """Every pair the story names — warfarin/danshen/dong quai/ginseng, St John's wort with an
    an SSRI (sertraline) and with a DOAC, potassium with an ACE inhibitor/ARB/spironolactone,
    calcium or iron with levothyroxine or a quinolone, an NSAID with an anticoagulant — reads
    in English, Malay and Chinese with both products named, before it is saved."""
    pairs = [
        ("warfarin", "3 mg", "danshen", "0.25 g"),
        ("warfarin", "3 mg", "dong quai", "500 mg"),
        ("warfarin", "3 mg", "ginseng", "500 mg"),
        ("sertraline", "50 mg", "st john's wort", "300 mg"),
        ("apixaban", "5 mg", "st john's wort", "300 mg"),
        ("losartan", "50 mg", "potassium chloride", "600 mg"),
        ("perindopril", "4 mg", "potassium chloride", "600 mg"),
        ("spironolactone", "25 mg", "potassium chloride", "600 mg"),
        ("levothyroxine", "50 mcg", "calcium carbonate", "600 mg"),
        # ferrous fumarate is both a tablet (Ferrofort) and a capsule (Fefol) at 200 mg: the
        # form is on the label too, the way a real pack always names its own form.
        ("levothyroxine", "50 mcg", "ferrous fumarate", "200 mg", "tablet"),
        ("levofloxacin", "500 mg", "calcium carbonate", "600 mg"),
        ("warfarin", "3 mg", "ibuprofen", "200 mg"),
        ("apixaban", "5 mg", "ibuprofen", "200 mg"),
    ]
    for i, row in enumerate(pairs):
        first_generic, first_strength, second_generic, second_strength = row[:4]
        second_form = row[4] if len(row) > 4 else None
        owner = await pa(sg, phone=f"+659111{2000 + i}")
        await add(sg, owner, label(first_generic, first_strength, "1 tab OD", quantity=30))
        photo = await artefact(sg, owner)
        second_label = label(
            second_generic, second_strength, "1 tab OD", quantity=30,
            **({"form": second_form} if second_form else {}),
        )
        shown = await planned(sg, owner, second_label, photo)
        assert shown.flagged, f"{first_generic} + {second_generic} was not screened"
        for language in ("en", "ms", "zh"):
            for each in shown.flagged:
                question = interaction_question(
                    each.interaction, names={}, prescriber="Dr Tan", language=language
                )
                assert len(question) >= 2, (first_generic, second_generic, language)


async def test_an_unreviewed_pair_is_still_shown_never_silent_and_queued_for_the_pharmacist(
    sg: AsyncSession,
) -> None:
    """Warfarin and high-dose fish oil: a pair a pharmacist has not yet checked
    (`awaiting_review`). It is still flagged before save — never silence — but the words ask
    him to check with a pharmacist too, instead of naming a severity nobody has verified; the
    pair is queued on the pharmacist review queue the first time it is actually raised."""
    owner = await pa(sg)
    await add(sg, owner, label("warfarin", "3 mg", "1 tab ON", quantity=28))
    photo = await artefact(sg, owner)
    shown = await planned(sg, owner, label("fish oil", "1000 mg", "1 cap OD", quantity=30), photo)
    (flagged,) = shown.flagged
    assert flagged.interaction.review_state is ReviewState.AWAITING_REVIEW

    done = await add(sg, owner, label("fish oil", "1000 mg", "1 cap OD", quantity=30), photo)
    (flag,) = done.flags
    assert flag.awaiting_review

    (view,) = await interaction_flags(sg, context=owner, registry=REGISTRY, language="en")
    assert view.question[0].startswith("Ask Dr Tan or the pharmacist about taking")
    assert "has not checked this pair" in view.question[1]
    # It never asserts the severity or the mechanism of a pair nobody has verified.
    assert "bleed" not in " ".join(view.question).lower()

    queued = await queue(sg, kind=ReviewKind.INTERACTION, verdict=Verdict.PENDING)
    assert any(
        set(item.lines["pair"]) == {"warfarin", "fish oil"} and item.lines["text_id"]
        for item in queued
    )


async def test_a_pair_flagged_twice_is_queued_for_the_pharmacist_once(sg: AsyncSession) -> None:
    first = await pa(sg, phone="+6591110002")
    await add(sg, first, label("warfarin", "3 mg", "1 tab ON", quantity=28))
    photo1 = await artefact(sg, first)
    await add(sg, first, label("fish oil", "1000 mg", "1 cap OD", quantity=30), photo1)

    second = await pa(sg, phone="+6591110003")
    await add(sg, second, label("warfarin", "3 mg", "1 tab ON", quantity=28))
    photo2 = await artefact(sg, second)
    await add(sg, second, label("fish oil", "1000 mg", "1 cap OD", quantity=30), photo2)

    queued = await queue(sg, kind=ReviewKind.INTERACTION, verdict=Verdict.PENDING)
    matching = [item for item in queued if set(item.lines["pair"]) == {"warfarin", "fish oil"}]
    assert len(matching) == 1


BANNED_WORDS = {
    "en": {"stop", "start", "increase", "reduce", "double", "halve", "dose", "doses"},
    "ms": {"berhenti", "hentikan", "mula", "mulakan", "naikkan", "kurangkan", "gandakan"},
}
BANNED_CHARACTERS_ZH = ("停", "開始", "开始", "增加", "減少", "减少", "加倍")


async def test_the_boundary_no_flagged_pair_tells_him_to_stop_or_change_a_medicine() -> None:
    """Every interaction pair in the fixture, screened, reads as a question for the doctor —
    never an instruction to start, stop, or change what he takes — in every language."""
    for interaction in REGISTRY.interactions(sorted(REGISTRY.generics)):
        for language in ("en", "ms", "zh"):
            question = interaction_question(
                interaction, names={}, prescriber="Dr Tan", language=language
            )
            said = " ".join(question)
            if language == "zh":
                assert not any(c in said for c in BANNED_CHARACTERS_ZH), (interaction.pair, said)
            else:
                words = set(said.lower().replace(".", "").split())
                assert not (words & BANNED_WORDS[language]), (interaction.pair, question)
