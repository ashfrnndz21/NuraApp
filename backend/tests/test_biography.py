"""E01-02: the health biography session.

Acceptance: a shoebox of 30 documents becomes a reconciled record in one sitting.

The sitting walks its steps — about you, papers, read-back, questions, closed — worked out
from the record; every paper goes through the capture path and is confirmed on its card; the
read-back reads the confirmed facts back in plain words, a yes his confirm, a no a dispute
that leaves the fact standing; the questions ask for what the papers did not say; the close
counts it all in his words and makes the first week. Every refusal is on the trail.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy

from app.memory.models import Artifact, ArtifactKind, ConfidenceState, Fact
from app.safety.plain_words import verify
from tests.api import let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.onboarding_support import (
    KIT,
    PA,
    SETTINGS,
    add_paper,
    answers,
    call,
    refused,
    stewarded,
    through_the_papers,
)
from tests.paper import DISCHARGE_LETTER, LIPID_PANEL, WARFARIN_LABEL, placeholder_pdf

READ_BACK_MS = [
    "Anda beritahu kami: Darah tinggi.",
    "Anda beritahu kami: Kolesterol tinggi.",
    "Anda beritahu kami: Kencing manis.",
    "Anda beritahu kami: Masuk hospital tahun lepas.",
    "Anda beritahu kami: Ubat cair darah.",
    "Doktor anda ialah Dr Tan.",
    "Kolesterol anda 230 pada Khamis 7 September 2023.",
    "Kolesterol baik anda 73 pada Khamis 7 September 2023.",
    "Kolesterol jahat anda 152 pada Khamis 7 September 2023.",
    "Label ini untuk ubat cair darah anda, Warfarin.",
    "Label ini menyebut 1 biji sekali sehari waktu malam.",
    "Label ini kata Dr Lim yang beri ubat ini.",
]
"""What Mei reads back for Pa, in his language: what he told, then each paper's facts."""

LDL_MS = "Kolesterol jahat anda 152 pada Khamis 7 September 2023."


