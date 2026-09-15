"""The family strings (E12): the roles and the helper list in his words, the digest a
caregiver reads, and the messages a chief can send him.

Every line is a template in English, Malay and Chinese, tagged `@patient` and checked by
`make plain-words`. Slots are filled at run time with names, dates and numbers only —
never with a class name, an id or a sentence assembled from pieces. The parts of the record
are named by `app.consent.texts.SCOPE_WORDS`, the same words the consent used, so what the
family screen says a key opens is what the patient read when he agreed to it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.keys.scopes import KeyRole, KeyWindow, Scope

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

Lines = Sequence[str]


def language_of(asked: str | None) -> str:
    """One of ours, or English."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


# --- roles and the helper list -------------------------------------------------------------

# @patient phrase
ROLE_WORDS: Mapping[str, Mapping[KeyRole, str]] = {
    "en": {
        KeyRole.CHIEF: "the person who runs your care",
        KeyRole.CAREGIVER: "a family member who helps",
        KeyRole.VIEWER: "someone who only looks",
        KeyRole.HELPER: "your helper",
        KeyRole.EMERGENCY: "someone to call in an emergency",
        KeyRole.CLINIC: "your doctor's clinic",
    },
    "ms": {
        KeyRole.CHIEF: "orang yang mengurus penjagaan anda",
        KeyRole.CAREGIVER: "ahli keluarga yang membantu",
        KeyRole.VIEWER: "orang yang hanya melihat",
        KeyRole.HELPER: "pembantu anda",
        KeyRole.EMERGENCY: "orang untuk dihubungi dalam kecemasan",
        KeyRole.CLINIC: "klinik",
    },
    "zh": {
        KeyRole.CHIEF: "照顾您的主要家人",
        KeyRole.CAREGIVER: "帮忙的家人",
        KeyRole.VIEWER: "只看不改的人",
        KeyRole.HELPER: "您的帮佣",
        KeyRole.EMERGENCY: "紧急时要找的人",
        KeyRole.CLINIC: "诊所",
    },
}
"""Who each role is to him, in his words."""

# @patient
ROLE_IS: Mapping[str, str] = {
    "en": "{name} is {role}.",
    "ms": "{name} ialah {role}.",
    "zh": "{name}是{role}。",
}

# @patient
CAN_SEE: Mapping[str, str] = {
    "en": "{name} can see these parts:",
    "ms": "{name} boleh melihat bahagian ini:",
    "zh": "{name}可以看这些：",
}

# @patient
WINDOW_LINES: Mapping[str, Mapping[KeyWindow, str]] = {
    "en": {
        KeyWindow.ALWAYS: "{name} can see them until you say stop.",
        KeyWindow.THIRTY_DAYS: "{name} can see them for 30 days.",
        KeyWindow.SEVENTY_TWO_HOURS: "{name} can see them for 3 days.",
        KeyWindow.ONE_DAY: "{name} can see them for 1 day.",
    },
    "ms": {
        KeyWindow.ALWAYS: "{name} boleh melihatnya sehingga anda minta ia dihentikan.",
        KeyWindow.THIRTY_DAYS: "{name} boleh melihatnya selama 30 hari.",
        KeyWindow.SEVENTY_TWO_HOURS: "{name} boleh melihatnya selama 3 hari.",
        KeyWindow.ONE_DAY: "{name} boleh melihatnya selama 1 hari.",
    },
    "zh": {
        KeyWindow.ALWAYS: "{name}可以一直看，直到您说停。",
        KeyWindow.THIRTY_DAYS: "{name}可以看 30 天。",
        KeyWindow.SEVENTY_TWO_HOURS: "{name}可以看 3 天。",
        KeyWindow.ONE_DAY: "{name}可以看 1 天。",
    },
}
"""How long a key runs, in his words, by the window it was cut for."""

# @patient
UNTIL_DAY: Mapping[str, str] = {
    "en": "{name} can see them until {day}.",
    "ms": "{name} boleh melihatnya sehingga {day}.",
    "zh": "{name}可以看到{day}为止。",
}
"""A key with an end that is not one of the preset windows: it was shortened."""

