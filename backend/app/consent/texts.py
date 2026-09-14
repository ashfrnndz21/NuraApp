"""The words a person agreed to, by purpose, version, language and region.

Every wording ever shown stays here, because the record of a consent has to be able to say
what was agreed to even after the words have moved on. A new version is appended, never
edited in place; the newest per purpose is the one a fresh consent is asked for, and an
older one no longer stands for it. A consent can only be recorded in words that are here,
in the language they were shown in: the record never claims someone agreed to words that
do not exist.

Letting one person in is agreed to in words that name that person and what they will see:
the wording for `SHARE_WITH_PERSON` is a template with `{name}` and `{what}`, rendered at
the moment of agreement and kept on the row as rendered. `{what}` is the parts of the
record, in the patient's words for them (`SCOPE_WORDS`).

The summaries are what the patient reads, so they follow `docs/plain-words.md`: whole
sentences, one idea per line, his words for things ("your papers", "your blood pressure
book", "your Today page"), the name of his country, nothing to decode. Where the words
name the country, there is one text per region. Nura speaks four languages; the words
are here in English, Malay and Chinese, and Tamil is still to come.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.consent.models import ConsentPurpose
from app.keys.scopes import Scope
from app.regions import Region

# @patient
LANGUAGES: Mapping[str, str] = {"en": "English", "zh": "Chinese", "ms": "Malay", "ta": "Tamil"}
"""The languages Nura speaks, by code, with the name the page uses. Nothing else is a
language a consent can be recorded in."""

# @patient
SCOPE_WORDS: Mapping[str, Mapping[Scope, str]] = {
    "en": {
        Scope.MEDICINES: "medicines",
        Scope.VISITS: "visits to the doctor",
        Scope.READINGS: "blood pressure and sugar numbers",
        Scope.RECORDS: "papers",
        Scope.NOTES: "private notes",
        Scope.MONEY: "insurance letters",
        Scope.EMERGENCY: "emergency card",
        Scope.FAMILY: "family list",
        Scope.ASK: "questions to Nura",
        Scope.SEND: "messages Nura sends",
    },
    "ms": {
        Scope.MEDICINES: "ubat",
        Scope.VISITS: "lawatan ke doktor",
        Scope.READINGS: "bacaan tekanan darah dan gula",
        Scope.RECORDS: "surat-surat",
        Scope.NOTES: "nota peribadi",
        Scope.MONEY: "surat insurans",
        Scope.EMERGENCY: "kad kecemasan",
        Scope.FAMILY: "senarai keluarga",
        Scope.ASK: "soalan kepada Nura",
        Scope.SEND: "mesej yang Nura hantar",
    },
    "zh": {
        Scope.MEDICINES: "药物",
        Scope.VISITS: "看医生的记录",
        Scope.READINGS: "血压和血糖数字",
        Scope.RECORDS: "病历文件",
        Scope.NOTES: "私人笔记",
        Scope.MONEY: "保险信件",
        Scope.EMERGENCY: "紧急卡",
        Scope.FAMILY: "家人名单",
        Scope.ASK: "问 Nura 的问题",
        Scope.SEND: "Nura 发的信息",
    },
}
"""The parts of the record, in his words, in the order the page lists them. `PROFILE` is
not a part of the record — it is whose record it is — so it is never a thing to see."""

_AND: Mapping[str, str] = {"en": " and ", "ms": " dan ", "zh": "和"}
_COMMA: Mapping[str, str] = {"en": ", ", "ms": ", ", "zh": "、"}


@dataclass(frozen=True, slots=True)
class ConsentText:
    purpose: ConsentPurpose
    version: str
    language: str
    summary: str
    """The plain-words statement of what the person is agreeing to. For a per-holder
    purpose, a template with `{name}` and `{what}`."""
    region: Region | None = None
    """The region these words are for, or None for words that serve every region."""


# @patient
TEXTS: tuple[ConsentText, ...] = (
    # --- keeping the record ---------------------------------------------------------------
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They never leave Singapore. "
        "You can stop this at any time. "
        "Nura then stops keeping anything new.",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They never leave Malaysia. "
        "You can stop this at any time. "
        "Nura then stops keeping anything new.",
        region=Region.MY,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "ms",
        "Nura menyimpan surat-surat anda, ubat anda dan buku tekanan darah anda. "
        "Semuanya tidak pernah keluar dari Singapura. "
        "Anda boleh berhenti pada bila-bila masa. "
        "Selepas itu Nura tidak menyimpan apa-apa yang baru.",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "ms",
        "Nura menyimpan surat-surat anda, ubat anda dan buku tekanan darah anda. "
        "Semuanya tidak pernah keluar dari Malaysia. "
        "Anda boleh berhenti pada bila-bila masa. "
        "Selepas itu Nura tidak menyimpan apa-apa yang baru.",
        region=Region.MY,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "zh",
        "Nura 帮您保存您的病历文件、您的药物和您的血压本。"
        "这些东西不会离开新加坡。"
        "您可以随时停止。"
        "之后 Nura 就不再保存新的东西。",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "zh",
        "Nura 帮您保存您的病历文件、您的药物和您的血压本。"
        "这些东西不会离开马来西亚。"
        "您可以随时停止。"
        "之后 Nura 就不再保存新的东西。",
        region=Region.MY,
    ),
    # --- letting one person in --------------------------------------------------------------
    # Version 1 spoke of "your family" and named nobody; it stays as history. Version 2 names
    # the person and what they will see.
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "1",
        "en",
        "You choose who in your family can see your papers. "
        "You can see who looked at them. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "2",
        "en",
        "You are letting {name} see your {what}. "
        "{name} can see these until you say stop. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "2",
        "ms",
        "Anda membenarkan {name} melihat {what} anda. "
        "{name} boleh melihatnya sehingga anda kata berhenti. "
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "2",
        "zh",
        "您让{name}看您的{what}。"
        "{name}可以一直看，直到您说停止。"
        "您可以随时停止。",
    ),
    # --- recording the visit ---------------------------------------------------------------
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "en",
        "When you see the doctor, Nura listens and keeps what you and the doctor say. "
        "You can hear it again later. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "ms",
        "Semasa anda berjumpa doktor, Nura mendengar dan menyimpan apa yang anda dan doktor "
        "katakan. "
        "Anda boleh mendengarnya semula kemudian. "
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "zh",
        "您看医生的时候，Nura 会听并保存您和医生说的话。"
        "您以后可以再听一次。"
        "您可以随时停止。",
    ),
    # --- WhatsApp -----------------------------------------------------------------------------
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "en",
        "Every morning, Nura sends your Today page to you on WhatsApp. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "ms",
        "Setiap pagi, Nura menghantar halaman Hari Ini anda kepada anda di WhatsApp. "
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "zh",
        "每天早上，Nura 会把您的今日页面发到您的 WhatsApp。"
        "您可以随时停止。",
    ),
)
"""Append only. Within a purpose, versions are in the order they were introduced, and the
last one is current. Every version needs its English wording for every region; other
languages are added as they are translated, and a consent in a language that is not here
yet cannot be recorded. The Malay and Chinese words are a first translation awaiting a
native speaker's pass; Tamil is not here yet."""


