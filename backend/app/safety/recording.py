"""The recording consent pattern: what the app says before it listens, and the gate (E16-02).

    Consult recording: doctor notified aloud or by printed notice; consent stored with the
    recording; reviewed by counsel in both countries. (docs/build-plan.md §5)

The pattern is written up in docs/trust/recording-consent.md. What lives here is the part the
code enforces: `recording_notice` is the words the app speaks in the room before a recording
starts, in the patient's language, and `PRINTED_NOTICE` the card for the clinic desk that says
the same; `may_record` is the gate every recording surface asks before the microphone opens —
the RECORDING consent in force under the visits scope, and the records scope held, since that
is where the bytes go; `CHECKLIST` is the order of the steps the surface owes, named so the
document and the code can be checked against each other.

The gate is not the only mechanism. Where the bytes enter, `app.memory.episodic.store_artifact`
makes every writer of a voice declare whose voices it carries (`Recording`) and requires the
same consent, under the same visits scope, for every `Recording.CONSULT`, whichever surface
wrote it, so a recording of a visit with no consent in force cannot be kept even by a writer
that never asked here. A person's own voice note — his about himself, or a caregiver's on his
event — is `Recording.OWN_NOTE`: his words, or hers, kept like typed text on the consent to
hold the record, and not gated here (ADR 0003). Both refusals are on the trail like every
other. The doctor's spoken yes, when it is given, is the first seconds of the artefact.

The notice speaks to the doctor by name; when the record has not named one, the last line is
addressed plainly — "Is that OK, doctor?" — never "your doctor", which is not a form of
address. The other lines say "your doctor" as usual.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Channel, Outcome
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import ConsentCheck, require_consent
from app.keys.context import KeyContext, OutOfScope
from app.keys.scopes import Scope
from app.memory.models import Artifact
from app.safety.boundary import YOUR_DOCTOR, language_of

# @patient
SPOKEN_NOTICE: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Nura will listen now.",
        "Nura keeps what you and {doctor} say.",
        "Only you and the family you let in can hear it.",
        "Is that OK, {doctor}?",
    ),
    "ms": (
        "Nura akan mendengar sekarang.",
        "Nura menyimpan apa yang anda dan {doctor} kata.",
        "Hanya anda dan keluarga yang anda benarkan boleh mendengarnya.",
        "Boleh, {doctor}?",
    ),
    "zh": (
        "Nura 现在开始听。",
        "Nura 会保存您和{doctor}说的话。",
        "只有您和您让进来的家人可以听。",
        "{doctor}，可以吗？",
    ),
}
"""What the app says aloud in the room, before the recording starts, in the patient's language.
The last line is to the doctor, by name; the doctor's answer is the first seconds kept.
"The family you let in" is the consent's own phrase (`app.consent.texts`), word for word, and
it is the rule: a visit's recording is heard by him and the family he let in — his chief and
his caregivers — and the artefact door refuses anyone else (`episodic.OnlyTheFamilyHears`)."""

# @patient
VOCATIVE_LINE: Mapping[str, str] = {
    "en": "Is that OK, doctor?",
    "ms": "Boleh ya, doktor?",
    "zh": "医生，可以吗？",
}
"""The last line of the notice when no doctor is named: addressed plainly, never "your doctor"."""

# @patient
PRINTED_NOTICE: Mapping[str, tuple[str, ...]] = {
    "en": (
        "This patient uses Nura.",
        "Nura listens to what you and the patient say.",
        "Nura keeps it for the patient to hear again.",
        "Only the patient can hear it.",
        "The patient can let his family hear it too.",
        "You can say no.",
        "Then Nura does not listen.",
    ),
    "ms": (
        "Pesakit ini menggunakan Nura.",
        "Nura mendengar apa yang anda dan pesakit kata.",
        "Nura menyimpannya untuk pesakit dengar semula.",
        "Hanya pesakit boleh mendengarnya.",
        "Pesakit boleh benarkan keluarganya mendengar juga.",
        "Anda boleh kata tidak.",
        "Nura tidak akan mendengar.",
    ),
    "zh": (
        "这位病人使用 Nura。",
        "Nura 会听您和病人说的话。",
        "Nura 会保存下来，让病人再听。",
        "只有病人可以听。",
        "病人也可以让家人听。",
        "您可以说不。",
        "Nura 就不会听。",
    ),
}
"""The card for the clinic desk, printed from the app: the same notice, for a doctor who
would rather read it. Read at a busy desk in three seconds: one idea per line, no ellipsis."""

# @patient
WHEN_NO: Mapping[str, tuple[str, ...]] = {
    "en": ("Nura will not listen today.", "{who} will write the notes by hand."),
    "ms": ("Nura tidak akan mendengar hari ini.", "{who} akan menulis nota dengan tangan."),
    "zh": ("Nura 今天不会听。", "{who} 会用手写下笔记。"),
}
"""What the patient is told when the doctor, or he, says no: nothing is kept, and who writes.
Not "Nura does not keep this visit": to keep a visit is to attend it."""

CHECKLIST: tuple[str, ...] = (
    "recording_consent_in_force",
    "records_scope_held",
    "doctor_named_or_addressed_plainly",
    "notice_spoken_or_printed",
    "answer_kept_as_first_seconds",
    "stop_is_one_tap",
    "no_means_nothing_kept",
)
"""The steps the recording surface owes, in order, as docs/trust/recording-consent.md names
them. `may_record` is the first two; `store_artifact` holds the first again where the bytes
land; the surface (E02-05) is held to the rest by its own tests."""


def recording_notice(language: str | None = None, *, doctor: str | None = None) -> str:
    """The spoken notice, one line per idea. With a named doctor every line names him; with
    none, the lines say "your doctor" and the last addresses the doctor plainly."""
    code = language_of(language)
    lines = SPOKEN_NOTICE[code]
    if doctor is None:
        return "\n".join(
            [*(line.format(doctor=YOUR_DOCTOR[code]) for line in lines[:-1]), VOCATIVE_LINE[code]]
        )
    return "\n".join(line.format(doctor=doctor) for line in lines)


def printed_notice(language: str | None = None) -> str:
    """The card for the desk, in the patient's language."""
    return "\n".join(PRINTED_NOTICE[language_of(language)])


def when_no(language: str | None = None, *, who: str) -> str:
    """What he is told on a no: nothing kept, and `who` writes the notes by hand."""
    return "\n".join(line.format(who=who) for line in WHEN_NO[language_of(language)])


async def may_record(
    session: AsyncSession, context: KeyContext, *, channel: Channel = Channel.APP
) -> ConsentCheck:
    """The gate: the RECORDING consent in force on this profile right now, and the reach to
    keep the recording, or a refusal.

    The consent is asked under the visits scope, since a recording is a visit's; the person
    asking must hold it, and the refusal — withheld, withdrawn, or given to older words — is
    written into the trail on `channel` by `require_consent`. Then the records scope, where
    the artefact is kept through (`store_artifact`'s door; a consult is then written under the
    visits scope, ADR 0004): a viewer key holds
    visits and not records, and a room told "Nura will listen now" must not then find that
    nothing was kept. That refusal is on the trail too, as a refused write of an artefact.
    The surface calls this before it opens the microphone; the store asks the consent again
    when the bytes land.
    """
    check = await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.RECORDING,
        scope=Scope.VISITS,
        channel=channel,
    )
    try:
        context.require(Scope.RECORDS)
    except OutOfScope as refusal:
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=Artifact.__tablename__,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
            channel=channel,
        )
        raise
    return check
