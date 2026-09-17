"""About him, to someone else (D1): on a key that is not his, the lines his chief's Home reads
are said about him by name — the catalogues' twins, in English, Malay and Chinese — and on his
own key nothing changes."""

from __future__ import annotations

import re
from collections.abc import Iterable

import pytest

from app.channels.about_him import LANGUAGES, TO_HIM, Reader, twins
from app.consent.texts import CONSENT_THEIRS, TEXTS, ConsentText
from app.safety.boundary import BOUNDARY_THEIRS, Surface, boundary_line
from tests.api import CONSENT, bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6598760451"
MEI = "+6598760452"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_twin_speaks_to_him_and_every_twin_names_only_its_own_slots(language: str) -> None:
    written = [(original, twin) for original, twin in twins(language) if original != twin]
    assert written, "the twins are written"
    for original, twin in written:
        assert not TO_HIM[language].search(twin), (language, twin)
        slots = set(re.findall(r"\{(\w+)\}", twin)) - {"patient"}
        assert slots <= set(re.findall(r"\{(\w+)\}", original)), (original, twin)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_boundary_twins_are_the_boundary_as_it_is_said(language: str) -> None:
    said = boundary_line(Surface.STATE_POSTURE, language).split("\n")
    for original, _twin in BOUNDARY_THEIRS[language].values():
        assert original in said


@pytest.mark.parametrize(
    ("language", "line", "about_him"),
    [
        (
            "en",
            "Your blood pressure today was 138 over 84.",
            "Pa's blood pressure today was 138 over 84.",
        ),
        (
            "en",
            "Take 1 tablet of your blood pressure tablet with breakfast.",
            "Pa takes 1 tablet of Pa's blood pressure tablet with breakfast.",
        ),
        ("en", "Nothing needs you today.", "Nothing needs doing for Pa today."),
        ("en", "Taken", "Pa took it"),
        ("en", "your blood pressure tablet", "Pa's blood pressure tablet"),
        (
            "en",
            "Nura put your day in order.\nThis is not a doctor's advice.\nAsk your doctor.",
            "Nura put Pa's day in order.\nThis is not a doctor's advice.\nAsk Pa's doctor.",
        ),
        (
            "ms",
            "Tekanan darah anda hari ini 138 atas 84.",
            "Tekanan darah Pa hari ini 138 atas 84.",
        ),
        ("zh", "您今天的血压是138比84。", "Pa今天的血压是138比84。"),
    ],
)
def test_a_line_to_him_is_said_about_him_by_name(language: str, line: str, about_him: str) -> None:
    assert Reader(his=False, name="Pa", language=language).says(line) == about_him
    assert Reader(his=True).says(line) == line


def test_a_line_with_no_twin_is_left_and_a_card_of_his_with_one_is_not_shown() -> None:
    reader = Reader(his=False, name="Pa", language="en")
    assert reader.says("Your own free words to him") == "Your own free words to him"
    assert reader.speaks_to_him(["Pa's day", ["Your own free words"]])
    assert not reader.speaks_to_him(["Pa's blood pressure today"])


async def test_his_state_to_him_and_about_him_to_his_daughter(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    scopes = ["medicines", "records", "family"]
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter", role="caregiver")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": scopes},
        headers=his,
    )
    assert granted.status_code == 201, granted.text

    to_him = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert to_him.status_code == 200, to_him.text
    about = await deployment.client.get(
        f"/profiles/{profile_id}/state", headers=bearer(mei["token"])
    )
    assert about.status_code == 200, about.text
    assert to_him.json()["boundary"].startswith("Nura put your day in order.")
    assert about.json()["boundary"].startswith("Nura put Pa's day in order.")
    assert about.json()["boundary"].endswith("Ask Pa's doctor.")
    if to_him.json()["line"]:
        assert not TO_HIM["en"].search(about.json()["line"])


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_consent_twins_are_the_consent_wording_as_it_is_said(language: str) -> None:
    """`CONSENT_THEIRS` quotes the wordings verbatim, the way `BOUNDARY_THEIRS` quotes the
    boundary: a change to a wording that leaves its twin behind is caught here."""
    said = [text.summary for text in TEXTS if text.language == language]
    for original, _twin in CONSENT_THEIRS[language].values():
        assert any(original in summary for summary in said), (language, original)