# @patient
HELPER_CAN: Mapping[str, Mapping[Scope, str]] = {
    "en": {
        Scope.MEDICINES: "{name} can see your medicines and tap Taken for you.",
        Scope.EMERGENCY: "{name} can see your emergency card.",
        Scope.SEND: "{name} gets the list from Nura every morning.",
        Scope.READINGS: "{name} can see your blood pressure book.",
        Scope.VISITS: "{name} can see your visits to the doctor.",
        Scope.RECORDS: "{name} can see your papers.",
    },
    "ms": {
        Scope.MEDICINES: "{name} boleh melihat ubat anda dan tekan Sudah ambil untuk anda.",
        Scope.EMERGENCY: "{name} boleh melihat kad kecemasan anda.",
        Scope.SEND: "{name} dapat senarai daripada Nura setiap pagi.",
        Scope.READINGS: "{name} boleh melihat buku tekanan darah anda.",
        Scope.VISITS: "{name} boleh melihat lawatan anda ke doktor.",
        Scope.RECORDS: "{name} boleh melihat surat-surat anda.",
    },
    "zh": {
        Scope.MEDICINES: "{name}可以看您的药，也可以替您按吃了。",
        Scope.EMERGENCY: "{name}可以看您的紧急卡。",
        Scope.SEND: "{name}每天早上收到 Nura 的清单。",
        Scope.READINGS: "{name}可以看您的血压本。",
        Scope.VISITS: "{name}可以看您看医生的记录。",
        Scope.RECORDS: "{name}可以看您的病历文件。",
    },
}
"""What a helper may do, one line per part her key opens. A part not here is not something
a helper is ever cut a key to; it is left out rather than named."""

# @patient
NO_HELPER: Mapping[str, str] = {
    "en": "Nobody holds a helper key to your papers yet.",
    "ms": "Belum ada siapa memegang kunci pembantu untuk surat-surat anda.",
    "zh": "还没有人拿着您文件的帮佣钥匙。",
}

# --- the digest ----------------------------------------------------------------------------

# @patient headline
DIGEST_HEAD: Mapping[str, str] = {
    "en": "{name} on {day}.",
    "ms": "{name} pada {day}.",
    "zh": "{name}，{day}。",
}

# @patient
DIGEST: Mapping[str, Mapping[str, str]] = {
    "en": {
        "message": "{who} wrote on {day}:",
        "reading": "{who} wrote down {name}'s blood pressure on {day}.",
        "reading_value": "It was {top_number} over {bottom_number}.",
        "taken": "{who} tapped Taken for {name} on {day}.",
        "visit": "{name} sees the doctor on {day}.",
        "task_done": "{who} finished this on {day}: {what}.",
        "task_open": "{who} will do this: {what}.",
        "order_done": "{who} ordered more medicine for {name} on {day}.",
        "order_open": "{who} will order more medicine for {name}.",
        "on_duty": "{who} is on duty today.",
        "nobody_on_duty": "Nobody is on duty today.",
        "quiet": "There is nothing new since {day}.",
    },
    "ms": {
        "message": "{who} menulis pada {day}:",
        "reading": "{who} mencatat tekanan darah {name} pada {day}.",
        "reading_value": "Bacaannya {top_number} atas {bottom_number}.",
        "taken": "{who} tekan Sudah ambil untuk {name} pada {day}.",
        "visit": "{name} berjumpa doktor pada {day}.",
        "task_done": "{who} sudah selesai pada {day}: {what}.",
        "task_open": "{who} akan buat ini: {what}.",
        "order_done": "{who} sudah pesan lagi ubat untuk {name} pada {day}.",
        "order_open": "{who} akan pesan lagi ubat untuk {name}.",
        "on_duty": "{who} bertugas hari ini.",
        "nobody_on_duty": "Tiada siapa bertugas hari ini.",
        "quiet": "Tiada apa yang baru sejak {day}.",
    },
    "zh": {
        "message": "{who}在{day}写道：",
        "reading": "{who}在{day}记下了{name}的血压。",
        "reading_value": "是{top_number}比{bottom_number}。",
        "taken": "{who}在{day}替{name}按了吃了。",
        "visit": "{name}在{day}看医生。",
        "task_done": "{who}在{day}做完了：{what}。",
        "task_open": "{who}会做这件事：{what}。",
        "order_done": "{who}在{day}为{name}再订了药。",
        "order_open": "{who}会为{name}再订药。",
        "on_duty": "今天{who}值班。",
        "nobody_on_duty": "今天没有人值班。",
        "quiet": "从{day}起没有新的事。",
    },
}
"""The day's cards and messages for a caregiver, one whole sentence each. The message
itself follows its header line as the family wrote it: it is their own words to each
other, not a line Nura wrote."""

