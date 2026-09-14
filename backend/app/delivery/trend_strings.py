"""Every line the lab trend says (E09-01), in his three languages, tagged for `make plain-words`.

The trend is a pattern to discuss, never a finding (`.claude/rules/safety.md`). So the lines
say the number and the day, the range, where the number sits only when the range is the one
the lab printed on his paper, how it moved — and last, the boundary for `Surface.TREND`
(`app.safety.boundary`), which names the doctor to ask. No line
names a cause, a medicine or anything to do but ask. A word that places his number — above,
below, inside — is never said without the lab's range beside it: "the range on your blood
test" is how the lab's range is said in his words, because "lab" is not one of them
(docs/plain-words.md §2: labs are "your blood test"). A range from the guideline table is
"the usual range for your age", and nothing is said about where he sits against it.

Each template is a whole line with `{slots}`; `app.reasoning.trends` fills them and verifies
every filled line before it leaves (`app.safety.plain_words.verify`).
"""

from __future__ import annotations

from collections.abc import Mapping

# @patient phrase
NAMES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "total_cholesterol": "your cholesterol",
        "ldl": "your bad cholesterol",
        "hdl": "your good cholesterol",
        "triglycerides": "your blood fat",
        "hba1c": "your sugar test",
        "creatinine": "your kidney number",
        "egfr": "your kidney filter",
        "potassium": "your body salt",
        "haemoglobin": "your blood count",
        "tsh": "your thyroid test",
    },
    "ms": {
        "total_cholesterol": "kolesterol anda",
        "ldl": "kolesterol jahat anda",
        "hdl": "kolesterol baik anda",
        "triglycerides": "lemak darah anda",
        "hba1c": "ujian gula anda",
        "creatinine": "nombor buah pinggang anda",
        "egfr": "penapis buah pinggang anda",
        "potassium": "garam badan anda",
        "haemoglobin": "kiraan darah anda",
        "tsh": "ujian tiroid anda",
    },
    "zh": {
        "total_cholesterol": "您的胆固醇",
        "ldl": "您的坏胆固醇",
        "hdl": "您的好胆固醇",
        "triglycerides": "您的血脂",
        "hba1c": "您的糖化血检",
        "creatinine": "您的肾指数",
        "egfr": "您的肾过滤",
        "potassium": "您的钾",
        "haemoglobin": "您的血色素",
        "tsh": "您的甲状腺检查",
    },
}
"""His words for each analyte (docs/plain-words.md §2: "your kidney number", "your sugar
test", "a body salt"). The chemical name is never in a line."""

# @patient
VALUE: Mapping[str, tuple[str, ...]] = {
    "en": ("{name} was {value} on {day}.",),
    "ms": ("{name} ialah {value} pada {day}.",),
    "zh": ("{day}，您验了血。", "{name}是{value}。"),
}
"""The latest number and its day. Chinese says it in two lines: a date with its year is
three numbers already, and a line holds no more than three (rule 10)."""

# @patient
LAB_RANGE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "under": "The range on your blood test is under {upper}.",
        "or_more": "The range on your blood test is {lower} or more.",
        "between": "The range on your blood test is {lower} to {upper}.",
    },
    "ms": {
        "under": "Julat pada ujian darah anda ialah bawah {upper}.",
        "or_more": "Julat pada ujian darah anda ialah {lower} ke atas.",
        "between": "Julat pada ujian darah anda ialah {lower} hingga {upper}.",
    },
    "zh": {
        "under": "您验血单上的范围是{upper}以下。",
        "or_more": "您验血单上的范围是{lower}或以上。",
        "between": "您验血单上的范围是{lower}到{upper}。",
    },
}
"""The range the lab printed on his paper: "the lab's range", in his words."""

# @patient
USUAL_RANGE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "under": "The usual range for your age is under {upper}.",
        "or_more": "The usual range for your age is {lower} or more.",
        "between": "The usual range for your age is {lower} to {upper}.",
    },
    "ms": {
        "under": "Julat biasa untuk umur anda ialah bawah {upper}.",
        "or_more": "Julat biasa untuk umur anda ialah {lower} ke atas.",
        "between": "Julat biasa untuk umur anda ialah {lower} hingga {upper}.",
    },
    "zh": {
        "under": "您这个年龄的一般范围是{upper}以下。",
        "or_more": "您这个年龄的一般范围是{lower}或以上。",
        "between": "您这个年龄的一般范围是{lower}到{upper}。",
    },
}
"""The guideline range for his age band (and sex, when the record holds it), when the paper
named no lab whose range is on file. No line says where he sits against it."""

# @patient
WHERE_IT_SITS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "in": "It is inside the range on your blood test.",
        "above": "It is above the range on your blood test.",
        "below": "It is below the range on your blood test.",
    },
    "ms": {
        "in": "Ia dalam julat pada ujian darah anda.",
        "above": "Ia di atas julat pada ujian darah anda.",
        "below": "Ia di bawah julat pada ujian darah anda.",
    },
    "zh": {
        "in": "它在您验血单上的范围之内。",
        "above": "它高于您验血单上的范围。",
        "below": "它低于您验血单上的范围。",
    },
}
"""Said only beside the lab's own range. Never "high", "normal", "bad": a place, not a verdict."""

# @patient
DIRECTION: Mapping[str, Mapping[str, str]] = {
    "en": {
        "up": "It has gone up since {day}.",
        "down": "It has gone down since {day}.",
        "steady": "It has stayed about the same since {day}.",
        "mixed": "It has gone up and down since {day}.",
    },
    "ms": {
        "up": "Ia telah naik sejak {day}.",
        "down": "Ia telah turun sejak {day}.",
        "steady": "Ia hampir sama sejak {day}.",
        "mixed": "Ia telah naik dan turun sejak {day}.",
    },
    "zh": {
        "up": "从{day}起，它上升了。",
        "down": "从{day}起，它下降了。",
        "steady": "从{day}起，它差不多一样。",
        "mixed": "从{day}起，它有升有降。",
    },
}
"""How it moved over the last three results, from the first of them: arithmetic only."""

# @patient
NOTHING_YET: Mapping[str, str] = {
    "en": "Your papers do not show {name} yet.",
    "ms": "Surat-surat anda belum menunjukkan {name}.",
    "zh": "您的文件里还没有{name}。",
}

LANGUAGES = ("en", "ms", "zh")

# Words that place a number against a range, by language. A line carrying one must carry
# the lab's range too (`LAB_RANGE_WORDS`); the tests hold every rendered line to that.
JUDGEMENT_WORDS: Mapping[str, tuple[str, ...]] = {
    "en": ("above", "below", "inside", "high", "low", "normal"),
    "ms": ("di atas", "di bawah", "dalam julat", "tinggi", "rendah", "normal"),
    "zh": ("高于", "低于", "之内", "偏高", "偏低", "正常"),
}
LAB_RANGE_WORDS: Mapping[str, str] = {
    "en": "the range on your blood test",
    "ms": "julat pada ujian darah anda",
    "zh": "您验血单上的范围",
}
