"""Every line a smart nudge says, in his three languages, tagged for `make plain-words`.

Whole lines, filled and never assembled: `{doctor}` the doctor's name, `{day}` "Monday 14
September", `{count}` a digit, `{name}` someone in his family, `{feeling}` his word for how he
feels (`app.delivery.strings.FEELINGS`, the feed's own phrases). A commitment's middle line is
his own words from the memo, quoted as they are and verified where the memo was written.

No line scolds, counts what was not done, or names a target (docs/smart-nudges.md §4). The
recognition lines are the same words the Me page says (`RECOGNITION` is shared), and "This
number only goes up." is the reassurance docs/plain-words.md rule 9 names.
"""

from __future__ import annotations

from collections.abc import Mapping

# @patient
LINES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "en": {
        "anticipation": ("You see {doctor} tomorrow, {day}.",),
        "anticipation_book": ("Please bring your blood pressure book.",),
        "anticipation_tablets": ("Please bring all your tablets.",),
        "recognition": (
            "Nura counts {count} days with your tablets taken.",
            "This number only goes up.",
        ),
        "recognition_one": (
            "Nura counts 1 day with your tablets taken.",
            "This number only goes up.",
        ),
        "recognition_none": (
            "Nura counts the days with your tablets taken.",
            "This number only goes up.",
        ),
        "pattern_every": (
            "You took your morning tablets every day this week.",
            "That is a good week.",
        ),
        "pattern_some": (
            "You took your morning tablets on {count} days this week.",
            "That is a good week.",
        ),
        "check_in": ("How are you feeling today?",),
        "check_in_watched": ("You told Nura about {feeling} last week.",),
        "commitment_said": ("You said you would do this:",),
        "commitment_ask": ("How did it go today?",),
        "presence_family": ("{name} wrote in the family messages today.",),
        "presence_here": ("Nura is here if you need it.",),
    },
    "ms": {
        "anticipation": ("Anda berjumpa {doctor} esok, {day}.",),
        "anticipation_book": ("Sila bawa buku tekanan darah anda.",),
        "anticipation_tablets": ("Sila bawa semua ubat anda.",),
        "recognition": (
            "Nura mengira {count} hari ubat anda sudah diambil.",
            "Nombor ini hanya naik.",
        ),
        "recognition_one": (
            "Nura mengira 1 hari ubat anda sudah diambil.",
            "Nombor ini hanya naik.",
        ),
        "recognition_none": (
            "Nura mengira hari-hari ubat anda sudah diambil.",
            "Nombor ini hanya naik.",
        ),
        "pattern_every": (
            "Ubat pagi anda sudah diambil setiap hari minggu ini.",
            "Ini minggu yang baik.",
        ),
        "pattern_some": (
            "Ubat pagi anda sudah diambil pada {count} hari minggu ini.",
            "Ini minggu yang baik.",
        ),
        "check_in": ("Apa rasa anda hari ini?",),
        "check_in_watched": ("Anda beritahu Nura tentang {feeling} minggu lepas.",),
        "commitment_said": ("Anda kata anda akan buat ini:",),
        "commitment_ask": ("Bagaimana hari ini?",),
        "presence_family": ("{name} menulis dalam mesej keluarga hari ini.",),
        "presence_here": ("Nura ada di sini jika anda perlukan.",),
    },
    "zh": {
        "anticipation": ("您明天{day}看{doctor}。",),
        "anticipation_book": ("请带上您的血压本子。",),
        "anticipation_tablets": ("请带上您所有的药。",),
        "recognition": ("按时服药的日子，Nura 已经数到{count}天。", "这个数字只会往上走。"),
        "recognition_one": ("按时服药的日子，Nura 已经数到1天。", "这个数字只会往上走。"),
        "recognition_none": ("Nura 会数您按时服药的日子。", "这个数字只会往上走。"),
        "pattern_every": ("这个星期您每天早上都按时服药。", "这是很好的一个星期。"),
        "pattern_some": ("这个星期，您早上按时服药{count}天。", "这是很好的一个星期。"),
        "check_in": ("您今天感觉怎么样？",),
        "check_in_watched": ("上个星期您告诉 Nura 您{feeling}。",),
        "commitment_said": ("您说过要做这件事：",),
        "commitment_ask": ("今天怎么样？",),
        "presence_family": ("{name}今天在家人群里留言了。",),
        "presence_here": ("需要的时候，Nura 就在这里。",),
    },
}

# @patient
WHY: Mapping[str, Mapping[str, str]] = {
    "en": {
        "anticipation": "You see this because your visit is tomorrow.",
        "recognition": "You see this because the number went up.",
        "pattern": "You see this because of your morning tablets this week.",
        "check_in": "You see this because something changed this week.",
        "check_in_watched": "You see this because you told Nura last week.",
        "commitment": "You see this because you said you would do it.",
        "presence_family": "You see this because {name} wrote today.",
        "presence_here": "You see this because it has been a quiet week.",
    },
    "ms": {
        "anticipation": "Anda nampak ini kerana lawatan anda esok.",
        "recognition": "Anda nampak ini kerana nombor itu naik.",
        "pattern": "Anda nampak ini kerana ubat pagi anda minggu ini.",
        "check_in": "Anda nampak ini kerana ada perubahan minggu ini.",
        "check_in_watched": "Anda nampak ini kerana anda beritahu Nura minggu lepas.",
        "commitment": "Anda nampak ini kerana anda kata anda akan buat.",
        "presence_family": "Anda nampak ini kerana {name} menulis hari ini.",
        "presence_here": "Anda nampak ini kerana minggu ini tenang.",
    },
    "zh": {
        "anticipation": "您看到这个，是因为您明天要看医生。",
        "recognition": "您看到这个，是因为这个数字往上走了。",
        "pattern": "您看到这个，是因为这个星期您早上都按时服药。",
        "check_in": "您看到这个，是因为这个星期有变化。",
        "check_in_watched": "您看到这个，是因为上个星期您告诉了 Nura。",
        "commitment": "您看到这个，是因为您说过要这样做。",
        "presence_family": "您看到这个，是因为{name}今天留言了。",
        "presence_here": "您看到这个，是因为这个星期很平静。",
    },
}
"""Why he is seeing this: every nudge carries one (docs/smart-nudges.md §1)."""

# @patient phrase
ACTIONS: Mapping[str, Mapping[str, str]] = {
    "en": {"accept": "OK", "commitment_accept": "It went well", "dismiss": "Not today"},
    "ms": {"accept": "OK", "commitment_accept": "Semuanya baik", "dismiss": "Bukan hari ini"},
    "zh": {"accept": "好的", "commitment_accept": "很顺利", "dismiss": "今天不要"},
}
"""The one action a nudge offers, and "Not today" beside it: a visible button, never a swipe."""


def recognition_lines(count: int, language: str) -> tuple[str, ...]:
    """The number that only goes up, in his words: the recognition nudge and the Me page."""
    table = LINES[language]
    if count <= 0:
        return table["recognition_none"]
    if count == 1:
        return table["recognition_one"]
    return tuple(line.format(count=count) for line in table["recognition"])


def catalogue() -> list[tuple[str, str]]:
    """Every template here as (language, line), for the tests that hold them to the rules."""
    found: list[tuple[str, str]] = []
    for code, groups in LINES.items():
        found.extend((code, line) for lines in groups.values() for line in lines)
        found.extend((code, line) for line in WHY[code].values())
    return found