async def test_the_sitting_walks_its_steps_and_reads_the_papers_back(
    deployment: Deployment,
) -> None:
    mei, profile_id = await stewarded(deployment)
    base = f"/profiles/{profile_id}/biography"
    her = mei["token"]

    await refused(deployment, "GET", base, her, 404, "NoBiography")
    opened = await call(deployment, "POST", base, her, 201)
    assert opened["step"] == "about_you" and opened["next"] == "save_settings"
    assert opened["language"] == "ms"
    assert opened["prompt"]["headline"] == "Sedikit tentang anda"
    assert opened["prompt"]["lines"][0] == "Beritahu kami bahasa yang anda paling suka."
    assert opened["read_back"] == [] and opened["questions"] == []

    await call(deployment, "PUT", f"/profiles/{profile_id}/settings", her, 200, json=SETTINGS)
    after = await call(deployment, "GET", base, her, 200)
    assert after["step"] == "papers" and after["next"] == "add_paper"

    added = await call(
        deployment,
        "POST",
        f"{base}/papers",
        her,
        201,
        json={**_paper(LIPID_PANEL, "lab_result")},
    )
    assert added["paper"]["paper"] == "lab_result" and added["paper"]["position"] == 0
    assert added["card"]["document_kind"] == "lab_report" and len(added["card"]["fields"]) == 7
    waiting = await call(deployment, "GET", base, her, 200)
    assert waiting["step"] == "papers" and waiting["next"] == "confirm_cards"
    assert waiting["open_cards"] == 1 and waiting["read_back"] == []
    await refused(
        deployment, "POST", f"{base}/read-back", her, 409, "CardsStillOpen", json={"answers": []}
    )

    from tests.onboarding_support import confirm_card

    await confirm_card(deployment, her, profile_id, added["card"], triglycerides=54)
    await add_paper(deployment, her, profile_id, WARFARIN_LABEL, "medicine")
    ready = await call(deployment, "GET", base, her, 200)
    assert ready["step"] == "read_back" and ready["next"] == "read_back"
    assert [p["paper"] for p in ready["papers"]] == ["lab_result", "medicine"]
    assert [line["line"] for line in ready["read_back"]] == READ_BACK_MS
    assert ready["prompt"]["headline"] == "Ini yang Nura faham"
    for line in ready["read_back"]:
        assert not [f for f in verify(line["line"], "ms") if f.severity == "fail"], line

    # A line missing is refused, and so is a line it did not read.
    partial = answers(ready)[1:]
    await refused(
        deployment,
        "POST",
        f"{base}/read-back",
        her,
        400,
        "NotEveryLineAnswered",
        json={"answers": partial},
    )
    stranger = [*partial, {"fact_id": str(uuid.uuid4()), "answer": "yes"}]
    await refused(
        deployment,
        "POST",
        f"{base}/read-back",
        her,
        400,
        "NotEveryLineAnswered",
        json={"answers": stranger},
    )

    ldl_before = await _fact(deployment, profile_id, her, "lipid_panel", "ldl")
    answered = await call(
        deployment,
        "POST",
        f"{base}/read-back",
        her,
        200,
        json={"answers": answers(ready, no=lambda line: line == LDL_MS)},
    )
    assert answered["step"] == "questions" and answered["next"] == "close"
    said = {line["line"]: line for line in answered["read_back"]}
    assert said[LDL_MS]["answer"] == "no" and said[LDL_MS]["dispute_fact_id"]
    assert all(
        line["answer"] == "yes" and line["dispute_fact_id"] is None
        for text, line in said.items()
        if text != LDL_MS
    )

    # The "no" is a dispute beside the fact: the fact still holds, and the dispute names it,
    # the photo it came from, the moment of the read-back and Mei's yes.
    assert await _fact(deployment, profile_id, her, "lipid_panel", "ldl") == ldl_before
    async with deployment.sessions() as session:
        dispute = await session.get(Fact, uuid.UUID(said[LDL_MS]["dispute_fact_id"]))
        assert dispute is not None
        assert dispute.confidence_state is ConfidenceState.DISPUTED
        assert str(dispute.supersedes_id) == ldl_before["fact_id"]
        assert str(dispute.artifact_id) == ldl_before["artifact_id"]
        assert dispute.event_id is not None and dispute.value == 152
        assert str(dispute.confirmed_by_person_id) == mei["person_id"]

    assert answered["after_no"] == "Mei akan lihat surat itu sekali lagi."
    assert [q["line"] for q in answered["questions"]] == [
        "Adakah anda periksa tekanan darah di rumah?",
        "Adakah anda ada surat hospital anda?",
        "Bila ujian gula anda yang terakhir?",
        "Bila ujian buah pinggang anda yang terakhir?",
    ]
    assert [q["question_id"] for q in answered["questions"]] == [
        "bp_numbers",
        "discharge_letter",
        "sugar_result",
        "kidney_result",
    ]
    assert all(q["kept"] is None for q in answered["questions"])
    assert answered["more"] == "3 lagi boleh tunggu kemudian."
    await refused(
        deployment,
        "POST",
        f"{base}/read-back",
        her,
        409,
        "AlreadyReadBack",
        json={"answers": answers(ready)},
    )

    closed = await call(deployment, "POST", f"{base}/close", her, 200)
    summary = closed["summary"]
    assert (summary["papers"], summary["facts"], summary["disputes"]) == (2, 13, 1)
    assert (summary["conditions"], summary["medicines"], summary["prompts"]) == (5, 1, 7)
    assert summary["lines"] == [
        "Nura simpan 2 surat anda.",
        "Nura catat 13 perkara daripada surat-surat anda.",
        "Anda kata satu baris tidak betul.",
        "Mei akan lihat surat itu sekali lagi.",
        "Esok waktu sarapan, Nura akan minta satu perkara lagi.",
        "Ada 7 perkara untuk diminta, satu setiap hari.",
        "Halaman Hari Ini anda datang daripada apa yang anda beritahu kami.",
    ]
    assert closed["biography"]["step"] == "closed" and closed["biography"]["next"] is None
    assert len(closed["plan"]["prompts"]) == 7
    await refused(
        deployment,
        "POST",
        f"{base}/papers",
        her,
        409,
        "BiographyClosed",
        json=_paper(LIPID_PANEL, "lab_result"),
    )
    again = await call(deployment, "GET", base, her, 200)
    assert again["step"] == "closed" and again["read_back"] == answered["read_back"]


