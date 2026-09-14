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

# @patient
STOP_LINES: Mapping[str, Mapping[ConsentPurpose, tuple[str, ...]]] = {
    "en": {
        ConsentPurpose.HOLD_HEALTH_RECORD: (
            "If you stop this, Nura keeps nothing new from today.",
            "Nura does not take away the papers it already has.",
        ),
        ConsentPurpose.SHARE_WITH_PERSON: (
            "If you stop this, {name} cannot see your papers.",
            "{name} stops seeing them at once.",
            "You can let {name} in again later.",
        ),
        ConsentPurpose.RECORDING: (
            "If you stop this, Nura stops listening at your visits.",
            "The recordings Nura already kept stay with your papers.",
        ),
        ConsentPurpose.WHATSAPP: (
            "If you stop this, Nura sends you nothing on WhatsApp.",
            "Your Today page stays in the app.",
        ),
        ConsentPurpose.CALENDAR: (
            "If you stop this, Nura stops looking in your calendar.",
            "The visits you already said yes to stay.",
        ),
    },
    "ms": {
        ConsentPurpose.HOLD_HEALTH_RECORD: (
            "Jika anda hentikan ini, Nura tidak simpan apa-apa yang baharu mulai hari ini.",
            "Nura tidak buang surat-surat yang sudah ada.",
        ),
        ConsentPurpose.SHARE_WITH_PERSON: (
            "Jika anda hentikan ini, {name} tidak boleh melihat surat-surat anda.",
            "{name} berhenti melihatnya serta-merta.",
            "Anda boleh benarkan {name} masuk semula nanti.",
        ),
        ConsentPurpose.RECORDING: (
            "Jika anda hentikan ini, Nura berhenti mendengar semasa lawatan anda.",
            "Rakaman yang Nura sudah simpan kekal bersama surat-surat anda.",
        ),
        ConsentPurpose.WHATSAPP: (
            "Jika anda hentikan ini, Nura tidak hantar apa-apa kepada anda di WhatsApp.",
            "Halaman Hari Ini anda kekal dalam aplikasi.",
        ),
        ConsentPurpose.CALENDAR: (
            "Jika anda hentikan ini, Nura berhenti melihat kalendar anda.",
            "Lawatan yang anda sudah setuju kekal.",
        ),
    },
    "zh": {
        ConsentPurpose.HOLD_HEALTH_RECORD: (
            "如果您停止这个，从今天起 Nura 不再保存新的东西。",
            "Nura 不会拿走已经有的文件。",
        ),
        ConsentPurpose.SHARE_WITH_PERSON: (
            "如果您停止这个，{name} 就不能看您的文件了。",
            "{name} 马上就看不到了。",
            "以后您可以再让 {name} 进来。",
        ),
        ConsentPurpose.RECORDING: (
            "如果您停止这个，Nura 就不在您看医生的时候听了。",
            "Nura 已经保存的录音会留在您的文件里。",
        ),
        ConsentPurpose.WHATSAPP: (
            "如果您停止这个，Nura 不会在 WhatsApp 上给您发任何东西。",
            "您的“今天”页面还在应用里。",
        ),
        ConsentPurpose.CALENDAR: (
            "如果您停止这个，Nura 就不再看您的日历了。",
            "您已经同意的看医生预约会留着。",
        ),
    },
}
"""What stopping one agreement will do, said before his yes. `{name}` is the person let in."""

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
        ConsentPurpose.HOLD_HEALTH_RECORD: "Nura keeps nothing new from today.",
        ConsentPurpose.SHARE_WITH_PERSON: "{name} cannot see your papers now.",
        ConsentPurpose.RECORDING: "Nura will not listen at your visits to the doctor.",
        ConsentPurpose.WHATSAPP: "Nura sends you nothing on WhatsApp.",
        ConsentPurpose.CALENDAR: "Nura will not look in your calendar.",
    },
    "ms": {
        ConsentPurpose.HOLD_HEALTH_RECORD: "Nura tidak simpan apa-apa yang baharu mulai hari ini.",
        ConsentPurpose.SHARE_WITH_PERSON: "{name} tidak boleh melihat surat-surat anda sekarang.",
        ConsentPurpose.RECORDING: "Nura tidak akan mendengar semasa lawatan anda ke doktor.",
        ConsentPurpose.WHATSAPP: "Nura tidak hantar apa-apa kepada anda di WhatsApp.",
        ConsentPurpose.CALENDAR: "Nura tidak akan melihat kalendar anda.",
    },
    "zh": {
        ConsentPurpose.HOLD_HEALTH_RECORD: "从今天起 Nura 不再保存新的东西。",
        ConsentPurpose.SHARE_WITH_PERSON: "{name} 现在不能看您的文件了。",
        ConsentPurpose.RECORDING: "您看医生的时候 Nura 不会再听。",
        ConsentPurpose.WHATSAPP: "Nura 不会在 WhatsApp 上给您发任何东西。",
        ConsentPurpose.CALENDAR: "Nura 不会再看您的日历。",
    },
}
"""What stopping did, said after his yes."""


def language_of(asked: str | None) -> str:
    """One of the three, or English."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else "en"


def stop_lines(purpose: ConsentPurpose, *, name: str, language: str | None) -> list[str]:
    """What stopping this agreement will do, in his words. `name` is the person let in (for
    an agreement that names one); every other agreement has no slot for it."""
    return [line.format(name=name) for line in STOP_LINES[language_of(language)][purpose]]


def stopped_lines(purpose: ConsentPurpose, *, name: str, language: str | None) -> list[str]:
    """What stopping did, in his words."""
    words = language_of(language)
    return [STOPPED[words], STOPPED_LINES[words][purpose].format(name=name)]
