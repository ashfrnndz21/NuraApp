"""The strings catalogue for the Health tab and Connect's upcoming call: the ring, the metric
rows, the insight cards, the food log and the call join line.

Every line here is in English, Malay and Chinese (`docs/plain-words.md`), tagged `@patient`
so `make plain-words` and `make language` hold them to the same standard as every other
patient string, and filed under the same key in each language so the translation memory can
hold the three to one another (`app.language.memory`). A line with `_THEIRS` beside it is the
same line in the caregiver's voice — third person, naming him — for the screens a caregiver
reads (docs/00-MASTER-BUILD-SPEC.md: "a caregiver's screen never speaks in the patient's
voice"). The Malay and Chinese here are plain, direct translations; like every other new
translation in this repo they want a native reviewer's pass before they ship to a real family
(the reference-ranges fixture carries the same note: "needs a clinician's sign-off").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

Lines = Sequence[str]


def _in(language: str | None) -> str:
    return language if language in LANGUAGES else DEFAULT_LANGUAGE


# --- the ring (Home > Health > Health Overview) --------------------------------------------

# @patient headline
RING_LABEL: Mapping[str, str] = {
    "en": "Tablets taken this week",
    "ms": "Ubat yang diambil minggu ini",
    "zh": "本周已服用的药",
}

# @patient headline
RING_LABEL_THEIRS: Mapping[str, str] = {
    "en": "{patient}'s tablets taken this week",
    "ms": "Ubat {patient} yang diambil minggu ini",
    "zh": "{patient}本周已服用的药",
}

# @patient phrase
RING_OF: Mapping[str, str] = {"en": "of {total}", "ms": "daripada {total}", "zh": "共{total}次"}


def ring_words(taken: int, total: int, *, language: str | None, theirs: bool = False) -> str:
    """"12 of 14" (or its Malay and Chinese words), a plain count, never a percentage or a
    grade — the ring shows a real number he can check against what he did, never a score."""
    lang = _in(language)
    if lang == "zh":
        return f"{taken}次，共{total}次"
    of_ = RING_OF[lang].format(total=total)
    return f"{taken} {of_}"


def ring_label(language: str | None, *, theirs: bool = False, patient: str = "") -> str:
    lang = _in(language)
    table = RING_LABEL_THEIRS if theirs else RING_LABEL
    return table[lang].format(patient=patient)


# --- metric rows (steps, heart rate, sleep, water) ------------------------------------------

# @patient headline
METRIC_LABEL: Mapping[str, Mapping[str, str]] = {
    "en": {"steps": "Steps", "heart_rate": "Heart rate", "sleep": "Sleep", "water": "Water"},
    "ms": {"steps": "Langkah", "heart_rate": "Kadar jantung", "sleep": "Tidur", "water": "Air"},
    "zh": {"steps": "步数", "heart_rate": "心率", "sleep": "睡眠", "water": "喝水"},
}

# @patient phrase
METRIC_NOT_LOGGED: Mapping[str, str] = {
    "en": "Not written down yet",
    "ms": "Belum dicatat",
    "zh": "还没有记录",
}

# @patient phrase
METRIC_NOT_LOGGED_THEIRS: Mapping[str, str] = {
    "en": "{patient} has not written this down yet",
    "ms": "{patient} belum mencatat ini",
    "zh": "{patient}还没有记录这个",
}

# @patient phrase
METRIC_SKIPPED: Mapping[str, str] = {
    "en": "None today",
    "ms": "Tiada hari ini",
    "zh": "今天没有",
}
"""What a metric row says when the day's own word on it is "none" — a real answer, not a
blank (docs/recommendation-engine.md, the absence rule)."""

# @patient phrase
METRIC_SKIPPED_THEIRS: Mapping[str, str] = {
    "en": "{patient} said none today",
    "ms": "{patient} kata tiada hari ini",
    "zh": "{patient}今天说没有",
}

# @patient phrase
NO_USUAL_RANGE: Mapping[str, str] = {
    "en": "No usual range for this yet",
    "ms": "Belum ada julat biasa untuk ini",
    "zh": "暂时还没有这个的正常范围",
}
"""What a heart-rate row says instead of a pill, honestly, until a clinician-reviewed range
exists for it (`app.reasoning.ranges` has none today) — never an invented "normal" band."""


def metric_label(kind: str, language: str | None) -> str:
    return METRIC_LABEL[_in(language)][kind]


def metric_status_words(
    status: str, *, language: str | None, theirs: bool = False, patient: str = ""
) -> str:
    """The row's own words for its status, when there is no number to show: "Not logged
    yet" or "None today" — never the same phrase for two different states (a status a
    reader downstream, human or engine, must be able to tell apart, docs/recommendation-
    engine.md)."""
    lang = _in(language)
    if status == "skipped":
        table = METRIC_SKIPPED_THEIRS if theirs else METRIC_SKIPPED
        return table[lang].format(patient=patient)
    table = METRIC_NOT_LOGGED_THEIRS if theirs else METRIC_NOT_LOGGED
    return table[lang].format(patient=patient)


def metric_value_words(value: float, unit: str, language: str | None) -> str:
    """"4,230 steps", "72 bpm", "6h 45m", "5 cups" — digits, small and few, his own unit."""
    lang = _in(language)
    shown = int(value) if float(value).is_integer() else round(value, 1)
    if unit == "min":
        hours, minutes = divmod(int(value), 60)
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
    if unit == "/min":
        word = {"en": "bpm", "ms": "degupan seminit", "zh": "次/分钟"}[lang]
        return f"{shown} {word}"
    if unit == "steps":
        word = {"en": "steps", "ms": "langkah", "zh": "步"}[lang]
        return f"{shown:,} {word}" if lang == "en" else f"{shown} {word}"
    if unit == "cups":
        word = {"en": "cups", "ms": "cawan", "zh": "杯"}[lang]
        return f"{shown} {word}"
    return f"{shown} {unit}"


# --- Health Insights -------------------------------------------------------------------------

# @patient
INSIGHT_DOSES_STEADY: Mapping[str, Lines] = {
    "en": ("You have taken every tablet on time this week.", "Nura is not worried about you."),
    "ms": ("Anda sudah ambil setiap ubat tepat pada masanya minggu ini.", "Nura tidak risau tentang anda."),
    "zh": ("这个星期您每次都准时吃药。", "Nura不担心您。"),
}

# @patient
INSIGHT_DOSES_STEADY_THEIRS: Mapping[str, Lines] = {
    "en": ("{patient} has taken every tablet on time this week.",),
    "ms": ("{patient} sudah ambil setiap ubat tepat pada masanya minggu ini.",),
    "zh": ("{patient}这个星期每次都准时吃药。",),
}

# @patient
INSIGHT_DOSES_SOME_LATE: Mapping[str, Lines] = {
    "en": ("You have taken {taken} of {total} tablets this week.", "One tablet was late."),
    "ms": ("Anda sudah ambil {taken} daripada {total} ubat minggu ini.", "Satu ubat lewat diambil."),
    "zh": ("这个星期您吃了{total}次中的{taken}次药。", "有一次吃晚了。"),
}

# @patient
INSIGHT_DOSES_SOME_LATE_THEIRS: Mapping[str, Lines] = {
    "en": ("{patient} has taken {taken} of {total} tablets this week.",),
    "ms": ("{patient} sudah ambil {taken} daripada {total} ubat minggu ini.",),
    "zh": ("{patient}这个星期吃了{total}次中的{taken}次药。",),
}

# @patient
INSIGHT_CHECKED_IN: Mapping[str, Lines] = {
    "en": ("You checked in {days} days this week.", "Nura is glad to hear from you."),
    "ms": ("Anda sudah daftar masuk {days} hari minggu ini.", "Nura gembira mendengar khabar anda."),
    "zh": ("这个星期您有{days}天报到。", "Nura很高兴收到您的消息。"),
}

# @patient
INSIGHT_CHECKED_IN_THEIRS: Mapping[str, Lines] = {
    "en": ("{patient} checked in {days} days this week.",),
    "ms": ("{patient} sudah daftar masuk {days} hari minggu ini.",),
    "zh": ("{patient}这个星期有{days}天报到。",),
}

# @patient
INSIGHT_ACTIVE: Mapping[str, Lines] = {
    "en": ("Great job staying active!", "You wrote down {value} steps today."),
    "ms": ("Syabas, anda aktif hari ini!", "Anda catat {value} langkah hari ini."),
    "zh": ("做得好，今天很活跃！", "您今天记录了{value}步。"),
}

# @patient
INSIGHT_ACTIVE_THEIRS: Mapping[str, Lines] = {
    "en": ("{patient} stayed active today.", "{patient} wrote down {value} steps today."),
    "ms": ("{patient} aktif hari ini.", "{patient} catat {value} langkah hari ini."),
    "zh": ("{patient}今天很活跃。", "{patient}今天记录了{value}步。"),
}

# @patient
INSIGHT_WATER: Mapping[str, Lines] = {
    "en": ("You wrote down {value} cups of water today.", "Water is OK."),
    "ms": ("Anda catat {value} cawan air hari ini.", "Air kosong boleh."),
    "zh": ("您今天记录了喝{value}杯水。", "喝水没问题。"),
}

# @patient
INSIGHT_WATER_THEIRS: Mapping[str, Lines] = {
    "en": ("{patient} wrote down {value} cups of water today.",),
    "ms": ("{patient} catat {value} cawan air hari ini.",),
    "zh": ("{patient}今天记录了喝{value}杯水。",),
}


def _fmt(lines: Lines, **slots: object) -> tuple[str, ...]:
    return tuple(line.format(**slots) for line in lines)


def doses_insight(
    taken: int, total: int, *, language: str | None, theirs: bool = False, patient: str = ""
) -> tuple[str, str]:
    """A headline and a detail line, both true statements about the week's doses — never a
    speculation, never advice."""
    lang = _in(language)
    if total == 0:
        return "", ""
    if taken >= total:
        table = INSIGHT_DOSES_STEADY_THEIRS if theirs else INSIGHT_DOSES_STEADY
        lines = _fmt(table[lang], patient=patient)
    else:
        table = INSIGHT_DOSES_SOME_LATE_THEIRS if theirs else INSIGHT_DOSES_SOME_LATE
        lines = _fmt(table[lang], taken=taken, total=total, patient=patient)
    headline, *rest = lines
    return headline, rest[0] if rest else ""


def checked_in_insight(
    days: int, *, language: str | None, theirs: bool = False, patient: str = ""
) -> tuple[str, str]:
    lang = _in(language)
    table = INSIGHT_CHECKED_IN_THEIRS if theirs else INSIGHT_CHECKED_IN
    lines = _fmt(table[lang], days=days, patient=patient)
    headline, *rest = lines
    return headline, rest[0] if rest else ""


def active_insight(
    steps: float, *, language: str | None, theirs: bool = False, patient: str = ""
) -> tuple[str, str]:
    lang = _in(language)
    table = INSIGHT_ACTIVE_THEIRS if theirs else INSIGHT_ACTIVE
    shown = int(steps) if float(steps).is_integer() else steps
    lines = _fmt(table[lang], value=f"{shown:,}" if lang == "en" else str(shown), patient=patient)
    headline, *rest = lines
    return headline, rest[0] if rest else ""


def water_insight(
    cups: float, *, language: str | None, theirs: bool = False, patient: str = ""
) -> tuple[str, str]:
    lang = _in(language)
    table = INSIGHT_WATER_THEIRS if theirs else INSIGHT_WATER
    shown = int(cups) if float(cups).is_integer() else cups
    lines = _fmt(table[lang], value=str(shown), patient=patient)
    headline, *rest = lines
    return headline, rest[0] if rest else ""


# --- food intake (E: lifestyle) --------------------------------------------------------------

# @patient headline
MEAL_LABEL: Mapping[str, Mapping[str, str]] = {
    "en": {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"},
    "ms": {"breakfast": "Sarapan", "lunch": "Makan tengah hari", "dinner": "Makan malam", "snack": "Snek"},
    "zh": {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "点心"},
}


def meal_label(meal: str, language: str | None) -> str:
    return MEAL_LABEL[_in(language)].get(meal, meal)


# @patient phrase
FOOD_CATALOG: Mapping[str, Mapping[str, str]] = {
    "en": {
        "rice": "Rice",
        "nasi_lemak": "Nasi lemak",
        "chicken_rice": "Chicken rice",
        "noodles": "Noodles",
        "bread": "Bread",
        "porridge": "Porridge",
        "roti_canai": "Roti canai",
        "laksa": "Laksa",
        "fish": "Fish",
        "vegetables": "Vegetables",
        "fruit": "Fruit",
        "soup": "Soup",
        "tea": "Tea",
        "coffee": "Coffee",
        "milo": "Milo",
    },
    "ms": {
        "rice": "Nasi",
        "nasi_lemak": "Nasi lemak",
        "chicken_rice": "Nasi ayam",
        "noodles": "Mi",
        "bread": "Roti",
        "porridge": "Bubur",
        "roti_canai": "Roti canai",
        "laksa": "Laksa",
        "fish": "Ikan",
        "vegetables": "Sayur",
        "fruit": "Buah",
        "soup": "Sup",
        "tea": "Teh",
        "coffee": "Kopi",
        "milo": "Milo",
    },
    "zh": {
        "rice": "白饭",
        "nasi_lemak": "椰浆饭",
        "chicken_rice": "海南鸡饭",
        "noodles": "面条",
        "bread": "面包",
        "porridge": "粥",
        "roti_canai": "印度煎饼",
        "laksa": "叻沙",
        "fish": "鱼",
        "vegetables": "蔬菜",
        "fruit": "水果",
        "soup": "汤",
        "tea": "茶",
        "coffee": "咖啡",
        "milo": "美禄",
    },
}
"""Common foods in Singapore and Malaysia, for a tap instead of typing. Free entry is always
open beside it: `app.lifestyle.food.log_food` takes a catalogue id or his own words, never
both required. No calories, no grams — that is not how he thinks about a meal."""

CATALOG_IDS = frozenset(FOOD_CATALOG["en"])


def food_catalog(language: str | None) -> Mapping[str, str]:
    return FOOD_CATALOG[_in(language)]


# --- Connect: Upcoming Call --------------------------------------------------------------

# @patient headline
CALL_JOIN: Mapping[str, str] = {"en": "Join", "ms": "Sertai", "zh": "加入"}

# @patient action
CALL_RING: Mapping[str, str] = {
    "en": "Nura will ring {who} for you.",
    "ms": "Nura akan telefon {who} untuk anda.",
    "zh": "Nura会帮您打电话给{who}。",
}

# @patient action
CALL_OPEN_LINK: Mapping[str, str] = {
    "en": "Nura will open the call {who} sent.",
    "ms": "Nura akan buka panggilan yang dihantar oleh {who}.",
    "zh": "Nura会打开{who}发来的通话链接。",
}


def call_join_words(who: str, has_link: bool, language: str | None) -> str:
    lang = _in(language)
    table = CALL_OPEN_LINK if has_link else CALL_RING
    return table[lang].format(who=who)


__all__ = [
    "CALL_JOIN",
    "CATALOG_IDS",
    "FOOD_CATALOG",
    "LANGUAGES",
    "MEAL_LABEL",
    "NO_USUAL_RANGE",
    "RING_LABEL",
    "active_insight",
    "call_join_words",
    "checked_in_insight",
    "doses_insight",
    "food_catalog",
    "meal_label",
    "metric_label",
    "metric_status_words",
    "metric_value_words",
    "ring_label",
    "ring_words",
    "water_insight",
]
