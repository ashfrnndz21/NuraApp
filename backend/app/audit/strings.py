"""The trail in his words (E12-04): every line of the audit trail as a sentence.

The trail stores a class name for a refusal and a table name for what was touched
(`app.audit.models`), because the trail must never carry what the record said. When the
patient reads it, neither may reach him raw. This is the total map from those names to
sentences a daughter would say out loud: an arm for every refusal Nura raises, a word for
every table it touches, and a default arm for each, so that a name added tomorrow renders
as a sentence today. Every line follows `docs/plain-words.md` and is checked by
`make plain-words`; `app.family.trail` fills the slots and groups the lines by day.

The slots: `{who}` is the person, or "You" when it is the patient himself; `{what}` is the
part of his record in his words; `{day}` is "Monday 14 September"; `{other}` is who a copy
went to. Nothing else is ever put into a line — no id, no class name, no table name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.audit.models import Action
from app.consent.texts import SCOPE_WORDS
from app.keys.scopes import Scope

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

Lines = Sequence[str]

# @patient phrase
YOU: Mapping[str, str] = {"en": "You", "ms": "Anda", "zh": "您"}
"""The patient, as the subject of his own line."""

NURA = "Nura"
"""Nura itself, as the subject of a line: the reminders it sends, the checks it makes. A
name, the same in every language, so not a line of the catalogue."""

# @patient
SYSTEM_CHECKS: Mapping[str, str] = {
    "en": "On {day}, Nura checked your papers {count} times to remind you on time.",
    "ms": "Pada {day}, Nura menyemak surat-surat anda {count} kali untuk ingatkan anda tepat pada masanya.",
    "zh": "{day}，Nura 查看了您的文件 {count} 次，好按时提醒您。",
}
"""The day's reads by Nura itself, folded into one line (the delivery engine checks every few
minutes; one line, not hundreds)."""

# @patient phrase
TARGET_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "profile": "your papers",
        "audit_entry": "who looked at your papers",
        "key": "the keys to your papers",
        "consent": "what you agreed to",
        "consent_record": "the page of what you agreed to",
        "stewardship": "who set up your papers",
        "confirmation": "your yes",
        "state_snapshot": "how you are doing",
        "review_card": "the paper Nura read",
        "review_field": "the paper Nura read",
        "thread_message": "the family messages",
        "roster_slot": "who is on duty",
        "task": "what the family will do",
        "privacy": "what only you can see",
        "document": "your papers",
        "delivery": "the messages Nura sent",
        "delivery_ladder": "who Nura asked to check on you",
        "delivery_settings": "when Nura sends you things",
        "attachment": "your papers",
        "provider_note": "the notes about your doctors",
        "last_looked": "what changed in your papers",
        "ask": "your questions to Nura",
    },
    "ms": {
        "profile": "surat-surat anda",
        "audit_entry": "siapa yang melihat surat-surat anda",
        "key": "kunci surat-surat anda",
        "consent": "apa yang anda setuju",
        "consent_record": "halaman apa yang anda setuju",
        "stewardship": "siapa yang membuka surat-surat anda",
        "confirmation": "jawapan ya anda",
        "state_snapshot": "keadaan anda",
        "review_card": "kertas yang Nura baca",
        "review_field": "kertas yang Nura baca",
        "thread_message": "mesej keluarga",
        "roster_slot": "siapa yang bertugas",
        "task": "apa yang keluarga akan buat",
        "privacy": "apa yang hanya anda boleh lihat",
        "document": "surat-surat anda",
        "delivery": "mesej yang Nura hantar",
        "delivery_ladder": "siapa yang Nura minta tengok anda",
        "delivery_settings": "bila Nura hantar sesuatu kepada anda",
        "attachment": "surat-surat anda",
        "provider_note": "nota tentang doktor anda",
        "last_looked": "apa yang berubah dalam surat-surat anda",
        "ask": "soalan anda kepada Nura",
    },
    "zh": {
        "profile": "您的文件",
        "audit_entry": "谁看过您的文件",
        "key": "您文件的钥匙",
        "consent": "您同意过的事",
        "consent_record": "您同意过的事那一页",
        "stewardship": "谁开了您的文件",
        "confirmation": "您的同意",
        "state_snapshot": "您的近况",
        "review_card": "Nura 读过的纸",
        "review_field": "Nura 读过的纸",
        "thread_message": "家人的留言",
        "roster_slot": "谁在值班",
        "task": "家人要做的事",
        "privacy": "只有您能看的部分",
        "document": "您的病历文件",
        "delivery": "Nura 发出的消息",
        "delivery_ladder": "Nura 请谁来看您",
        "delivery_settings": "Nura 什么时候给您发东西",
        "attachment": "您的病历文件",
        "provider_note": "关于您的医生的留言",
        "last_looked": "您的文件有什么变化",
        "ask": "您问 Nura 的问题",
    },
}
"""His words for the tables whose scope's words would say the wrong thing. Every other
table — the medicines, the visits, the readings, the notes — is named by the words of the
scope it was touched under (`app.consent.texts.SCOPE_WORDS`), which is the default arm."""

# @patient
ALLOWED: Mapping[str, Mapping[Action, str]] = {
    "en": {
        Action.READ: "{who} looked at {what} on {day}.",
        Action.WRITE: "{who} wrote in {what} on {day}.",
        Action.SHARE: "{who} shared {what} with {other} on {day}.",
    },
    "ms": {
        Action.READ: "{who} melihat {what} pada {day}.",
        Action.WRITE: "{who} menulis dalam {what} pada {day}.",
        Action.SHARE: "{who} berkongsi {what} dengan {other} pada {day}.",
    },
    "zh": {
        Action.READ: "{who}在{day}看了{what}。",
        Action.WRITE: "{who}在{day}写了{what}。",
        Action.SHARE: "{who}在{day}把{what}分享给{other}。",
    },
}
"""A reach that landed: who, what, when. Never what it said."""

ONLY_YOU = "only_you"
NO_KEY_TO_PART = "no_key_to_part"
KEY_CLOSED = "key_closed"
CANNOT_CHANGE = "cannot_change"
NO_YES = "no_yes"
NOT_AGREED = "not_agreed"
WIDER = "wider"
DEFAULT = "default"

# @patient
REFUSED: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        ONLY_YOU: ("{who} asked to see {what} on {day}.", "Only you can."),
        NO_KEY_TO_PART: (
            "{who} asked to see {what} on {day}.",
            "{who} does not have a key to that part.",
            "Nothing was shown.",
        ),
        KEY_CLOSED: (
            "{who} tried to open your papers on {day}.",
            "That key is closed, so nothing was shown.",
        ),
        CANNOT_CHANGE: (
            "{who} asked to change {what} on {day}.",
            "Only you can say yes to that.",
            "Nothing changed.",
        ),
        NO_YES: (
            "{who} tried to save {what} on {day}.",
            "Nura did not hear a fresh yes.",
            "Nothing changed.",
        ),
        NOT_AGREED: (
            "{who} asked to let someone in on {day}.",
            "You had not agreed to that.",
            "Nothing changed.",
        ),
        WIDER: (
            "{who} asked to show someone more on {day}.",
            "That needs your agreement first.",
            "Nothing changed.",
        ),
        DEFAULT: ("Something did not save on {day}.", "Nothing in your papers changed."),
    },
    "ms": {
        ONLY_YOU: ("{who} minta melihat {what} pada {day}.", "Hanya anda boleh."),
        NO_KEY_TO_PART: (
            "{who} minta melihat {what} pada {day}.",
            "{who} tidak ada kunci untuk bahagian itu.",
            "Tiada apa yang ditunjukkan.",
        ),
        KEY_CLOSED: (
            "{who} cuba membuka surat-surat anda pada {day}.",
            "Kunci itu sudah ditutup, jadi tiada apa yang ditunjukkan.",
        ),
        CANNOT_CHANGE: (
            "{who} minta mengubah {what} pada {day}.",
            "Hanya anda boleh bersetuju.",
            "Tiada apa yang berubah.",
        ),
        NO_YES: (
            "{who} cuba menyimpan {what} pada {day}.",
            "Nura tidak dengar jawapan ya yang baru.",
            "Tiada apa yang berubah.",
        ),
        NOT_AGREED: (
            "{who} minta membenarkan seseorang masuk pada {day}.",
            "Anda belum bersetuju.",
            "Tiada apa yang berubah.",
        ),
        WIDER: (
            "{who} minta memberi seseorang lebih untuk dilihat pada {day}.",
            "Itu perlukan persetujuan anda dahulu.",
            "Tiada apa yang berubah.",
        ),
        DEFAULT: (
            "Sesuatu tidak tersimpan pada {day}.",
            "Tiada apa dalam surat-surat anda berubah.",
        ),
    },
    "zh": {
        ONLY_YOU: ("{who}在{day}想看{what}。", "只有您能看。"),
        NO_KEY_TO_PART: ("{who}在{day}想看{what}。", "{who}没有那部分的钥匙。", "什么都没有显示。"),
        KEY_CLOSED: ("{who}在{day}想打开您的文件。", "那把钥匙已经关了，什么都没有显示。"),
        CANNOT_CHANGE: ("{who}在{day}想改{what}。", "只有您能同意。", "什么都没有改。"),
        NO_YES: ("{who}在{day}想保存{what}。", "Nura 没有听到新的同意。", "什么都没有改。"),
        NOT_AGREED: ("{who}在{day}想让人进来。", "您还没有同意。", "什么都没有改。"),
        WIDER: ("{who}在{day}想让人看更多。", "那要先问您。", "什么都没有改。"),
        DEFAULT: ("{day}有东西没有保存。", "您的病历文件什么都没有改。"),
    },
}
"""A reach that was refused, by the kind of refusal. Every arm is a whole sentence with a
subject, one idea per line, and says that nothing changed or nothing was shown."""

REFUSAL_FAMILY: Mapping[str, str] = {
    # A part the key does not open. Whether the second line is "Only you can" is decided
    # per line by `refusal_family`, from the part that was asked for.
    "OutOfScope": NO_KEY_TO_PART,
    "NotTheirsToRead": NO_KEY_TO_PART,
    "NotOnThisProfile": NO_KEY_TO_PART,
    "WidenedRead": NO_KEY_TO_PART,
    # A person the record once knew, whose key is closed.
    "NoKey": KEY_CLOSED,
    # A change only the owner, or the chief he named, may make.
    "NotTheirKeyToCut": CANNOT_CHANGE,
    "NotTheirsToChange": CANNOT_CHANGE,
    "NotTheirConsentToGive": CANNOT_CHANGE,
    "NotTheirConsentToWithdraw": CANNOT_CHANGE,
    "NotTheClaimant": CANNOT_CHANGE,
    "NotTheOwner": CANNOT_CHANGE,
    "NotTheDoer": CANNOT_CHANGE,
    "NotAChief": CANNOT_CHANGE,
    "ImmutableRow": CANNOT_CHANGE,
    # A yes that was missing, spent, old or for something else.
    "NotAConfirmerHere": NO_YES,
    "NotWhatWasConfirmed": NO_YES,
    "AlreadySpent": NO_YES,
    "ConfirmationExpired": NO_YES,
    # The patient had not agreed, or had stopped agreeing.
    "NoConsent": NOT_AGREED,
    "ConsentWithheld": NOT_AGREED,
    "ConsentRevoked": NOT_AGREED,
    "ConsentOutOfDate": NOT_AGREED,
    "NoHolderNamed": NOT_AGREED,
    # A key asked to open more than the words the patient read.
    "WouldWiden": WIDER,
}
"""Which arm each refusal Nura raises renders under. A name that is not here — a rule about
the shape of a request, a row that was not found, a name added tomorrow — renders under
`DEFAULT`, so `refused_because` never reaches him raw."""

OWNER_ONLY_SCOPES: frozenset[Scope] = frozenset({Scope.NOTES, Scope.MONEY})
"""The parts that are preset to nobody but a chief: asked for by anyone else, the answer is
"Only you can", the same as for a part marked "only me"."""


def language_of(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def what_words(target: str, scope: Scope, language: str) -> str:
    """His words for the thing touched: by table where the table has its own, else by the
    scope it was touched under; whose record it is when neither says."""
    words = TARGET_WORDS.get(language, TARGET_WORDS[DEFAULT_LANGUAGE])
    if target in words:
        return words[target]
    by_scope = SCOPE_WORDS.get(language, SCOPE_WORDS[DEFAULT_LANGUAGE])
    if scope in by_scope:
        return by_scope[scope]
    return words["profile"]


def refusal_family(refused_because: str | None, scope: Scope, *, only_me: frozenset[Scope]) -> str:
    """Which arm a refusal renders under. A part that is the owner's alone — marked "only
    me", or preset to nobody but a chief — answers "Only you can"."""
    family = REFUSAL_FAMILY.get(refused_because or "", DEFAULT)
    if family == NO_KEY_TO_PART and (scope in only_me or scope in OWNER_ONLY_SCOPES):
        return ONLY_YOU
    return family


def allowed_lines(
    action: Action, language: str, *, who: str, what: str, day: str, other: str
) -> list[str]:
    template = ALLOWED.get(language, ALLOWED[DEFAULT_LANGUAGE])[action]
    return [template.format(who=who, what=what, day=day, other=other)]


def refused_lines(family: str, language: str, *, who: str, what: str, day: str) -> list[str]:
    arms = REFUSED.get(language, REFUSED[DEFAULT_LANGUAGE])
    return [line.format(who=who, what=what, day=day) for line in arms.get(family, arms[DEFAULT])]


def catalogue() -> list[str]:
    """Every template in this file, in every language, for the plain-words check."""
    found: list[str] = []
    for by_action in ALLOWED.values():
        found.extend(by_action.values())
    for arms in REFUSED.values():
        for lines in arms.values():
            found.extend(lines)
    return found