# --- the push composer --------------------------------------------------------------------

# @patient
PUSH_TEMPLATES: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "water_pill_morning": ("Nura says the water pill is at 8.", "Take it with breakfast."),
        "pickup": ("{who} will pick you up at {when}.", "Bring your blood pressure book."),
        "call_you": ("{who} will call you {when}.", "It is not a worry."),
        "drink_water": ("Drink a glass of water now.", "Water is OK."),
        "weigh_tomorrow": (
            "Tomorrow morning, stand on the scale before breakfast.",
            "{who} will read the number.",
        ),
        "see_doctor": ("You see {doctor} on {day}.", "{who} will take you."),
        "thinking_of_you": ("{who} is thinking of you today.", "Have a good rest."),
    },
    "ms": {
        "water_pill_morning": ("Nura kata pil air pada pukul 8.", "Ambil bersama sarapan."),
        "pickup": ("{who} akan ambil anda pada {when}.", "Bawa buku tekanan darah anda."),
        "call_you": ("{who} akan telefon anda {when}.", "Ini bukan satu kebimbangan."),
        "drink_water": ("Minum segelas air sekarang.", "Air kosong boleh."),
        "weigh_tomorrow": (
            "Esok pagi, naik penimbang sebelum sarapan.",
            "{who} akan baca nombornya.",
        ),
        "see_doctor": ("Anda berjumpa {doctor} pada {day}.", "{who} akan bawa anda."),
        "thinking_of_you": ("{who} teringat anda hari ini.", "Berehatlah dengan baik."),
    },
    "zh": {
        "water_pill_morning": ("Nura 说去水药是 8 点吃。", "和早餐一起吃。"),
        "pickup": ("{who}会在{when}来接您。", "带上您的血压本。"),
        "call_you": ("{who}{when}会打电话给您。", "不用担心。"),
        "drink_water": ("现在喝一杯水。", "喝水没问题。"),
        "weigh_tomorrow": ("明天早上，早餐前先站上体重秤。", "{who}会看那个数字。"),
        "see_doctor": ("您{day}看{doctor}。", "{who}会带您去。"),
        "thinking_of_you": ("{who}今天想着您。", "好好休息。"),
    },
}
"""What a chief can send him, by template id: whole lines, filled with the chief's name
(`{who}`), a time in words (`{when}`), the doctor's name (`{doctor}`) and a day (`{day}`).
Nothing here tells him to start, stop or change a medicine: the water-pill line says when
the tablet he already takes is due, as his list does."""

TEMPLATE_SLOTS: Mapping[str, frozenset[str]] = {
    "water_pill_morning": frozenset(),
    "pickup": frozenset({"who", "when"}),
    "call_you": frozenset({"who", "when"}),
    "drink_water": frozenset(),
    "weigh_tomorrow": frozenset({"who"}),
    "see_doctor": frozenset({"who", "doctor", "day"}),
    "thinking_of_you": frozenset({"who"}),
}
"""Which slots each template needs. A composer that leaves one empty is refused."""


def fill(lines: Lines, **values: str) -> list[str]:
    return [line.format(**values) for line in lines]


def catalogue() -> list[str]:
    """Every template in this file, in every language, for the plain-words check."""
    found: list[str] = []
    for by_language in (ROLE_IS, CAN_SEE, UNTIL_DAY, NO_HELPER, DIGEST_HEAD):
        found.extend(by_language.values())
    for table in (WINDOW_LINES, HELPER_CAN, DIGEST):
        for by_key in table.values():
            found.extend(by_key.values())
    for by_template in PUSH_TEMPLATES.values():
        for lines in by_template.values():
            found.extend(lines)
    return found
