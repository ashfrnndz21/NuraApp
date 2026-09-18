"""Every line the Health Analyst's report says (`app.reasoning.analyst`), in his three
languages, tagged for `make plain-words` — this file, not `app.reasoning.analyst.port`, is
under the paths `.claude/rules/patient-strings.md` already checks (`backend/app/delivery/**`),
so the report's words are verified the same way every other patient string here is, without
touching that rules file.

Each template is a whole line with `{slots}`; `app.reasoning.analyst.rule` fills them, and
`app.reasoning.analyst.pipeline.finalize` verifies every filled line (plain words, then the
conclusion-or-advice blocklist) before it is shown. So every line here says what was found and
never what it means: no line names a cause, says "high" or "low", or tells him to stop, start
or change a medicine — the boundary `.claude/rules/safety.md` and the pipeline both hold to.
`why_plain` says only the mechanics of the comparison (age against a table, a list against
another list, amounts added up) — never a doctor's opinion, so it never needs the word
"diagnose" or "should" in any of the three languages, where a single character can trip the
blocklist's own scan (`app.reasoning.analyst.pipeline._CONCLUSION_WORDS["zh"]`).
"""

from __future__ import annotations

from collections.abc import Mapping

LANGUAGES = ("en", "ms", "zh")

# @patient headline
SECTION_TITLES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "what_changed": "What changed",
        "worth_a_look": "Worth a look",
        "medicines_and_supplements": "Medicines and supplements",
        "what_you_pay": "What you pay",
        "screenings_due": "Screenings due",
        "questions_for_the_doctor": "Questions for the doctor",
    },
    "ms": {
        "what_changed": "Apa yang berubah",
        "worth_a_look": "Patut dilihat",
        "medicines_and_supplements": "Ubat dan suplemen",
        "what_you_pay": "Apa yang anda bayar",
        "screenings_due": "Saringan yang perlu dibuat",
        "questions_for_the_doctor": "Soalan untuk doktor",
    },
    "zh": {
        "what_changed": "有什么变化",
        "worth_a_look": "值得留意",
        "medicines_and_supplements": "药物和补充品",
        "what_you_pay": "您付的钱",
        "screenings_due": "该做的检查",
        "questions_for_the_doctor": "给医生的问题",
    },
}
"""Whole words a person reads at the top of each part of the report, in the fixed order
`app.reasoning.analyst.port.SECTION_KEYS` names — the same table the previous builder wrote
into `port.py`, moved here so it sits under a path `make plain-words` already checks."""

# @patient phrase
BP_NAME: Mapping[str, Mapping[str, str]] = {
    "en": {"systolic": "your top blood pressure number",
           "diastolic": "your bottom blood pressure number"},
    "ms": {"systolic": "nombor atas tekanan darah anda",
           "diastolic": "nombor bawah tekanan darah anda"},
    "zh": {"systolic": "您血压的上压数字", "diastolic": "您血压的下压数字"},
}
"""His words for the two blood-pressure numbers (docs/plain-words.md: "your blood pressure
book" is the reading; this is which of its two numbers a trend insight is about)."""

# @patient
TREND_LINE: Mapping[str, str] = {
    "en": "{name} was outside the usual range on {day}.",
    "ms": "{name} berada di luar julat biasa pada {day}.",
    "zh": "{name}在{day}不在一般范围内。",
}
"""Filled with `BP_NAME` (below), whose own words already say "your top blood pressure
number" — the template itself carries no possessive, so its `_THEIRS` twin is the same text:
`app.channels.about_him.Reader.says` rewrites the possessive inside the filled `{name}` slot
itself (`app.delivery.strings.theirs`), never this template."""

# @patient
TREND_LINE_THEIRS: Mapping[str, str] = {
    "en": "{name} was outside the usual range on {day}.",
    "ms": "{name} berada di luar julat biasa pada {day}.",
    "zh": "{name}在{day}不在一般范围内。",
}

# @patient
TREND_WHY: Mapping[str, str] = {
    "en": "This is compared with the usual range for your age.",
    "ms": "Ini dibandingkan dengan julat biasa untuk umur anda.",
    "zh": "这是与您这个年龄的一般范围做比较。",
}

# @patient
TREND_WHY_THEIRS: Mapping[str, str] = {
    "en": "This is compared with the usual range for {patient}'s age.",
    "ms": "Ini dibandingkan dengan julat biasa untuk umur {patient}.",
    "zh": "这是与{patient}这个年龄的一般范围做比较。",
}

