"""The words a person agreed to, by purpose, version, language and region.

Every wording ever shown stays here, because the record of a consent has to be able to say
what was agreed to even after the words have moved on. A new version is appended, never
edited in place; the newest per purpose is the one a fresh consent is asked for, and an
older one no longer stands for it. A consent can only be recorded in words that are here,
in the language they were shown in: the record never claims someone agreed to words that
do not exist.

Letting one person in is agreed to in words that name that person and what they will see:
the wording for `SHARE_WITH_PERSON` is a template with `{named}` (the person, with who they
are to him if the granter said), `{name}` (the person again), `{parts}` (one line per
part of the record, in his words — `SCOPE_WORDS`) and, from version 3 (#185), `{role_line}`
and `{window_line}` (what they are cut a key as, and for how long, in the family screen's
own words — `app.family.strings.ROLE_IS`, `WINDOW_LINES`) — rendered at the moment of
agreement and kept on the row as rendered, one line per idea.

The summaries are what the patient reads, so they follow `docs/plain-words.md`: whole
sentences, one idea per line, his words for things ("your papers", "your blood pressure
book", "your Today page"), the name of his country, nothing to decode. Where the words
name the country, there is one text per region. The words are here in English, Malay and
Chinese; Tamil joins the languages Nura speaks when its words are on file.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.consent.models import ConsentPurpose
from app.family.relationships import relationship_words
from app.family.strings import ROLE_IS, ROLE_WORDS, WINDOW_LINES
from app.keys.scopes import KeyRole, KeyWindow, Scope
from app.regions import Region

# @patient phrase
LANGUAGES: Mapping[str, str] = {"en": "English", "zh": "Chinese", "ms": "Malay"}
"""The languages Nura speaks today, by code, with the name the page uses. Nothing else is a
language a consent can be recorded in. Tamil is added here the day its words are in TEXTS."""

# @patient phrase
SCOPE_WORDS: Mapping[str, Mapping[Scope, str]] = {
    "en": {
        Scope.MEDICINES: "your medicines",
        Scope.VISITS: "your visits to the doctor",
        Scope.READINGS: "your blood pressure book and your sugar numbers",
        Scope.RECORDS: "your papers",
        Scope.NOTES: "your private notes",
        Scope.MONEY: "your insurance letters",
        Scope.EMERGENCY: "your emergency card",
        Scope.FAMILY: "your family list",
        Scope.ASK: "your questions to Nura",
        Scope.SEND: "the messages Nura sends",
    },
    "ms": {
        Scope.MEDICINES: "ubat anda",
        Scope.VISITS: "lawatan anda ke doktor",
        Scope.READINGS: "buku tekanan darah dan bacaan gula anda",
        Scope.RECORDS: "surat-surat anda",
        Scope.NOTES: "nota peribadi anda",
        Scope.MONEY: "surat insurans anda",
        Scope.EMERGENCY: "kad kecemasan anda",
        Scope.FAMILY: "senarai keluarga anda",
        Scope.ASK: "soalan anda kepada Nura",
        Scope.SEND: "mesej yang Nura hantar",
    },
    "zh": {
        Scope.MEDICINES: "您的药",
        Scope.VISITS: "您看医生的记录",
        Scope.READINGS: "您的血压本和血糖数字",
        Scope.RECORDS: "您的病历文件",
        Scope.NOTES: "您的私人笔记",
        Scope.MONEY: "您的保险信件",
        Scope.EMERGENCY: "您的紧急卡",
        Scope.FAMILY: "您的家人名单",
        Scope.ASK: "您问 Nura 的问题",
        Scope.SEND: "Nura 发的信息",
    },
}
"""The parts of the record, in his words, one line each, in the order the page lists them.
`PROFILE` is not a part of the record — it is whose record it is — so it is never a thing
to see."""

# @patient phrase
NAMED_WITH_RELATIONSHIP: Mapping[str, str] = {
    "en": "{name}, {relationship},",
    "ms": "{name}, {relationship},",
    "zh": "{name}（{relationship}）",
}
"""How each language says who the person is to him, when the granter said: "Ash, your
daughter," in English and Malay, "Ash（您的女儿）" in Chinese. `relationship` is the code's
words in the language of the words (`app.family.relationships`)."""


@dataclass(frozen=True, slots=True)
class ConsentText:
    purpose: ConsentPurpose
    version: str
    language: str
    summary: str
    """The plain-words statement of what the person is agreeing to, one line per idea. For a
    per-holder purpose, a template with `{named}`, `{name}` and `{parts}`."""
    region: Region | None = None
    """The region these words are for, or None for words that serve every region."""


# @patient
TEXTS: tuple[ConsentText, ...] = (
    # --- keeping the record ---------------------------------------------------------------
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book.\n"
        "They never leave Singapore.\n"
        "You can tell Nura to stop at any time.\n"
        "After that day, Nura keeps nothing new.\n"
        "The papers Nura already has stay in your record.",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "en",
        "Nura keeps your papers, your medicines and your blood pressure book.\n"
        "They never leave Malaysia.\n"
        "You can tell Nura to stop at any time.\n"
        "After that day, Nura keeps nothing new.\n"
        "The papers Nura already has stay in your record.",
        region=Region.MY,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "ms",
        "Nura menyimpan surat-surat anda, ubat anda dan buku tekanan darah anda.\n"
        "Semuanya kekal di Singapura.\n"
        "Anda boleh minta Nura berhenti pada bila-bila masa.\n"
        "Selepas itu, Nura tidak menyimpan apa-apa yang baru.\n"
        "Apa yang sudah disimpan kekal dalam rekod anda.",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "ms",
        "Nura menyimpan surat-surat anda, ubat anda dan buku tekanan darah anda.\n"
        "Semuanya kekal di Malaysia.\n"
        "Anda boleh minta Nura berhenti pada bila-bila masa.\n"
        "Selepas itu, Nura tidak menyimpan apa-apa yang baru.\n"
        "Apa yang sudah disimpan kekal dalam rekod anda.",
        region=Region.MY,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "zh",
        "Nura 帮您保存您的病历文件、您的药和您的血压本。\n"
        "这些东西不会离开新加坡。\n"
        "您可以随时叫 Nura 停下来。\n"
        "从那天起，Nura 不再保存新的东西。\n"
        "已经保存的，还是留在您的记录里。",
        region=Region.SG,
    ),
    ConsentText(
        ConsentPurpose.HOLD_HEALTH_RECORD,
        "1",
        "zh",
        "Nura 帮您保存您的病历文件、您的药和您的血压本。\n"
        "这些东西不会离开马来西亚。\n"
        "您可以随时叫 Nura 停下来。\n"
        "从那天起，Nura 不再保存新的东西。\n"
        "已经保存的，还是留在您的记录里。",
        region=Region.MY,
    ),
    # --- letting one person in --------------------------------------------------------------
    # Version 1 spoke of "your family" and named nobody; it stays as history. Version 2 names
    # the person and lists what they will see.
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "1",
        "en",
        "You choose who in your family can see your papers. "  # plain-words: history, not shown
        "You can see who looked at them. "
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "2",
        "en",
        "You are letting {named} see some of your record.\n"
        "{name} can see these parts:\n"
        "{parts}\n"
        "{name} can see them until you say stop.\n"
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "2",
        "ms",
        "Anda membenarkan {named} melihat sebahagian daripada rekod anda.\n"
        "{name} boleh melihat bahagian ini:\n"
        "{parts}\n"
        "{name} boleh melihatnya sehingga anda minta ia dihentikan.\n"
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "2",
        "zh",
        "您让{named}看您记录里的一部分。\n"
        "{name} 可以看这些：\n"
        "{parts}\n"
        "{name} 可以一直看，直到您说停。\n"
        "您可以随时停止。",
    ),
    # Version 3 (#185) names the role and the window, not only the person and the parts: a
    # key cut under this consent is refused if it asks for a different role or a window that
    # runs longer than the one named here (`app.keys.grants.grant_key`). `{role_line}` and
    # `{window_line}` are rendered with the family screen's own words for a role
    # (`app.family.strings.ROLE_IS`) and a window (`WINDOW_LINES`), so what the patient reads
    # here is what the family screen says the key opens.
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "3",
        "en",
        "You are letting {named} see some of your record.\n"
        "{role_line}\n"
        "{name} can see these parts:\n"
        "{parts}\n"
        "{window_line}\n"
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "3",
        "ms",
        "Anda membenarkan {named} melihat sebahagian daripada rekod anda.\n"
        "{role_line}\n"
        "{name} boleh melihat bahagian ini:\n"
        "{parts}\n"
        "{window_line}\n"
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.SHARE_WITH_PERSON,
        "3",
        "zh",
        "您让{named}看您记录里的一部分。\n"
        "{role_line}\n"
        "{name} 可以看这些：\n"
        "{parts}\n"
        "{window_line}\n"
        "您可以随时停止。",
    ),
    # --- recording the visit ---------------------------------------------------------------
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "en",
        "When you see the doctor, Nura listens.\n"
        "Nura keeps what you and the doctor say.\n"
        "Only you and the family you let in can hear it.\n"
        "You can hear it again whenever you want.\n"
        "You can tell Nura to stop at any time.",
    ),
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "ms",
        "Semasa anda berjumpa doktor, Nura mendengar.\n"
        "Nura menyimpan apa yang anda dan doktor katakan.\n"
        "Hanya anda dan keluarga yang anda benarkan boleh mendengarnya.\n"
        "Anda boleh mendengarnya semula bila-bila masa.\n"
        "Anda boleh minta Nura berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.RECORDING,
        "1",
        "zh",
        "您看医生的时候，Nura 会听。\n"
        "Nura 会保存您和医生说的话。\n"
        "只有您和您让进来的家人可以听。\n"
        "您什么时候想听，都可以再听一次。\n"
        "您可以随时叫 Nura 停下来。",
    ),
    # --- WhatsApp -----------------------------------------------------------------------------
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "en",
        "Every morning, Nura sends you your Today page on WhatsApp.\n"
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "ms",
        "Setiap pagi, Nura menghantar halaman Hari Ini anda melalui WhatsApp.\n"
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.WHATSAPP,
        "1",
        "zh",
        "每天早上，Nura 会把您的今日页面发到您的 WhatsApp。\n您可以随时停止。",
    ),
    # --- the calendar (E18-02) ---------------------------------------------------------------
    # Read for events, never for people: docs/read-only-connectors.md section 2.
    ConsentText(
        ConsentPurpose.CALENDAR,
        "1",
        "en",
        "Nura reads your calendar to find visits to the doctor.\n"
        "Nura keeps only the visits it finds.\n"
        "Everything else in your calendar is left alone.\n"
        "Nothing is added until you say yes.\n"
        "Nura never writes in your calendar.\n"
        "You can stop this at any time.",
    ),
    ConsentText(
        ConsentPurpose.CALENDAR,
        "1",
        "ms",
        "Nura membaca kalendar anda untuk mencari lawatan ke doktor.\n"
        "Nura menyimpan lawatan yang dijumpai sahaja.\n"
        "Yang lain dalam kalendar anda tidak disentuh.\n"
        "Tiada apa-apa ditambah sehingga anda kata ya.\n"
        "Nura tidak pernah menulis dalam kalendar anda.\n"
        "Anda boleh berhenti pada bila-bila masa.",
    ),
    ConsentText(
        ConsentPurpose.CALENDAR,
        "1",
        "zh",
        "Nura 会看您的日历，找出看医生的时间。\n"
        "Nura 只保存找到的看医生时间。\n"
        "日历里其他的东西都不碰。\n"
        "您说好之前，什么都不会加进去。\n"
        "Nura 从来不会写进您的日历。\n"
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


# @patient
def what_lines(scopes: Iterable[Scope], language: str) -> list[str]:
    """The parts of the record, in his words, one line each, in the page's order."""
    words = SCOPE_WORDS.get(language, SCOPE_WORDS["en"])
    wanted = set(scopes)
    parts = [words[scope] for scope in words if scope in wanted]
    return parts or [words[Scope.RECORDS]]