def versions(purpose: ConsentPurpose) -> list[str]:
    """Every version ever shown for this purpose, oldest first, each once."""
    seen: list[str] = []
    for text in TEXTS:
        if text.purpose is purpose and text.version not in seen:
            seen.append(text.version)
    return seen


def current_version(purpose: ConsentPurpose) -> str:
    """The version a consent given today is asked for: the last one appended."""
    return versions(purpose)[-1]


def wording(purpose: ConsentPurpose, version: str, language: str, region: Region) -> str | None:
    """The words shown for this purpose, version and language in this region, or None.

    Words written for the region win over words written for every region. A language Nura
    does not speak has no words, whatever the catalogue says. For a per-holder purpose this
    is the template; `render_sharing` fills it in.
    """
    if language not in LANGUAGES:
        return None
    anywhere: str | None = None
    for text in TEXTS:
        if text.purpose is purpose and text.version == version and text.language == language:
            if text.region is region:
                return text.summary
            if text.region is None:
                anywhere = text.summary
    return anywhere


def what_words(scopes: Iterable[Scope], language: str) -> str:
    """The parts of the record, in his words, joined the way his language joins a list."""
    words = SCOPE_WORDS.get(language, SCOPE_WORDS["en"])
    parts = [words[scope] for scope in words if scope in set(scopes)]
    if not parts:
        return words[Scope.RECORDS]
    if len(parts) == 1:
        return parts[0]
    comma, and_ = _COMMA.get(language, ", "), _AND.get(language, " and ")
    return comma.join(parts[:-1]) + and_ + parts[-1]


def render_sharing(template: str, *, name: str, scopes: Iterable[Scope], language: str) -> str:
    """Fill the sharing template with the person and the parts, as the patient will read it."""
    return template.format(name=name, what=what_words(scopes, language))