# @patient phrase
SCREENING_NAME: Mapping[str, Mapping[str, str]] = {
    "en": {
        "cholesterol_test": "your cholesterol test",
        "diabetes_screening": "your sugar test",
        "eye_check": "an eye check",
        "kidney_check": "your kidney test",
    },
    "ms": {
        "cholesterol_test": "ujian darah untuk kolesterol",
        "diabetes_screening": "ujian gula anda",
        "eye_check": "pemeriksaan mata",
        "kidney_check": "ujian buah pinggang anda",
    },
    "zh": {
        "cholesterol_test": "胆固醇验血",
        "diabetes_screening": "您的血糖检查",
        "eye_check": "眼睛检查",
        "kidney_check": "您的肾检查",
    },
}
"""His words for each screening in `app.reasoning.analyst.screenings.SCREENINGS`
(docs/plain-words.md §2: "your blood test", "your sugar test", "your kidney number")."""

# @patient
SCREENING_LINE: Mapping[str, str] = {
    "en": "{name} has not been written down yet.",
    "ms": "{name} belum ditulis lagi.",
    "zh": "还没有写下{name}的记录。",
}
"""Filled with `SCREENING_NAME` (above); its `_THEIRS` twin is the same text, the same
reasoning `TREND_LINE_THEIRS` carries — the possessive lives inside the filled `{name}` slot,
rewritten there, not in this template."""

# @patient
SCREENING_LINE_THEIRS: Mapping[str, str] = {
    "en": "{name} has not been written down yet.",
    "ms": "{name} belum ditulis lagi.",
    "zh": "还没有写下{name}的记录。",
}

# @patient
SCREENING_WHY: Mapping[str, str] = {
    "en": "This compares your age and what you have told Nura with a general guide.",
    "ms": "Ini membandingkan umur anda dengan panduan am.",
    "zh": "这是把您的年龄和一般指引做比较。",
}

# @patient
SCREENING_WHY_THEIRS: Mapping[str, str] = {
    "en": "This compares {patient}'s age and what has been told to Nura with a general guide.",
    "ms": "Ini membandingkan umur {patient} dengan panduan am.",
    "zh": "这是把{patient}的年龄和一般指引做比较。",
}

# @patient
DUPLICATE_LINE: Mapping[str, str] = {
    "en": "2 of your medicines are written down as {name}.",
    "ms": "2 daripada ubat anda ditulis sebagai {name}.",
    "zh": "记录里有2笔药，写的都是{name}。",
}
"""Named once, not twice: `app.medicines.strings.PLAIN_NAME` is a class-level word (rule 13,
"the same words every time"), so two lines in the same class already say the same name — a
line naming it twice reads as a repeat, not two different medicines."""

# @patient
DUPLICATE_LINE_THEIRS: Mapping[str, str] = {
    "en": "2 of {patient}'s medicines are written down as {name}.",
    "ms": "2 daripada ubat {patient} ditulis sebagai {name}.",
    "zh": "记录里有2笔{patient}的药，写的都是{name}。",
}

# @patient
DUPLICATE_WHY: Mapping[str, str] = {
    "en": "This compares the kind written down for each medicine on your list.",
    "ms": "Ini membandingkan jenis yang ditulis untuk setiap ubat dalam senarai anda.",
    "zh": "这是比较您药物清单上每种药的分类。",
}

# @patient
DUPLICATE_WHY_THEIRS: Mapping[str, str] = {
    "en": "This compares the kind written down for each medicine on {patient}'s list.",
    "ms": "Ini membandingkan jenis yang ditulis untuk setiap ubat dalam senarai {patient}.",
    "zh": "这是比较{patient}药物清单上每种药的分类。",
}

# @patient
SUPPLEMENT_LINE: Mapping[str, str] = {
    "en": "{name} is on your list, and no condition on file explains it.",
    "ms": "{name} ada dalam senarai anda, dan tiada keadaan direkodkan yang menerangkannya.",
    "zh": "{name}在您的清单上，但记录中的病况没有说明原因。",
}

# @patient
SUPPLEMENT_LINE_THEIRS: Mapping[str, str] = {
    "en": "{name} is on {patient}'s list, and no condition on file explains it.",
    "ms": "{name} ada dalam senarai {patient}, dan tiada keadaan direkodkan yang menerangkannya.",
    "zh": "{name}在{patient}的清单上，但记录中的病况没有说明原因。",
}

# @patient
SUPPLEMENT_WHY: Mapping[str, str] = {
    "en": "This compares your supplements with the conditions written down for you.",
    "ms": "Ini membandingkan suplemen anda dengan keadaan yang ditulis untuk anda.",
    "zh": "这是把您的补充品和记录中的病况做比较。",
}

# @patient
SUPPLEMENT_WHY_THEIRS: Mapping[str, str] = {
    "en": "This compares {patient}'s supplements with the conditions written down for {patient}.",
    "ms": "Ini membandingkan suplemen {patient} dengan keadaan yang ditulis untuk {patient}.",
    "zh": "这是把{patient}的补充品和记录中的病况做比较。",
}

