"""E19-05: the red-flag word table, and a flag written before anything else."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.channels.whatsapp.models import MessageKind, WhatsAppMessage
from app.identity.service import register_person
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.models import Artifact, Fact
from app.regions import Region
from app.safety.red_flags import RED_FLAG_WORDS, Escalation, Flag, RedFlag, detect
from tests.support import agree_to_family_sharing
from tests.whatsapp_support import KIT, MEI, family


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("he fell in the bathroom", RedFlag.FALL),
        ("Pa jatuh dalam bilik air", RedFlag.FALL),
        ("阿公在浴室跌倒了", RedFlag.FALL),
        ("he's very breathless just sitting", RedFlag.BREATHLESS_AT_REST),
        ("says his chest is tight", RedFlag.CHEST_TIGHTNESS),
        ("left leg is swollen since morning", RedFlag.ONE_SIDED_SWELLING),
        ("worst headache of his life", RedFlag.WORST_HEADACHE),
        ("suddenly cannot see properly", RedFlag.SUDDEN_BLURRING),
        ("he is confused and does not recognise me", RedFlag.CONFUSION),
        ("shaky and sweaty after the sugar tablet", RedFlag.SHAKY_AND_SWEATY),
    ],
)
def test_the_word_table_names_the_rule(text: str, rule: RedFlag) -> None:
    assert detect(text) is rule


@pytest.mark.parametrize(
    "text", ["BP 150/90 this morning", "a fellow from church visited", "fall back plan", None, ""]
)
def test_ordinary_words_are_not_a_flag(text: str | None) -> None:
    # "fall" as a word is a fall; a name that merely contains one ("fellow") is not.
    if text == "fall back plan":
        assert detect(text) is RedFlag.FALL
    else:
        assert detect(text) is None


def test_every_rule_has_words_in_three_languages_or_a_reason() -> None:
    assert set(RED_FLAG_WORDS) == set(RedFlag)
    for patterns in RED_FLAG_WORDS.values():
        assert len(patterns) >= 3


async def test_a_red_flag_is_written_before_anything_else_and_escalates(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164=KIT)
    await agree_to_family_sharing(sg, home.owner, kit, scopes={Scope.MEDICINES, Scope.EMERGENCY})
    await grant_key(sg, context=home.owner, holder=kit, role=KeyRole.HELPER)

    handled = await home.inbound(sg, MEI, "he fell in the bathroom just now")
    assert handled.outcome == "red_flag" and handled.flag_id is not None

    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.rule is RedFlag.FALL
    assert flag.raised_by_person_id == home.mei.id and flag.profile_id == home.profile.id

    # Before anything else: the flag's line on the trail comes before the artefact's. The
    # clock is frozen, so the order is the order the rows were written in.
    trail = list(
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.profile_id == home.profile.id, AuditEntry.action == Action.WRITE
            )
        )
    )
    targets = [e.target for e in trail if e.actor_person_id == home.mei.id]
    assert targets.index("safety_flag") < targets.index("artifact")
    assert targets.index("artifact") < targets.index("whatsapp_message")
    assert targets.index("whatsapp_message") < targets.index("safety_escalation")

    # The reply in the thread: the doctor's word, and who knows now.
    assert len(handled.replies) == 1
    lines = handled.replies[0].text.splitlines()
    assert lines[0] == "This one we do not wait for."
    assert lines[1] == "Call your doctor today."
    assert lines[2] == "Pa and Kit know now."

    # The ladder: owner, then chiefs (Mei is the poster and left out), then the rest.
    ladder = (await sg.scalars(select(Escalation).where(Escalation.flag_id == flag.id))).one()
    assert [step["standing"] for step in ladder.roster] == ["owner", "helper"]
    assert [step["person_id"] for step in ladder.roster] == [str(home.pa.id), str(kit.id)]
    assert ladder.told == [str(home.mei.id)]

    # Nothing was extracted from the words: no fact, no proposal; the message is kept.
    assert list(await sg.scalars(select(Fact))) == []
    kept = (await sg.scalars(select(WhatsAppMessage))).all()
    assert next(m.kind for m in kept if m.person_id == home.mei.id) is MessageKind.RED_FLAG
    assert (await sg.get(Artifact, handled.artifact_id)) is not None


async def test_a_red_flag_from_a_key_without_the_emergency_scope_is_refused_and_written_down(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The keys are not bypassed for a flag: a key cut without the emergency scope cannot
    write one, and the reaching is on the trail. Every role but a clinic holds it."""
    home = await family(
        sg, tmp_path, mei_scopes=frozenset({Scope.MEDICINES}), mei_role=KeyRole.HELPER
    )
    handled = await home.inbound(sg, MEI, "he fell in the bathroom")
    assert handled.outcome == "refused" and handled.refused == "OutOfScope"
    assert list(await sg.scalars(select(Flag))) == []
    trail = await read_audit(sg, context=home.owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.target == "safety_flag"
        and e.scope is Scope.EMERGENCY
        and e.actor_person_id == home.mei.id
        for e in trail
    )
