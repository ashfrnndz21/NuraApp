"""Stopping one agreement, as the owner reads it before and after (E00-02).

`app.consent.service.withdraw_consent` does the withdrawing; this is only its words. Before
the owner says yes, the confirm step shows what stopping will do (`stop_lines`); after, what
it did (`stopped_lines`). Both are written to him — "you" — because withdrawing is his alone:
anyone else is refused before a line is rendered (`NotTheirConsentToWithdraw`).

The words sit under `app/consent/` with the agreements they stop, in the three languages Nura
speaks, and follow docs/plain-words.md like every line he reads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.consent.models import ConsentPurpose

LANGUAGES = ("en", "ms", "zh")

APP_STOPS: frozenset[ConsentPurpose] = frozenset(
    {
        ConsentPurpose.SHARE_WITH_PERSON,
        ConsentPurpose.RECORDING,
        ConsentPurpose.CALENDAR,
        ConsentPurpose.WHATSAPP,
    }
)
"""What the owner stops in the app with one yes. WhatsApp is among them since #143: his
agreement is for messages to him, and his family's red-flag notices rest on their own keys.
Stopping it stops what reaches him on WhatsApp, and every other message about him to his
family there (#163): they are told on WhatsApp only when he is unwell — or in the app, for
whoever cannot be sent WhatsApp — and get everything else in the app. The confirm step says
exactly that.
Keeping his papers is not stopped here: that is closing his account (`app.identity.closing`),
which says what it stops, and when his papers go (`StopsByClosingTheAccount`)."""

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
        ConsentPurpose.WHATSAPP: (
            "If you stop this, Nura stops messaging you on WhatsApp.",
            "Your Today page and reminders will not come there.",
            "You can say yes to WhatsApp again later.",
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
        ConsentPurpose.WHATSAPP: (
            "Jika anda hentikan ini, Nura berhenti menghantar mesej kepada anda di WhatsApp.",
            "Halaman Hari Ini dan peringatan anda tidak akan datang di situ.",
            "Anda boleh setuju dengan WhatsApp semula nanti.",
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
        ConsentPurpose.WHATSAPP: (
            "如果您停止这个，Nura 就不再在 WhatsApp 上给您发消息。",
            "您的“今天”页面和提醒不会再发到那里。",
            "以后您可以再同意使用 WhatsApp。",
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
        ConsentPurpose.WHATSAPP: "Nura will not message you on WhatsApp.",
    },
    "ms": {
        ConsentPurpose.SHARE_WITH_PERSON: "{name} tidak boleh melihat surat-surat anda sekarang.",
        ConsentPurpose.RECORDING: "Nura tidak akan mendengar semasa lawatan anda ke doktor.",
        ConsentPurpose.CALENDAR: "Nura tidak akan melihat kalendar anda.",
        ConsentPurpose.WHATSAPP: "Nura tidak akan menghantar mesej kepada anda di WhatsApp.",
    },
    "zh": {
        ConsentPurpose.SHARE_WITH_PERSON: "{name} 现在不能看您的文件了。",
        ConsentPurpose.RECORDING: "您看医生的时候 Nura 不会再听。",
        ConsentPurpose.CALENDAR: "Nura 不会再看您的日历。",
        ConsentPurpose.WHATSAPP: "Nura 不会再在 WhatsApp 上给您发消息。",
    },
}
"""What stopping did, said after his yes."""

# @patient
LEAVES_GROUP: Mapping[str, str] = {
    "en": "You leave the family group on WhatsApp.",
    "ms": "Anda keluar dari kumpulan keluarga di WhatsApp.",
    "zh": "您会退出 WhatsApp 上的家人群组。",
}
"""Stopping WhatsApp, when his family has a group there: he is out of it, at once (#143)."""

# @patient
LEFT_GROUP: Mapping[str, str] = {
    "en": "You are not in the family group on WhatsApp now.",
    "ms": "Anda tidak lagi dalam kumpulan keluarga di WhatsApp.",
    "zh": "您现在不在 WhatsApp 上的家人群组里了。",
}
"""Said after his yes, when he was in the family's group."""

# @patient
STILL_TOLD: Mapping[str, str] = {
    "en": "{named} is still told on WhatsApp when you are unwell.",
    "ms": "{named} masih diberitahu di WhatsApp apabila anda tidak sihat.",
    "zh": "您不舒服时，{named}仍会在 WhatsApp 上收到通知。",
}
"""Stopping WhatsApp, for each person a red flag reaches there: they are told on their own
key, not on his agreement (#143). `named` is the person as the words name them — "Mei, your
daughter," — from the relationship code, in his language (`app.consent.texts.named_words`)."""

# @patient
STILL_TOLD_IN_APP: Mapping[str, str] = {
    "en": "{named} is still told in the app when you are unwell.",
    "ms": "{named} masih diberitahu dalam aplikasi apabila anda tidak sihat.",
    "zh": "您不舒服时，{named}仍会在应用里收到通知。",
}
"""The same, for someone a red flag reaches but Nura cannot send WhatsApp: they said no to it,
or Nura has no number for them (#163)."""

# @patient
NOTHING_ELSE: Mapping[str, str] = {
    "en": "Your family gets other messages about you only in the app.",
    "ms": "Keluarga anda dapat mesej lain tentang anda hanya dalam aplikasi.",
    "zh": "关于您的其他消息，家人只会在应用里收到。",
}
"""Stopping WhatsApp, when he has family on it: nothing but a red flag goes to them about him
on WhatsApp now (`app.channels.whatsapp.outbound.send._may_message`, #163)."""


def language_of(asked: str | None) -> str:
    """One of the three, or English."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else "en"


def stop_lines(
    purpose: ConsentPurpose,
    *,
    name: str,
    language: str | None,
    told: bool = False,
    in_group: bool = False,
    still_told: Sequence[str] = (),
    told_in_app: Sequence[str] = (),
) -> list[str]:
    """What stopping this agreement will do, in his words. `name` is the person let in (for
    an agreement that names one); `told` when that person is one a red flag reaches. For
    WhatsApp, exactly what changes: `in_group` when he is in his family's group there;
    `still_told` names everyone a red flag still reaches on WhatsApp, `told_in_app` everyone it
    reaches only in the app (#143, #163); and, with any of them, that nothing else about him
    goes to them on WhatsApp."""
    words = language_of(language)
    lines = [line.format(name=name) for line in STOP_LINES[words][purpose]]
    if told:
        lines.insert(2, NOT_TOLD[words].format(name=name))
    if purpose is ConsentPurpose.WHATSAPP:
        lines[2:2] = _what_whatsapp_keeps(words, in_group, still_told, told_in_app)
    return lines


def _what_whatsapp_keeps(
    words: str, in_group: bool, still_told: Sequence[str], told_in_app: Sequence[str]
) -> list[str]:
    family = [STILL_TOLD[words].format(named=named) for named in still_told] + [
        STILL_TOLD_IN_APP[words].format(named=named) for named in told_in_app
    ]
    return ([LEAVES_GROUP[words]] if in_group else []) + family + ([NOTHING_ELSE[words]] if family else [])


def stopped_lines(
    purpose: ConsentPurpose,
    *,
    name: str,
    language: str | None,
    told: bool = False,
    in_group: bool = False,
    still_told: Sequence[str] = (),
    told_in_app: Sequence[str] = (),
) -> list[str]:
    """What stopping did, in his words."""
    words = language_of(language)
    lines = [STOPPED[words], STOPPED_LINES[words][purpose].format(name=name)]
    if told:
        lines.append(NOT_TOLD[words].format(name=name))
    if purpose is ConsentPurpose.WHATSAPP:
        if in_group:
            lines.append(LEFT_GROUP[words])
        lines += _what_whatsapp_keeps(words, False, still_told, told_in_app)
    return lines