# @patient
def named_words(name: str, relationship: str | None, language: str) -> str:
    """The person as the words first name them: "Ash", or "Ash, your daughter,". The
    relationship is a code (`app.family.relationships`), said here in the words' language."""
    said = relationship_words(relationship, language)
    if said is None:
        return name
    pattern = NAMED_WITH_RELATIONSHIP.get(language, NAMED_WITH_RELATIONSHIP["en"])
    return pattern.format(name=name, relationship=said)


# @patient
def render_sharing(
    template: str,
    *,
    name: str,
    relationship: str | None,
    scopes: Iterable[Scope],
    role: KeyRole,
    window: KeyWindow,
    language: str,
) -> str:
    """Fill the sharing template with the person, the parts, the role and the window, as the
    patient will read it (#185). `role` and `window` are always given — a version that does
    not name them (version 1 and 2, kept as history) simply never reads `{role_line}` or
    `{window_line}`, so filling them in is never wrong."""
    parts = "\n".join(f"- {part}" for part in what_lines(scopes, language))
    role_line = ROLE_IS[language].format(name=name, role=ROLE_WORDS[language][role])
    window_line = WINDOW_LINES[language][window].format(name=name)
    return template.format(
        named=named_words(name, relationship, language),
        name=name,
        parts=parts,
        role_line=role_line,
        window_line=window_line,
    )