async def test_a_shoebox_of_30_papers_becomes_the_record_in_one_sitting(
    deployment: Deployment,
) -> None:
    """The acceptance line: thirty papers in one sitting — two the extractor reads, twenty-
    eight it cannot (their cards empty, confirmed as they are) — read back and closed."""
    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    await through_the_papers(deployment, her, profile_id)
    for page in range(28):
        await add_paper(deployment, her, profile_id, f"shoebox-page-{page:02d}", "clinic_card")
    view = await call(deployment, "GET", f"/profiles/{profile_id}/biography", her, 200)
    assert view["step"] == "read_back" and len(view["papers"]) == 30
    assert [line["line"] for line in view["read_back"]] == READ_BACK_MS
    await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/biography/read-back",
        her,
        200,
        json={"answers": answers(view)},
    )
    closed = await call(deployment, "POST", f"/profiles/{profile_id}/biography/close", her, 200)
    assert closed["summary"]["papers"] == 30 and closed["summary"]["facts"] == 13
    assert closed["summary"]["lines"][0] == "Nura simpan 30 surat anda."
    # The clinic cards answered the visits: the plan does not ask for them.
    assert "next_visit" not in {p["prompt"] for p in closed["plan"]["prompts"]}


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
async def test_every_read_back_line_is_served_in_his_language(
    deployment: Deployment, language: str
) -> None:
    """None of the lines is dropped for failing plain words, in any of the three languages."""
    mei, profile_id = await stewarded(deployment)
    view = await through_the_papers(
        deployment, mei["token"], profile_id, settings={**SETTINGS, "language": language}
    )
    assert view["language"] == language
    assert len(view["read_back"]) == len(READ_BACK_MS)
    for line in view["read_back"]:
        assert not [f for f in verify(line["line"], language) if f.severity == "fail"], line
    if language == "en":
        assert view["read_back"][6]["line"] == (
            "Your cholesterol was 230 on Thursday 7 September 2023."
        )
        assert (
            view["read_back"][10]["line"] == "Nura read the label as 1 tablet once a day at night."
        )