# @patient
COST_LINE: Mapping[str, str] = {
    "en": "Most of what you paid this year, {amount}, was for {policy}.",
    "ms": "Kebanyakan bayaran anda tahun ini, {amount}, adalah untuk {policy}.",
    "zh": "您今年大部分的付款，{amount}，是给{policy}的。",
}

# @patient
COST_LINE_THEIRS: Mapping[str, str] = {
    "en": "Most of what {patient} paid this year, {amount}, was for {policy}.",
    "ms": "Kebanyakan bayaran {patient} tahun ini, {amount}, adalah untuk {policy}.",
    "zh": "{patient}今年大部分的付款，{amount}，是给{policy}的。",
}

# @patient
COST_WHY: Mapping[str, str] = {
    "en": "This adds up what you paid across your claims this year.",
    "ms": "Ini menjumlahkan bayaran anda merentasi tuntutan tahun ini.",
    "zh": "这是把您今年各项索赔的付款加起来。",
}

# @patient
COST_WHY_THEIRS: Mapping[str, str] = {
    "en": "This adds up what {patient} paid across {patient}'s claims this year.",
    "ms": "Ini menjumlahkan bayaran {patient} merentasi tuntutan {patient} tahun ini.",
    "zh": "这是把{patient}今年各项索赔的付款加起来。",
}

# @patient
COVERAGE_LINE: Mapping[str, str] = {
    "en": "Your {policy} policy shows as {status} in your papers.",
    "ms": "Polisi {policy} anda tertulis sebagai {status} dalam surat-surat anda.",
    "zh": "您的{policy}保单在文件中显示为{status}。",
}

# @patient
COVERAGE_LINE_THEIRS: Mapping[str, str] = {
    "en": "{patient}'s {policy} policy shows as {status} in {patient}'s papers.",
    "ms": "Polisi {policy} {patient} tertulis sebagai {status} dalam surat-surat {patient}.",
    "zh": "{patient}的{policy}保单在文件中显示为{status}。",
}

# @patient
COVERAGE_WHY: Mapping[str, str] = {
    "en": "This is what is written down about your policy right now.",
    "ms": "Ini adalah apa yang tertulis tentang polisi anda sekarang.",
    "zh": "这是您保单目前在文件中的记录。",
}

# @patient
COVERAGE_WHY_THEIRS: Mapping[str, str] = {
    "en": "This is what is written down about {patient}'s policy right now.",
    "ms": "Ini adalah apa yang tertulis tentang polisi {patient} sekarang.",
    "zh": "这是{patient}保单目前在文件中的记录。",
}

# @patient phrase
STATUS_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "lapsed": "no longer active",
        "cancelled": "cancelled",
        "renewal_due": "past its renewal date",
    },
    "ms": {
        "lapsed": "tidak lagi aktif",
        "cancelled": "dibatalkan",
        "renewal_due": "melepasi tarikh pembaharuan",
    },
    "zh": {
        "lapsed": "已经不再生效",
        "cancelled": "已取消",
        "renewal_due": "已经过了续保日期",
    },
}

# @patient
STEP_LABEL: Mapping[str, Mapping[str, str]] = {
    "en": {
        "records": "Looking at what you have told Nura.",
        "series": "Looking at your blood pressure.",
        "medicines": "Looking at your medicines.",
        "ledger": "Adding up what you paid.",
        "coverage": "Looking at your policies.",
    },
    "ms": {
        "records": "Melihat apa yang anda beritahu Nura.",
        "series": "Melihat tekanan darah anda.",
        "medicines": "Melihat ubat anda.",
        "ledger": "Menjumlahkan apa yang anda bayar.",
        "coverage": "Melihat polisi anda.",
    },
    "zh": {
        "records": "查看您告诉Nura的资料。",
        "series": "查看您的血压。",
        "medicines": "查看您的药物。",
        "ledger": "把您付的钱加起来。",
        "coverage": "查看您的保单。",
    },
}
"""One label per `app.reasoning.analyst.port.StepKey`, said the moment that real read
finishes (`POST /profiles/{id}/insights/stream`'s own `step` event) — the same "real work
already happened" discipline `app.search.ask.STEP_KEYS` holds its own labels to."""

