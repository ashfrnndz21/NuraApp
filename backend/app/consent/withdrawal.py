"""Stopping one agreement, as the owner reads it before and after (E00-02).

`app.consent.service.withdraw_consent` does the withdrawing; this is only its words. Before
the owner says yes, the confirm step shows what stopping will do (`stop_lines`); after, what
it did (`stopped_lines`). Both are written to him — "you" — because withdrawing is his alone:
anyone else is refused before a line is rendered (`NotTheirConsentToWithdraw`).

The words sit under `app/consent/` with the agreements they stop, in the three languages Nura
speaks, and follow docs/plain-words.md like every line he reads.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.consent.models import ConsentPurpose

LANGUAGES = ("en", "ms", "zh")

APP_STOPS: frozenset[ConsentPurpose] = frozenset(
    {ConsentPurpose.SHARE_WITH_PERSON, ConsentPurpose.RECORDING, ConsentPurpose.CALENDAR}
)
"""What the owner stops in the app with one yes. Keeping his papers and WhatsApp are not:
the not-feeling-well button and his Taken both rest on the first, and every WhatsApp message
about him — to his family too, a red flag's among them — rests on the second, so stopping
either is done with the Nura team, who can say what stops with it
(`NotStoppedInTheApp`)."""

# @patient
STOP_LINES: Mapping[str, Mapping[ConsentPurpose, tuple[str, ...]]] = {
    "en": {
        ConsentPurpose.SHARE_WITH_PERSON: (
            "If you stop this, {name} cannot see your papers.",
            "{name} stops seeing them at once.",
            "You can let {name} in again later.",
        ),
        ConsentPurpose.RECORDING: (
            "If you stop this, Nura stops listening at your visits.",
            "The recordings Nura already kept stay with your papers.",
        ),
        ConsentPurpose.CALENDAR: (
            "If you stop this, Nura stops looking in your calendar.",
            "The visits you already said yes to stay.",
        ),
    },
    "ms": {
        ConsentPurpose.SHARE_WITH_PERSON: (
            "Jika anda hentikan ini, {name} tidak boleh melihat surat-surat anda.",
            "{name} berhenti melihatnya serta-merta.",
            "Anda boleh benarkan {name} masuk semula nanti.",
        ),
        ConsentPurpose.RECORDING: (
            "Jika anda hentikan ini, Nura berhenti mendengar semasa lawatan anda.",
            "Rakaman yang Nura sudah simpan kekal bersama surat-surat anda.",
        ),
        ConsentPurpose.CALENDAR: (
            "Jika anda hentikan ini, Nura berhenti melihat kalendar anda.",
            "Lawatan yang anda sudah setuju kekal.",
        ),
    },
    "zh": {
        ConsentPurpose.SHARE_WITH_PERSON: (
            "如果您停止这个，{name} 就不能看您的文件了。",
            "{name} 马上就看不到了。",
            "以后您可以再让 {name} 进来。",
        ),
        ConsentPurpose.RECORDING: (
            "如果您停止这个，Nura 就不在您看医生的时候听了。",
            "Nura 已经保存的录音会留在您的文件里。",
        ),
        ConsentPurpose.CALENDAR: (
            "如果您停止这个，Nura 就不再看您的日历了。",
            "您已经同意的看医生预约会留着。",
        ),
    },
}
"""What stopping one agreement will do, said before his yes. `{name}` is the person let in."""

# @patient
NOT_TOLD: Mapping[str, str] = {
    "en": "Nura will not tell {name} when you are not well.",
    "ms": "Nura tidak akan beritahu {name} bila anda tidak sihat.",
    "zh": "您不舒服的时候，Nura 不会再告诉{name}。",
}
"""Said too when the person let in holds the emergency card: they come off the ladder a red
flag climbs (`app.delivery.triggers.ladder`), so they are not told when he is unwell."""

# @patient
STOPPED: Mapping[str, str] = {
    "en": "You stopped this.",
    "ms": "Anda sudah hentikan ini.",
    "zh": "您已经停止了这个。",
}
"""The first line after his yes, whatever was stopped."""

# @patient
STOPPED_LINES: Mapping[str, Mapping[ConsentPurpose, str]] = {
    "en": {
        ConsentPurpose.SHARE_WITH_PERSON: "{name} cannot see your papers now.",
        ConsentPurpose.RECORDING: "Nura will not listen at your visits to the doctor.",
        ConsentPurpose.CALENDAR: "Nura will not look in your calendar.",
    },
    "ms": {
        ConsentPurpose.SHARE_WITH_PERSON: "{name} tidak boleh melihat surat-surat anda sekarang.",
        ConsentPurpose.RECORDING: "Nura tidak akan mendengar semasa lawatan anda ke doktor.",
        ConsentPurpose.CALENDAR: "Nura tidak akan melihat kalendar anda.",
    },
    "zh": {
        ConsentPurpose.SHARE_WITH_PERSON: "{name} 现在不能看您的文件了。",
        ConsentPurpose.RECORDING: "您看医生的时候 Nura 不会再听。",
        ConsentPurpose.CALENDAR: "Nura 不会再看您的日历。",
    },
}
"""What stopping did, said after his yes."""


def language_of(asked: str | None) -> str:
    """One of the three, or English."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else "en"


def stop_lines(
    purpose: ConsentPurpose, *, name: str, language: str | None, told: bool = False
) -> list[str]:
    """What stopping this agreement will do, in his words. `name` is the person let in (for
    an agreement that names one); `told` when that person is one a red flag reaches."""
    words = language_of(language)
    lines = [line.format(name=name) for line in STOP_LINES[words][purpose]]
    if told:
        lines.insert(2, NOT_TOLD[words].format(name=name))
    return lines


def stopped_lines(
    purpose: ConsentPurpose, *, name: str, language: str | None, told: bool = False
) -> list[str]:
    """What stopping did, in his words."""
    words = language_of(language)
    lines = [STOPPED[words], STOPPED_LINES[words][purpose].format(name=name)]
    if told:
        lines.append(NOT_TOLD[words].format(name=name))
    return lines
