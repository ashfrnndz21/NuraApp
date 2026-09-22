"""D-2, "whose paper is it" (audit-2026-09-22.md §3.2, §5; docs/design/build-spec.md's
"Owner requirement added 2026-09-22"): the safety half of package 7a.

Before this, `person.birth_year`/`person.sex` off a lab header were written as profile facts
with no comparison against the profile's own record at all (`review.py:_write_paper`, as the
audit found it) — a wrong person's paper could change the age and sex the app reasons with.
The two-part fix: `app.ingestion.whose_paper.check_whose_paper` compares the card's identity
fields against the profile's own, deterministically (rules, not a model), and
`confirm_review_card` refuses outright while a mismatch is unanswered
(`QuestionUnanswered`) — the write-path half this file's API-level tests exercise. The
reading screen's own clarify question is `web/tests/e2e/whoseP­aper.spec.ts`.
"""

from __future__ import annotations

from app.ingestion.whose_paper import names_match
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import confirm, decide, mint, photo
from tests.conftest import Deployment
from tests.paper import LAB_REPORT_NOT_HIS, LIPID_PANEL_2025

PA = "+6591170001"
NOT_HIS_PAPER = LAB_REPORT_NOT_HIS
"""The owner's own example (#302-adjacent, D-2): "Demo Patient Name, 40 Y / M" against a
profile born in the 1950s — built in `tests/fixtures/paper/lab-report-not-his-2026-09-20.json`."""


# --- the pure comparator, no session needed -------------------------------------------------


def test_names_match_is_tolerant_to_case_spacing_and_initials() -> None:
    assert names_match("Mary Lim", "Mary Lim")
    assert names_match("MARY LIM", "mary   lim")
    assert names_match("M Lim", "Mary Lim")
    assert names_match("Mary Lim", "M Lim")
    assert names_match("Lim Mary", "Mary Lim")  # order-independent, still tolerant


def test_names_match_never_tolerates_a_different_surname() -> None:
    assert not names_match("Mary Tan", "Mary Lim")
    assert not names_match("Demo Patient Name", "Pa")


# --- the write door, over HTTP ---------------------------------------------------------------