# @patient
STEP_LABEL_THEIRS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "records": "Looking at what has been told to Nura.",
        "series": "Looking at {patient}'s blood pressure.",
        "medicines": "Looking at {patient}'s medicines.",
        "ledger": "Adding up what {patient} paid.",
        "coverage": "Looking at {patient}'s policies.",
    },
    "ms": {
        "records": "Melihat apa yang diberitahu kepada Nura.",
        "series": "Melihat tekanan darah {patient}.",
        "medicines": "Melihat ubat {patient}.",
        "ledger": "Menjumlahkan apa yang {patient} bayar.",
        "coverage": "Melihat polisi {patient}.",
    },
    "zh": {
        "records": "查看告诉Nura的资料。",
        "series": "查看{patient}的血压。",
        "medicines": "查看{patient}的药物。",
        "ledger": "把{patient}付的钱加起来。",
        "coverage": "查看{patient}的保单。",
    },
}

# @patient
ASK_THE_DOCTOR_LINE: Mapping[str, str] = {
    "en": "Something about one of your medicines is worth asking the doctor about.",
    "ms": "Ada sesuatu tentang salah satu ubat anda untuk ditanya kepada doktor.",
    "zh": "您其中一种药物的事，值得问问医生。",
}
"""What is shown instead of a medicine or supplement candidate's own words when those words
fail the plain-words check or the conclusion-or-advice blocklist (`app.reasoning.analyst.
pipeline.finalize`, #236): a real question is filed for the doctor, and this line — never the
candidate's own text — is what the report shows."""

# @patient
ASK_THE_DOCTOR_LINE_THEIRS: Mapping[str, str] = {
    "en": "Something about one of {patient}'s medicines is worth asking the doctor about.",
    "ms": "Ada sesuatu tentang salah satu ubat {patient} untuk ditanya kepada doktor.",
    "zh": "{patient}其中一种药物的事，值得问问医生。",
}

# @patient
ASK_THE_DOCTOR_WHY: Mapping[str, str] = {
    "en": "This was set aside instead of being shown as written.",
    "ms": "Ini diketepikan dan tidak ditunjukkan seperti yang ditulis.",
    "zh": "这个部分被保留下来，没有照原文显示。",
}

# @patient
WITHHELD_LINE: Mapping[str, str] = {
    "en": "{title} is not shown to you.",
    "ms": "{title} tidak ditunjukkan kepada anda.",
    "zh": "{title}没有显示给您看。",
}
"""One line per section `app.reasoning.analyst.service._narrowed_for` left out for a key
narrower than the one that generated the report (`InsightReportOut.withheld`) — named, never
a silent gap where a section used to be. `{title}` is that section's own
`app.reasoning.analyst.port.SECTION_TITLES` entry, already a plain word."""

# @patient
WITHHELD_LINE_THEIRS: Mapping[str, str] = {
    "en": "{title} is not shown to {patient}.",
    "ms": "{title} tidak ditunjukkan kepada {patient}.",
    "zh": "{title}没有显示给{patient}看。",
}


def fill(line: str, **slots: object) -> str:
    """One filled template, for `rule.py` to hand straight to `pipeline.finalize`. Every
    template here opens on a `{slot}` — a plain name such as "the joint supplement" — so the
    first letter of the *filled* line, never the template's own words, is capitalised: plain
    words rule 1, "a whole sentence", starts with a capital, and a plain name is written
    lower-case everywhere else it already appears mid-sentence (docs/plain-words.md)."""
    filled = line.format(**slots)
    return filled[:1].upper() + filled[1:] if filled else filled


__all__ = [
    "ASK_THE_DOCTOR_LINE",
    "ASK_THE_DOCTOR_LINE_THEIRS",
    "ASK_THE_DOCTOR_WHY",
    "BP_NAME",
    "COST_LINE",
    "COST_LINE_THEIRS",
    "COST_WHY",
    "COST_WHY_THEIRS",
    "COVERAGE_LINE",
    "COVERAGE_LINE_THEIRS",
    "COVERAGE_WHY",
    "COVERAGE_WHY_THEIRS",
    "DUPLICATE_LINE",
    "DUPLICATE_LINE_THEIRS",
    "DUPLICATE_WHY",
    "DUPLICATE_WHY_THEIRS",
    "LANGUAGES",
    "SCREENING_LINE",
    "SCREENING_LINE_THEIRS",
    "SCREENING_NAME",
    "SCREENING_WHY",
    "SCREENING_WHY_THEIRS",
    "SECTION_TITLES",
    "STATUS_WORDS",
    "STEP_LABEL",
    "STEP_LABEL_THEIRS",
    "SUPPLEMENT_LINE",
    "SUPPLEMENT_LINE_THEIRS",
    "SUPPLEMENT_WHY",
    "SUPPLEMENT_WHY_THEIRS",
    "TREND_LINE",
    "TREND_LINE_THEIRS",
    "TREND_WHY",
    "TREND_WHY_THEIRS",
    "WITHHELD_LINE",
    "WITHHELD_LINE_THEIRS",
    "fill",
]
