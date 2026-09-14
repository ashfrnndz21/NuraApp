"""The recording consent pattern: what the app says before it listens, and the gate (E16-02).

    Consult recording: doctor notified aloud or by printed notice; consent stored with the
    recording; reviewed by counsel in both countries. (docs/build-plan.md §5)

The pattern is written up in docs/trust/recording-consent.md. What lives here is the part the
code enforces: `recording_notice` is the words the app speaks in the room before a recording
starts, in the patient's language, and `PRINTED_NOTICE` the card for the clinic desk that says
the same; `may_record` is the gate every recording surface asks before the microphone opens,
and it is `app.consent.service.require_consent` for `RECORDING` under the visits scope, so a
recording with no consent in force is refused and the refusal is on the trail like every
other. `CHECKLIST` is the order of the steps the surface owes, named so the document and the
code can be checked against each other.

Nothing here opens a microphone or stores bytes: the recording surface (E02-05, E05) does
that, through `app.memory.episodic.store_artifact` as a VOICE artefact, after this gate says
yes. The doctor's spoken yes, when it is given, is the first seconds of that artefact.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Channel
from app.consent.models import ConsentPurpose
from app.consent.service import ConsentCheck, require_consent
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.safety.boundary import YOUR_DOCTOR, language_of

# @patient
SPOKEN_NOTICE: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Nura is about to listen and keep what is said.",
        "Only you and the family you choose can hear it.",
        "Is that OK, {doctor}?",
    ),
    "ms": (
        "Nura akan mendengar dan menyimpan apa yang dikatakan.",
        "Hanya anda dan keluarga yang anda pilih boleh mendengarnya.",
        "Boleh, {doctor}?",
    ),
    "zh": (
        "Nura 现在要听，并保存说过的话。",
        "只有您和您选的家人可以听。",
        "{doctor}，可以吗？",
    ),
}
"""What the app says aloud in the room, before the recording starts, in the patient's language.
The last line is to the doctor, by name; the doctor's answer is the first seconds kept."""

# @patient
PRINTED_NOTICE: Mapping[str, tuple[str, ...]] = {
    "en": (
        "This patient uses Nura.",
        "Nura listens to this visit and keeps what is said.",
        "Only the patient and the family they choose can hear it.",
        "Please say if you would rather it did not.",
    ),
    "ms": (
        "Pesakit ini menggunakan Nura.",
        "Nura mendengar lawatan ini dan menyimpan apa yang dikatakan.",
        "Hanya pesakit dan keluarga yang dipilihnya boleh mendengarnya.",
        "Sila beritahu jika anda tidak mahu.",
    ),
    "zh": (
        "这位病人使用 Nura。",
        "Nura 会听这次看诊，并保存说过的话。",
        "只有病人和他选的家人可以听。",
        "如果您不希望这样，请告诉我们。",
    ),
}
"""The card for the clinic desk, printed from the app: the same notice, for a doctor who
would rather read it. The words the patient holds are his; these are read by the clinic."""

# @patient
WHEN_NO: Mapping[str, tuple[str, ...]] = {
    "en": ("Nura does not keep this visit.", "{who} will write the notes by hand."),
    "ms": ("Nura tidak menyimpan lawatan ini.", "{who} akan menulis nota dengan tangan."),
    "zh": ("Nura 不保存这次看诊。", "{who} 会用手写下笔记。"),
}
"""What the patient is told when the doctor, or he, says no: nothing is kept, and who writes."""

CHECKLIST: tuple[str, ...] = (
    "recording_consent_in_force",
    "doctor_named_or_your_doctor",
    "notice_spoken_or_printed",
    "answer_kept_as_first_seconds",
    "stop_is_one_tap",
    "no_means_nothing_kept",
)
"""The steps the recording surface owes, in order, as docs/trust/recording-consent.md names
them. `may_record` is the first; the surface (E02-05) is held to the rest by its own tests."""


def recording_notice(language: str | None = None, *, doctor: str | None = None) -> str:
    """The spoken notice, one line per idea, naming the doctor when the record has one."""
    code = language_of(language)
    who = doctor or YOUR_DOCTOR[code]
    return "\n".join(line.format(doctor=who) for line in SPOKEN_NOTICE[code])


def printed_notice(language: str | None = None) -> str:
    """The card for the desk, in the patient's language."""
    return "\n".join(PRINTED_NOTICE[language_of(language)])


def when_no(language: str | None = None, *, who: str) -> str:
    """What he is told on a no: nothing kept, and `who` writes the notes by hand."""
    return "\n".join(line.format(who=who) for line in WHEN_NO[language_of(language)])


async def may_record(
    session: AsyncSession, context: KeyContext, *, channel: Channel = Channel.APP
) -> ConsentCheck:
    """The gate: the RECORDING consent in force on this profile right now, or a refusal.

    Asked under the visits scope, since a recording is a visit's; the person asking must
    hold it, and the refusal — withheld, withdrawn, or given to older words — is written
    into the trail on `channel` by `require_consent`. There is no path to a recording that
    does not pass here first: the surface calls this before it opens the microphone.
    """
    return await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.RECORDING,
        scope=Scope.VISITS,
        channel=channel,
    )
