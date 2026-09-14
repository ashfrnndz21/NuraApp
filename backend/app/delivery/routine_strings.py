"""Every line of the day's routine he reads (E10-01), in his three languages.

The patient's routine is one line per moment of his day: when he wakes, at breakfast, at
lunch, at dinner, before bed — what to check and what to take, in his words, the same words
the dose card uses ("Take 1 tablet of your blood pressure tablet with breakfast."). Clock
times are not in these lines: his day hangs on its moments, not on the clock
(`app.medicines.dose.Anchor`); the one hour he hears is when his Today page comes. The
caregiver's table keeps the times and the codes and is not a patient string.

Each template is a whole line with `{slots}`; `app.routines.service` fills and verifies them.
"""

from __future__ import annotations

from collections.abc import Mapping

# @patient phrase
MOMENTS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "wake": "When you wake up",
        "breakfast": "At breakfast",
        "lunch": "At lunch",
        "dinner": "At dinner",
        "bed": "Before bed",
    },
    "ms": {
        "wake": "Apabila anda bangun",
        "breakfast": "Semasa sarapan",
        "lunch": "Semasa makan tengah hari",
        "dinner": "Semasa makan malam",
        "bed": "Sebelum tidur",
    },
    "zh": {"wake": "起床后", "breakfast": "早餐时", "lunch": "午餐时", "dinner": "晚餐时", "bed": "睡前"},
}

# @patient phrase
DOING: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood_pressure": "check your blood pressure",
        "blood_sugar": "check your blood sugar",
        "weight": "stand on the scale",
        "walk": "go for a walk",
    },
    "ms": {
        "blood_pressure": "periksa tekanan darah anda",
        "blood_sugar": "periksa gula darah anda",
        "weight": "berdiri di atas penimbang",
        "walk": "pergi berjalan kaki",
    },
    "zh": {"blood_pressure": "量血压", "blood_sugar": "验血糖", "weight": "站上秤", "walk": "去散步"},
}
"""What he is prompted to do at a moment: a reading, or a walk."""

# @patient phrase
ITEM: Mapping[str, str] = {"en": "{amount} of {name}", "ms": "{amount} {name}", "zh": "{amount}{name}"}
"""One medicine at a moment, the way the dose card says it."""

AND: Mapping[str, str] = {"en": " and ", "ms": " dan ", "zh": "和"}
COMMA: Mapping[str, str] = {"en": ", ", "ms": ", ", "zh": "、"}

# @patient
LINE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "take": "{moment}, take {tablets}.",
        "do": "{moment}, {doing}.",
        "both": "{moment}, {doing}, then take {tablets}.",
    },
    "ms": {
        "take": "{moment}, ambil {tablets}.",
        "do": "{moment}, {doing}.",
        "both": "{moment}, {doing}, kemudian ambil {tablets}.",
    },
    "zh": {
        "take": "{moment}，吃{tablets}。",
        "do": "{moment}，{doing}。",
        "both": "{moment}，先{doing}，再吃{tablets}。",
    },
}
"""One moment of his day. Two medicines at most on a line; a third starts a second line."""

# @patient action
MORNING_CARD: Mapping[str, str] = {
    "en": "Nura sends your Today page at {clock}.",
    "ms": "Nura hantar halaman Hari Ini anda {clock}.",
    "zh": "Nura {clock}发您的“今天”页面。",
}
"""When his Today page comes, and who sends it."""