async def test_the_papers_can_wait(deployment: Deployment) -> None:
    """No papers: the read-back is what he told, and the close says so and plans for them."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    await call(deployment, "POST", f"/profiles/{profile_id}/biography", his, 201)
    await call(
        deployment,
        "PUT",
        f"/profiles/{profile_id}/settings",
        his,
        200,
        json={"language": "en", "conditions": ["high_blood_pressure"], "doctor_name": "Dr Tan"},
    )
    view = await call(deployment, "GET", f"/profiles/{profile_id}/biography", his, 200)
    assert view["step"] == "papers" and view["next"] == "add_paper"
    assert [line["line"] for line in view["read_back"]] == [
        "You told us: High blood pressure.",
        "Your doctor is Dr Tan.",
    ]
    answered = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/biography/read-back",
        his,
        200,
        json={"answers": answers(view, no=lambda line: "Dr Tan" in line)},
    )
    # He said no himself: his answer is kept beside the paper.
    assert answered["after_no"] == "Nura keeps your answer beside the paper."
    closed = await call(deployment, "POST", f"/profiles/{profile_id}/biography/close", his, 200)
    assert closed["summary"]["lines"][:3] == [
        "No papers were added this time.",
        "You said one line was not right.",
        "Nura keeps your answer beside the paper.",
    ]
    assert closed["plan"]["prompts"][0]["prompt"] == "medicines"


async def test_refusals_are_named_and_on_his_trail(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    kit = await register_by_phone(deployment, KIT, "Kit")
    profile_id = await own_profile(deployment, pa, language="en")
    his, kits = pa["token"], kit["token"]
    await let_in(deployment, pa, profile_id, KIT, ["records", "medicines", "visits"], "son", role="caregiver")
    await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/keys",
        his,
        201,
        json={
            "holder_phone_e164": KIT,
            "role": "caregiver",
            "scopes": ["records", "medicines", "visits"],
        },
    )
    base = f"/profiles/{profile_id}/biography"

    await refused(deployment, "POST", base, kits, 403, "NotTheirsToSetUp")
    await call(deployment, "POST", base, his, 201)
    await refused(deployment, "POST", base, his, 409, "BiographyAlreadyOpen")
    await refused(
        deployment, "POST", f"{base}/read-back", his, 409, "NotAtThisStep", json={"answers": []}
    )
    await refused(deployment, "POST", f"{base}/close", his, 409, "NotAtThisStep")
    await refused(
        deployment,
        "POST",
        f"{base}/papers",
        kits,
        403,
        "NotTheirsToSetUp",
        json=_paper(LIPID_PANEL, "lab_result"),
    )
    # A caregiver reads where it stands; she does not move it.
    seen = await call(deployment, "GET", base, kits, 200)
    assert seen["step"] == "about_you"

    trail = await call(deployment, "GET", f"/profiles/{profile_id}/audit", his, 200)
    refusals = {
        (e["actor_person_id"], e["refused_because"]) for e in trail if e["outcome"] == "refused"
    }
    assert {
        (kit["person_id"], "NotTheirsToSetUp"),
        (pa["person_id"], "BiographyAlreadyOpen"),
        (pa["person_id"], "NotAtThisStep"),
    } <= refusals


def _paper(label: str, kind: str) -> dict[str, Any]:
    from tests.onboarding_support import paper

    return paper(label, kind)


async def _fact(
    deployment: Deployment, profile_id: str, token: str, subject: str, attribute: str
) -> dict[str, Any]:
    facts = await call(
        deployment, "GET", f"/profiles/{profile_id}/facts", token, 200, params={"subject": subject}
    )
    found: dict[str, Any] = next(f for f in facts if f["attribute"] == attribute)
    return found


async def test_a_pdf_paper_and_a_no_on_the_label_line(deployment: Deployment) -> None:
    """A PDF — the hospital letter — goes the way an import does: kept as a PDF artefact and
    read into a review card. A "no" on the warfarin label's line is a dispute that still
    rests on the label photo, so the label rule for a high-risk drug still holds."""
    import base64

    from tests.onboarding_support import confirm_card

    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    await through_the_papers(deployment, her, profile_id)
    added = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/biography/papers",
        her,
        201,
        json={
            "data": base64.b64encode(placeholder_pdf(DISCHARGE_LETTER)).decode(),
            "content_type": "application/pdf",
            "captured_at": "2026-09-03T08:00:00Z",
            "paper": "discharge_letter",
        },
    )
    assert added["paper"]["paper"] == "discharge_letter"
    assert added["card"]["document_kind"] == "discharge_letter" and added["card"]["fields"]
    async with deployment.sessions() as session:
        stored = await session.get(Artifact, uuid.UUID(added["card"]["artifact_id"]))
        assert stored is not None and stored.kind is ArtifactKind.PDF
    await confirm_card(deployment, her, profile_id, added["card"])
    view = await call(deployment, "GET", f"/profiles/{profile_id}/biography", her, 200)
    assert view["step"] == "read_back" and len(view["papers"]) == 3
    dose_line = "Label ini menyebut 1 biji sekali sehari waktu malam."
    answered = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/biography/read-back",
        her,
        200,
        json={"answers": answers(view, no=lambda line: line == dose_line)},
    )
    said = {line["line"]: line for line in answered["read_back"]}
    dose = await _fact(deployment, profile_id, her, "medicine", "dose")
    assert said[dose_line]["answer"] == "no" and said[dose_line]["fact_id"] == dose["fact_id"]
    async with deployment.sessions() as session:
        dispute = await session.get(Fact, uuid.UUID(said[dose_line]["dispute_fact_id"]))
        assert dispute is not None and dispute.confidence_state is ConfidenceState.DISPUTED
        assert (dispute.subject, dispute.attribute) == ("medicine", "dose")
        assert str(dispute.artifact_id) == dose["artifact_id"]
    closed = await call(deployment, "POST", f"/profiles/{profile_id}/biography/close", her, 200)
    assert "discharge_letter" not in {p["prompt"] for p in closed["plan"]["prompts"]}


async def test_questions_are_kept_or_not_and_one_not_kept_stays_out_of_the_week(
    deployment: Deployment,
) -> None:
    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    base = f"/profiles/{profile_id}/biography"
    view = await through_the_papers(deployment, her, profile_id)
    await refused(
        deployment,
        "POST",
        f"{base}/questions",
        her,
        409,
        "NotAtThisStep",
        json={"question_id": "bp_numbers", "keep": True},
    )
    await call(deployment, "POST", f"{base}/read-back", her, 200, json={"answers": answers(view)})
    kept = await call(
        deployment,
        "POST",
        f"{base}/questions",
        her,
        200,
        json={"question_id": "bp_numbers", "keep": True},
    )
    assert {q["question_id"]: q["kept"] for q in kept["questions"]}["bp_numbers"] is True
    # He changes his mind on one, and says "not this one" to another the screen did not show.
    for question_id, keep in (
        ("sugar_result", True),
        ("sugar_result", False),
        ("insurance", False),
    ):
        after = await call(
            deployment,
            "POST",
            f"{base}/questions",
            her,
            200,
            json={"question_id": question_id, "keep": keep},
        )
    shown = {q["question_id"]: q["kept"] for q in after["questions"]}
    assert shown["bp_numbers"] is True and shown["sugar_result"] is False
    await refused(
        deployment,
        "POST",
        f"{base}/questions",
        her,
        404,
        "NoSuchQuestion",
        json={"question_id": "medicines", "keep": True},
    )
    closed = await call(deployment, "POST", f"{base}/close", her, 200)
    planned = [p["prompt"] for p in closed["plan"]["prompts"]]
    assert planned == [
        "bp_numbers",
        "discharge_letter",
        "kidney_result",
        "next_visit",
        "last_visit",
    ]
    assert closed["summary"]["prompts"] == 5


async def test_the_read_back_one_line_at_a_time(deployment: Deployment) -> None:
    """One thing a screen: each line answered on its own; the read-back is done with the last."""
    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    path = f"/profiles/{profile_id}/biography/read-back"
    view = await through_the_papers(deployment, her, profile_id)
    lines = view["read_back"]
    first = await call(
        deployment, "POST", path, her, 200, json={"line_id": lines[0]["fact_id"], "answer": "yes"}
    )
    assert first["step"] == "read_back"
    assert [line["answer"] for line in first["read_back"]] == ["yes"] + [None] * (len(lines) - 1)
    await refused(
        deployment,
        "POST",
        path,
        her,
        404,
        "NoSuchReadBackLine",
        json={"line_id": lines[0]["fact_id"], "answer": "no"},
    )
    await refused(
        deployment,
        "POST",
        path,
        her,
        404,
        "NoSuchReadBackLine",
        json={"line_id": str(uuid.uuid4()), "answer": "yes"},
    )
    bad = await deployment.client.post(
        path, json={"line_id": lines[1]["fact_id"]}, headers={"Authorization": f"Bearer {her}"}
    )
    assert bad.status_code == 422
    last: dict[str, Any] = first
    for line in lines[1:]:
        said = "no" if line["line"] == LDL_MS else "yes"
        last = await call(
            deployment, "POST", path, her, 200, json={"line_id": line["fact_id"], "answer": said}
        )
    assert last["step"] == "questions"
    by_line = {line["line"]: line for line in last["read_back"]}
    assert by_line[LDL_MS]["answer"] == "no" and by_line[LDL_MS]["dispute_fact_id"]
    assert last["after_no"] == "Mei akan lihat surat itu sekali lagi."


async def test_a_card_made_through_capture_joins_the_sitting(deployment: Deployment) -> None:
    """The web's capture screen makes the card; the sitting takes it in by its id, and reads
    back in the language the screen asks for."""
    from tests.onboarding_support import confirm_card

    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    base = f"/profiles/{profile_id}/biography"
    await call(deployment, "POST", base, her, 201)
    await call(deployment, "PUT", f"/profiles/{profile_id}/settings", her, 200, json=SETTINGS)
    photo = _paper(LIPID_PANEL, "lab_result")
    del photo["paper"]
    card = await call(deployment, "POST", f"/profiles/{profile_id}/photos", her, 201, json=photo)
    added = await call(
        deployment, "POST", f"{base}/papers", her, 201, json={"card_id": card["card_id"]}
    )
    assert added["paper"]["paper"] == "lab_result" and added["paper"]["confirmed"] is False
    await refused(
        deployment,
        "POST",
        f"{base}/papers",
        her,
        409,
        "PaperAlreadyAdded",
        json={"card_id": card["card_id"]},
    )
    await confirm_card(deployment, her, profile_id, card, triglycerides=54)
    view = await call(deployment, "GET", base, her, 200)
    assert view["step"] == "read_back" and len(view["read_back"]) == 9
    english = await call(deployment, "GET", base, her, 200, params={"language": "en"})
    assert (
        english["language"] == "en"
        and english["prompt"]["headline"] == "Here is what Nura understood"
    )
    assert "Your cholesterol was 230 on Thursday 7 September 2023." in [
        line["line"] for line in english["read_back"]
    ]


# --- a kept question is a question for the doctor (E05) -------------------------------------

BP_QUESTION_MS = "Adakah anda periksa tekanan darah di rumah?"


async def _book_dr_tan(
    deployment: Deployment, token: str, profile_id: str, when: str = "2026-10-01T02:00:00Z"
) -> str:
    provider = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/providers",
        token,
        201,
        json={"name": "Dr Tan", "kind": "doctor"},
    )
    booking = {"provider_id": provider["provider_id"], "scheduled_at": when, "purpose": "check-up"}
    minted = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/confirmations",
        token,
        201,
        json={"subject": "appointment", **booking},
    )
    visit = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/appointments",
        token,
        201,
        json={**booking, "confirmation_id": minted["confirmation_id"]},
    )
    appointment_id: str = visit["appointment_id"]
    return appointment_id


async def _on_the_list(
    deployment: Deployment, person_id: str, profile_id: str, appointment_id: str
) -> list[str]:
    """The visit's current questions (E05), as the loop reads them."""
    from app.db import unit_of_work
    from app.keys.context import resolve_key_context
    from app.reasoning.visits.questions import current_questions
    from app.regions import Region

    async with deployment.sessions() as session:
        async with unit_of_work(session):
            context = await resolve_key_context(
                session,
                region=Region.SG,
                person_id=uuid.UUID(person_id),
                profile_id=uuid.UUID(profile_id),
            )
            found = await current_questions(
                session, context=context, appointment_id=uuid.UUID(appointment_id)
            )
            texts = [one.text for one in found]
        await session.commit()
    return texts