async def _pa_with_papers_on_file(deployment: Deployment) -> tuple[dict[str, str], str]:
    """Pa, his own profile, and one lab paper already confirmed — the record now holds a
    CONFIRMED `person.birth_year` (1951, the 1950s) for `check_whose_paper` to compare
    against. Nothing here is itself a case this module's check flags: no prior paper on file,
    nothing to mismatch."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL_2025), headers=bearer(pa["token"])
    )
    assert posted.status_code == 201, posted.text
    card = posted.json()
    assert card["clarify"] is None  # nothing on file yet to mismatch against
    done = await confirm(deployment, pa["token"], profile_id, card, decide(card))
    assert done.status_code == 200, done.text
    return pa, profile_id


async def test_a_demo_lab_sheet_against_a_profile_born_in_the_1950s_asks(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])

    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    assert posted.status_code == 201, posted.text
    card = posted.json()
    assert card["clarify"] is not None
    clarify = card["clarify"]
    assert clarify["kind"] == "whose_paper"
    assert set(clarify["mismatched"]) == {"name", "birth_year"}
    # FIX BEFORE MERGE, the independent safety review: the paper's own printed name (and, in
    # the same spirit, its year of birth) never reaches the wire at all -- only the closed
    # field-name enum above. Extracted text is hostile until confirmed; a page printing an
    # instruction in its name field must never become a sentence Nura composes.
    assert "paper_name" not in clarify
    assert "paper_birth_year" not in clarify
    assert "paper_sex" not in clarify
    # The extracted field itself (`card["fields"]`) still shows "Demo Patient Name" for him
    # to look at and confirm or reject -- that is the review card's ordinary job. Only the
    # *clarify* question -- the sentence Nura composes about a still-unconfirmed paper -- must
    # never quote it.
    assert "Demo Patient Name" not in str(clarify)

    # D-2's core rule: nothing is filed until the question is answered — not even a mint of
    # the confirmation succeeds in a way that could be spent, because the card itself refuses
    # first. Proven directly: the write door refuses even with every field confirmed.
    decisions = decide(card)
    minted = await mint(deployment, pa["token"], profile_id, card, decisions)
    assert minted.status_code == 201, minted.text  # minting a yes is not itself a write
    written = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert written.status_code == 400 and written.json() == {"refusal": "QuestionUnanswered"}

    # Nothing was written: no new person.birth_year, no lipid_panel line from this card.
    facts = await deployment.client.get(f"/profiles/{profile_id}/facts?subject=person", headers=his)
    assert facts.status_code == 200
    birth_years = [f["value"] for f in facts.json() if f["attribute"] == "birth_year"]
    assert birth_years == [1951]  # only the first paper's, never overwritten


async def test_someone_elses_keeps_the_paper_out_of_the_record_with_a_calm_line(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    card = posted.json()

    answered = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/answer",
        json={"value": "someone_elses"},
        headers=his,
    )
    assert answered.status_code == 200, answered.text
    out = answered.json()
    assert out["discarded"] is True and out["clarify"] is None

    # Set aside for good: not even a yes can be minted for it any more.
    decisions = decide(card)
    minted = await mint(deployment, pa["token"], profile_id, card, decisions)
    assert minted.status_code == 409 and minted.json() == {"refusal": "CardSetAside"}

    facts = await deployment.client.get(f"/profiles/{profile_id}/facts?subject=person", headers=his)
    birth_years = [f["value"] for f in facts.json() if f["attribute"] == "birth_year"]
    assert birth_years == [1951]  # the wrong paper never touched it


async def test_the_answer_is_on_the_trail_as_a_closed_code_never_the_papers_name(
    deployment: Deployment,
) -> None:
    """FIX BEFORE MERGE, the independent safety review: before this, `answer_review_card_
    question` wrote no audit line on success at all -- `@audited` only writes one on a
    refusal. The decision this whole package exists to make safe now has its own line, and
    it carries `answered_with` from the closed set the door already checked the value
    against ("someone_elses" here) -- never "Demo Patient Name", the paper's own printed
    text, anywhere on the trail."""
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    card = posted.json()

    answered = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/answer",
        json={"value": "someone_elses"},
        headers=his,
    )
    assert answered.status_code == 200, answered.text

    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    assert trail.status_code == 200, trail.text
    on_this_card = [e for e in trail.json() if e["target"] == "review_card" and e["target_id"] == card["card_id"]]
    answers = [e for e in on_this_card if e["answered_with"] is not None]
    assert len(answers) == 1
    assert answers[0]["answered_with"] == "someone_elses"
    assert "Demo Patient Name" not in str(trail.json())


async def test_not_sure_keeps_the_card_open(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    card = posted.json()

    # "I'm not sure" is never sent to the backend at all (`review.WHOSE_PAPER_ANSWERS`) — the
    # card is simply left exactly as it was, still pending, still open, on the list.
    reread = await deployment.client.get(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}", headers=his
    )
    assert reread.status_code == 200
    assert reread.json()["clarify"]["kind"] == "whose_paper"
    assert reread.json()["confirmed_at"] is None and reread.json()["discarded"] is False

    cards = await deployment.client.get(
        f"/profiles/{profile_id}/review-cards", params={"open": "true"}, headers=his
    )
    assert card["card_id"] in {c["card_id"] for c in cards.json()}


async def test_mine_lets_it_file_normally(deployment: Deployment) -> None:
    """Not every mismatch is real: answering "mine" is itself a decision a person may make
    (a paper printed under an old name, say), and once he has, the card confirms exactly like
    any other — the identity fields included."""
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    card = posted.json()

    answered = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/answer",
        json={"value": "mine"},
        headers=his,
    )
    assert answered.status_code == 200
    assert answered.json()["clarify"] is None and answered.json()["discarded"] is False

    decisions = decide(card)
    done = await confirm(deployment, pa["token"], profile_id, card, decisions)
    assert done.status_code == 200, done.text


async def test_a_second_answer_is_refused(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    card = posted.json()
    first = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/answer",
        json={"value": "someone_elses"},
        headers=his,
    )
    assert first.status_code == 200
    second = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/answer",
        json={"value": "mine"},
        headers=his,
    )
    assert second.status_code == 409 and second.json() == {"refusal": "QuestionAlreadyAnswered"}


async def test_an_unlisted_value_is_refused(deployment: Deployment) -> None:
    pa, profile_id = await _pa_with_papers_on_file(deployment)
    his = bearer(pa["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(NOT_HIS_PAPER), headers=his
    )
    card = posted.json()
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/answer",
        json={"value": "not_sure"},  # never a real answer — the chip never calls this door
        headers=his,
    )
    assert refused.status_code == 400 and refused.json() == {"refusal": "NotAnAnswer"}