def _lines_still_speaking_to_him(texts: Iterable[ConsentText], language: str) -> list[str]:
    """Every line, from every entry in `texts`, that still speaks to him after the reader has
    said it about someone reading a key that is not his. This walks the wordings themselves —
    not a hand-picked list of the purposes and versions `CONSENT_THEIRS` happens to name — so
    a purpose or version with no twin is found here, whether it exists today or is added
    later (the shape of #186 and #215: a list a future member could silently fall outside)."""
    reader = Reader(his=False, name="Pa", language=language)
    missing: list[str] = []
    for text in texts:
        if text.language != language:
            continue
        for line in text.summary.split("\n"):
            said = reader.says(line)
            if TO_HIM[language].search(said):
                missing.append(f"{text.purpose}/{text.version}: {line!r} -> {said!r}")
    return missing


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_consent_wording_ever_shown_is_said_about_him_by_name(language: str) -> None:
    """`GET /consents` answers every agreement ever given, whatever its purpose and whatever
    version it was made under, so every one of them — not just the ones a fixture happens to
    seed — must be safe for a chief to read about him by name. This enumerates `TEXTS` itself,
    so a wording added to it later without a `CONSENT_THEIRS` entry fails here, not on a
    caregiver's screen."""
    checked = [text for text in TEXTS if text.language == language]
    assert checked, f"no wordings recorded for {language!r}"
    assert _lines_still_speaking_to_him(TEXTS, language) == []


def test_the_completeness_check_is_not_vacuous() -> None:
    """Proof the check above actually catches an uncovered wording, not just that today's
    wordings happen to pass: a synthetic version with a "your" line and no twin is flagged."""
    from dataclasses import replace

    fixture = (
        *TEXTS,
        replace(TEXTS[0], version="test-only-no-twin", summary="Nura will remember your favourite colour."),
    )
    missing = _lines_still_speaking_to_him(fixture, "en")
    assert any("favourite colour" in line for line in missing), missing
    # And the real TEXTS alone, unpolluted by the fixture, still passes — the check itself
    # is not what is broken.
    assert _lines_still_speaking_to_him(TEXTS, "en") == []


@pytest.mark.parametrize(
    ("language", "line", "about_him"),
    [
        (
            "en",
            "Mei is the person who runs your care.",
            "Mei is the person who runs Pa's care.",
        ),
        ("en", "- your medicines", "- Pa's medicines"),
        (
            "en",
            "Mei can see them until you say stop.",
            "Mei can see them until Pa says stop.",
        ),
        (
            "en",
            "You are letting Mei, your daughter, see some of your record.",
            "Pa is letting Mei, Pa's daughter, see some of Pa's record.",
        ),
        ("en", "You can stop this at any time.", "Pa can stop this at any time."),
        (
            "en",
            "Nura keeps your papers, your medicines and your blood pressure book.",
            "Nura keeps Pa's papers, Pa's medicines and Pa's blood pressure book.",
        ),
        (
            "en",
            "You can tell Nura to stop at any time.",
            "Pa can tell Nura to stop at any time.",
        ),
        (
            "en",
            "The papers Nura already has stay in your record.",
            "The papers Nura already has stay in Pa's record.",
        ),
        (
            "ms",
            "Mei ialah orang yang mengurus penjagaan anda.",
            "Mei ialah orang yang mengurus penjagaan Pa.",
        ),
        ("ms", "- ubat anda", "- ubat Pa"),
        ("zh", "Mei是照顾您的主要家人。", "Mei是照顾Pa的主要家人。"),
        ("zh", "- 您的药", "- Pa的药"),
    ],
)
def test_the_family_and_consent_lines_are_said_about_him_by_name(
    language: str, line: str, about_him: str
) -> None:
    """The two paths #210 fixed (the family's grant lines) and the one #214 fixed (the
    consent wording) go through the same reader as everything else, and are said about him
    by name on a key that is not his — never left in his voice."""
    assert Reader(his=False, name="Pa", language=language).says(line) == about_him
    assert Reader(his=True).says(line) == line