def _question(view: dict[str, Any], question_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(q for q in view["questions"] if q["question_id"] == question_id)
    return found


async def test_a_question_kept_on_day_0_goes_to_the_visit_booked_later(
    deployment: Deployment,
) -> None:
    """Option (a): with no visit it waits on the sitting; booking Dr Tan puts it on that
    visit's list in the same request, on the booker's yes, and the sitting names the visit."""
    from app.onboarding.models import BiographyQuestion

    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    base = f"/profiles/{profile_id}/biography"
    view = await through_the_papers(deployment, her, profile_id)
    answered = await call(
        deployment, "POST", f"{base}/read-back", her, 200, json={"answers": answers(view)}
    )
    # Every question carries the State it was worked out under and where it came from.
    assert all(q["state_id"] for q in answered["questions"])
    assert _question(answered, "bp_numbers")["source"] == (
        "Ini daripada apa yang anda beritahu Nura pada Khamis 3 September 2026."
    )
    assert _question(answered, "kidney_result")["source"] == (
        "Ini daripada label ubat anda, Selasa 12 Mac 2024."
    )
    kept = await call(
        deployment,
        "POST",
        f"{base}/questions",
        her,
        200,
        json={"question_id": "bp_numbers", "keep": True},
    )
    waiting = _question(kept, "bp_numbers")
    assert waiting["kept"] is True and waiting["handed_over_to"] is None
    async with deployment.sessions() as session:
        row = (
            await session.execute(
                sqlalchemy.select(BiographyQuestion).where(BiographyQuestion.gap == "bp_numbers")
            )
        ).scalar_one()
        assert row.question_id is None and row.handed_over_at is None

    appointment_id = await _book_dr_tan(deployment, her, profile_id)
    after = await call(deployment, "GET", base, her, 200)
    assert _question(after, "bp_numbers")["handed_over_to"] == appointment_id
    assert BP_QUESTION_MS in await _on_the_list(
        deployment, mei["person_id"], profile_id, appointment_id
    )
    # The hand-over is written down: the sitting's question names the visit's question now.
    from sqlalchemy import select

    from app.audit.models import Action, AuditEntry, Outcome

    async with deployment.sessions() as session:
        handed = (
            await session.execute(
                select(BiographyQuestion).where(BiographyQuestion.gap == "bp_numbers")
            )
        ).scalar_one()
        assert handed.question_id is not None and handed.handed_over_at is not None
        lines = (
            (
                await session.execute(
                    select(AuditEntry).where(
                        AuditEntry.target == "biography_question",
                        AuditEntry.target_id == handed.id,
                        AuditEntry.action == Action.WRITE,
                        AuditEntry.outcome == Outcome.ALLOWED,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(lines) >= 2  # kept, then handed over


async def test_with_a_visit_coming_a_kept_question_goes_on_its_list_and_comes_off(
    deployment: Deployment,
) -> None:
    mei, profile_id = await stewarded(deployment)
    her = mei["token"]
    base = f"/profiles/{profile_id}/biography"
    view = await through_the_papers(deployment, her, profile_id)
    appointment_id = await _book_dr_tan(deployment, her, profile_id)
    await call(deployment, "POST", f"{base}/read-back", her, 200, json={"answers": answers(view)})

    async def keep(flag: bool) -> dict[str, Any]:
        said: dict[str, Any] = await call(
            deployment,
            "POST",
            f"{base}/questions",
            her,
            200,
            json={"question_id": "bp_numbers", "keep": flag},
        )
        return _question(said, "bp_numbers")

    assert (await keep(True))["handed_over_to"] == appointment_id
    assert BP_QUESTION_MS in await _on_the_list(
        deployment, mei["person_id"], profile_id, appointment_id
    )
    assert (await keep(False))["handed_over_to"] is None
    assert BP_QUESTION_MS not in await _on_the_list(
        deployment, mei["person_id"], profile_id, appointment_id
    )
    assert (await keep(True))["handed_over_to"] == appointment_id
    assert (await _on_the_list(deployment, mei["person_id"], profile_id, appointment_id)).count(
        BP_QUESTION_MS
    ) == 1