async def test_grants_and_consents_are_said_about_him_by_name_on_a_key_that_is_not_his(
    deployment: Deployment,
) -> None:
    """#210: the family's grant lines (`GET /grants`). #214: the consent wording (`GET
    /consents`) — his own account-opening agreement and the one that let her in, both quoted
    verbatim on his own key and about him by name on hers."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    scopes = ["medicines", "records", "family"]
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter", role="chief")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "chief", "scopes": scopes},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    hers = bearer(mei["token"])

    his_grants = await deployment.client.get(f"/profiles/{profile_id}/grants", headers=his)
    assert his_grants.status_code == 200, his_grants.text
    her_grants = await deployment.client.get(f"/profiles/{profile_id}/grants", headers=hers)
    assert her_grants.status_code == 200, her_grants.text
    her_lines = [line for grant in her_grants.json() for line in grant["lines"]]
    assert her_lines, "the grants have lines to check"
    for line in her_lines:
        assert not TO_HIM["en"].search(line), line
    assert any("Mei is the person who runs Pa's care." in line for line in her_lines) or any(
        "the person who runs Pa's care" in line for line in her_lines
    )
    his_lines = [line for grant in his_grants.json() for line in grant["lines"]]
    assert any(TO_HIM["en"].search(line) for line in his_lines), "his own key stays in his voice"

    his_consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    assert his_consents.status_code == 200, his_consents.text
    her_consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=hers)
    assert her_consents.status_code == 200, her_consents.text
    assert len(her_consents.json()) >= 2, "his own agreement and the one that let her in"
    for consent in her_consents.json():
        for consent_line in consent["wording_text"].split("\n"):
            assert not TO_HIM["en"].search(consent_line), consent_line
    assert any(
        TO_HIM["en"].search(consent_line)
        for consent in his_consents.json()
        for consent_line in consent["wording_text"].split("\n")
    ), "his own key still reads his own words"


async def test_consent_voice_follows_the_actor_not_the_reader(deployment: Deployment) -> None:
    """#214, "whose act was it": the voice of a consent's shown wording follows who gave it
    (`Consent.person_id`), never who is reading it. Mei records `HOLD_HEALTH_RECORD` for Pa
    under a lasting power of attorney before he claims the graph: her act stays hers, read on
    either key, and his own act — once he claims and agrees for himself — stays his."""
    mei = await register_by_phone(deployment, MEI, "Mei")
    hers = bearer(mei["token"])
    evidence = {
        "kind": "pdf",
        "storage_key": "sg/lpa/pa.pdf",
        "content_type": "application/pdf",
        "sha256": "a" * 64,
        "captured_at": "2026-09-01T00:00:00+00:00",
    }
    opened = await deployment.client.post(
        "/profiles/for-someone",
        json={
            "patient_phone_e164": PA,
            "display_name": "Pa",
            "language": "en",
            "consent": CONSENT,
            "basis": "lpa",
            "relationship": "daughter",
            "evidence": evidence,
        },
        headers=hers,
    )
    assert opened.status_code == 201, opened.text
    profile_id = opened.json()["profile_id"]

    # Mei reads her own act, on her own key: the words stand exactly as she read them.
    her_consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=hers)
    assert her_consents.status_code == 200, her_consents.text
    [her_view] = her_consents.json()
    assert her_view["person_id"] == mei["person_id"]
    assert TO_HIM["en"].search(her_view["wording_text"]), "her own act stays in her own words"

    # Pa registers, finds the graph waiting, and claims it.
    pa = await register_by_phone(deployment, PA, "Pa")
    his = bearer(pa["token"])
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "claim", "language": "en"},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    claimed = await deployment.client.post(
        f"/profiles/{profile_id}/claim",
        json={"confirmation_id": minted.json()["confirmation_id"], "language": "en"},
        headers=his,
    )
    assert claimed.status_code == 200, claimed.text

    his_consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    assert his_consents.status_code == 200, his_consents.text
    rows = his_consents.json()

    # Pa reads Mei's act, on his own key: it was hers, said about her by name — never left
    # to read as if he had agreed to it himself (the harm #214 reported).
    [her_act] = [c for c in rows if c["basis"] == "lpa"]
    assert her_act["person_id"] == mei["person_id"]
    assert not TO_HIM["en"].search(her_act["wording_text"]), her_act["wording_text"]
    assert "Mei" in her_act["wording_text"]

    # His own act, once he claims and agrees for himself: unchanged, on his own key.
    [his_own] = [
        c for c in rows if c["purpose"] == "hold_health_record" and c["basis"] == "owner"
    ]
    assert his_own["person_id"] == pa["person_id"]
    assert TO_HIM["en"].search(his_own["wording_text"])

    # The audit trail already names the actor: assert it directly, not just the wording.
    trail = await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)
    assert trail.status_code == 200, trail.text
    write = next(
        e
        for e in trail.json()
        if e["target"] == "consent" and e["target_id"] == her_act["consent_id"]
    )
    assert write["actor_person_id"] == mei["person_id"]
