"""The words of onboarding (E01): every sentence a patient reads or hears while his profile is
set up — the biography's script, the read-back, the questions, the first week's prompts and
the summary — in English, Malay and Chinese.

Each is tagged `@patient` and written to docs/plain-words.md: whole sentences, one idea per
line, his words for things, the day and the date, who does the next thing. The backend fills
the `{slots}` — a condition's name from `conditions.json`, the doctor's name, a number or a
line from a paper, a plain date — and every filled line goes through
`app.safety.plain_words.verify` before it is served (`app.onboarding.words`). Nothing here is
advice: a line reads back what a paper or a person said, asks him for a paper, or says what
Nura will do with it once it has it. The Malay and Chinese lines are a first translation
awaiting a native speaker's pass, like the boundary copy's.
"""

from __future__ import annotations

from collections.abc import Mapping

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"


def language_for(code: str | None) -> str:
    """One of the three languages these words exist in; English for anything else."""
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


# --- the biography's script: one headline and a few lines for each step ----------------------

# @patient headline
SCRIPT_HEADLINE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "about_you": "A few things about you",
        "papers": "Now, your papers",
        "read_back": "Here is what Nura understood",
        "questions": "A few questions about your papers",
        "closed": "Your app is ready",
    },
    "ms": {
        "about_you": "Sedikit tentang anda",
        "papers": "Sekarang, surat-surat anda",
        "read_back": "Ini yang Nura faham",
        "questions": "Beberapa soalan tentang surat-surat anda",
        "closed": "Aplikasi anda sudah sedia",
    },
    "zh": {
        "about_you": "关于您的几件事",
        "papers": "现在，您的文件",
        "read_back": "这是Nura的理解",
        "questions": "关于您的文件的几个问题",
        "closed": "您的应用已经准备好了",
    },
}

# @patient
SCRIPT_LINES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "en": {
        "about_you": (
            "Tell us which language you like best.",
            "Tap anything that is part of your health.",
            "It only tells Nura where to look.",
        ),
        "papers": (
            "Take a photo of each paper you have.",
            "Hospital letters and blood tests help the most.",
            "Tap once to save each paper.",
        ),
        "read_back": (
            "Tell us if any line is not right.",
            "It is better to fix it now.",
        ),
        "questions": (
            "Each question is short.",
            "Each answer helps Nura know you better.",
        ),
        "closed": (
            "Your Today page comes from what you told us.",
            "Each morning at breakfast, Nura asks for one more thing.",
        ),
    },
    "ms": {
        "about_you": (
            "Beritahu kami bahasa yang anda paling suka.",
            "Tekan apa-apa yang berkaitan dengan kesihatan anda.",
            "Ini hanya supaya Nura tahu apa yang perlu diberi perhatian.",
        ),
        "papers": (
            "Ambil gambar setiap surat yang anda ada.",
            "Surat hospital dan ujian darah paling membantu.",
            "Tekan sekali untuk simpan setiap surat.",
        ),
        "read_back": (
            "Beritahu kami jika ada baris yang tidak betul.",
            "Lebih baik kita betulkan sekarang.",
        ),
        "questions": (
            "Setiap soalan pendek sahaja.",
            "Setiap jawapan membantu Nura mengenali anda.",
        ),
        "closed": (
            "Halaman Hari Ini anda datang daripada apa yang anda beritahu kami.",
            "Setiap pagi waktu sarapan, Nura minta satu perkara lagi.",
        ),
    },
    "zh": {
        "about_you": (
            "请告诉我们您最喜欢哪种语言。",
            "请点一下和您健康有关的任何一项。",
            "这只是让Nura知道该注意什么。",
        ),
        "papers": (
            "请把您的每一张文件拍下来。",
            "出院信和验血报告最有帮助。",
            "每一张按一下就能保存。",
        ),
        "read_back": (
            "如果哪一行不对，请告诉我们。",
            "现在改正比较好。",
        ),
        "questions": (
            "每个问题都很简短。",
            "每个回答都让Nura更了解您。",
        ),
        "closed": (
            "您的今天页面来自您告诉我们的一切。",
            "每天早餐时，Nura会再请您提供一样东西。",
        ),
    },
}

# --- the read-back: one line per confirmed fact, which he answers yes or no ------------------
# A Chinese date is three numbers ("2023年9月7日"), so a result read back in Chinese takes a
# second line for its number (rule 10: a second number is a second line).

# @patient
READ_BACK: Mapping[str, Mapping[str, str]] = {
    "en": {
        "condition": "You told us: {condition}.",
        "doctor": "Your doctor is {doctor}.",
        "total_cholesterol": "Your cholesterol was {value} on {date}.",
        "ldl": "Your bad cholesterol was {value} on {date}.",
        "hdl": "Your good cholesterol was {value} on {date}.",
        "medicine": "The label is for a medicine called {medicine}.",
        "thinner": "The label is for your blood thinner, {medicine}.",
        "instruction": "Nura read the label as {instruction}.",
        "prescriber": "The label says {prescriber} gave you this medicine.",
    },
    "ms": {
        "condition": "Anda beritahu kami: {condition}.",
        "doctor": "Doktor anda ialah {doctor}.",
        "total_cholesterol": "Kolesterol anda {value} pada {date}.",
        "ldl": "Kolesterol jahat anda {value} pada {date}.",
        "hdl": "Kolesterol baik anda {value} pada {date}.",
        "medicine": "Label ini untuk ubat bernama {medicine}.",
        "thinner": "Label ini untuk ubat cair darah anda, {medicine}.",
        "instruction": "Label ini menyebut {instruction}.",
        "prescriber": "Label ini kata {prescriber} yang beri ubat ini.",
    },
    "zh": {
        "condition": "您告诉我们：{condition}。",
        "doctor": "您的医生是{doctor}。",
        "total_cholesterol": "这是{date}的验血结果。\n您的胆固醇是{value}。",
        "ldl": "这是{date}的验血结果。\n您的坏胆固醇是{value}。",
        "hdl": "这是{date}的验血结果。\n您的好胆固醇是{value}。",
        "medicine": "这个标签上的药叫{medicine}。",
        "thinner": "这个标签上的药是您的薄血药，{medicine}。",
        "instruction": "Nura看到标签上写的是：{instruction}。",
        "prescriber": "标签上写着这药是{prescriber}开的。",
    },
}

# --- the questions: what the papers did not say, asked of him -------------------------------

# @patient
QUESTION: Mapping[str, Mapping[str, str]] = {
    "en": {
        "medicines": "Which tablets do you take each day?",
        "bp_numbers": "Do you check your blood pressure at home?",
        "weight": "Do you weigh yourself most mornings?",
        "allergy_which": "Which medicine are you allergic to?",
        "thinner_which": "Which blood thinner do you take?",
        "discharge_letter": "Do you have your hospital letter?",
        "cholesterol_result": "When was your last cholesterol test?",
        "sugar_result": "When was your last sugar test?",
        "kidney_result": "When was your last kidney test?",
        "next_visit": "When do you see {doctor} next?",
        "last_visit": "When did you last see {doctor}?",
        "insurance": "Do you have an insurance card?",
        "meal_times": "What time do you have breakfast?",
        "someone_to_see": "Who else should see your papers?",
    },
    "ms": {
        "medicines": "Ubat apa yang anda makan setiap hari?",
        "bp_numbers": "Adakah anda periksa tekanan darah di rumah?",
        "weight": "Adakah anda timbang berat badan hampir setiap pagi?",
        "allergy_which": "Anda alah kepada ubat apa?",
        "thinner_which": "Ubat cair darah apa yang anda makan?",
        "discharge_letter": "Adakah anda ada surat hospital anda?",
        "cholesterol_result": "Bila ujian kolesterol anda yang terakhir?",
        "sugar_result": "Bila ujian gula anda yang terakhir?",
        "kidney_result": "Bila ujian buah pinggang anda yang terakhir?",
        "next_visit": "Bila anda jumpa {doctor} lagi?",
        "last_visit": "Bila kali terakhir anda jumpa {doctor}?",
        "insurance": "Adakah anda ada kad insurans?",
        "meal_times": "Pukul berapa anda bersarapan?",
        "someone_to_see": "Siapa lagi patut melihat surat-surat anda?",
    },
    "zh": {
        "medicines": "您每天吃哪些药？",
        "bp_numbers": "您在家量血压吗？",
        "weight": "您大多数早上都量体重吗？",
        "allergy_which": "您对哪种药过敏？",
        "thinner_which": "您吃的是哪种薄血药？",
        "discharge_letter": "您有出院信吗？",
        "cholesterol_result": "您上一次验胆固醇是什么时候？",
        "sugar_result": "您上一次验血糖是什么时候？",
        "kidney_result": "您上一次验肾功能是什么时候？",
        "next_visit": "您下次什么时候看{doctor}？",
        "last_visit": "您上一次看{doctor}是什么时候？",
        "insurance": "您有保险卡吗？",
        "meal_times": "您几点吃早餐？",
        "someone_to_see": "还有谁应该看您的文件？",
    },
}

# @patient
QUESTIONS_MORE: Mapping[str, str] = {
    "en": "{count} more can wait for later.",
    "ms": "{count} lagi boleh tunggu kemudian.",
    "zh": "还有{count}个可以以后再说。",
}

# @patient
CHECK_AGAIN: Mapping[str, str] = {
    "en": "{who} will look at that paper again.",
    "ms": "{who} akan lihat surat itu sekali lagi.",
    "zh": "{who}会再看一次那张文件。",
}
"""After a "no" on the read-back, when someone set the profile up for him: who does the
next thing (docs/plain-words.md rule 7)."""

# @patient
KEPT_BESIDE: Mapping[str, str] = {
    "en": "Nura keeps your answer beside the paper.",
    "ms": "Nura simpan jawapan anda bersama surat itu.",
    "zh": "Nura会把您的回答和文件放在一起。",
}
"""After a "no" when he is setting his own profile up: his answer stands beside the paper."""

# --- the first week: one prompt a day, what is missing and what it lets Nura do ----------------

# @patient headline
PROMPT_HEADLINE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "medicines": "Your tablets and how much you take",
        "bp_numbers": "Your usual blood pressure numbers",
        "weight": "Your weight most mornings",
        "allergy_which": "The medicine you are allergic to",
        "thinner_which": "Which blood thinner you take",
        "discharge_letter": "Your hospital letter",
        "cholesterol_result": "Your last cholesterol test",
        "sugar_result": "Your last sugar test",
        "kidney_result": "Your last kidney test",
        "next_visit": "Your next visit to {doctor}",
        "last_visit": "Your last visit to {doctor}",
        "insurance": "Your insurance card",
        "meal_times": "Your breakfast time",
        "someone_to_see": "Someone who can see your papers",
    },
    "ms": {
        "medicines": "Ubat anda dan berapa banyak anda makan",
        "bp_numbers": "Nombor tekanan darah biasa anda",
        "weight": "Berat badan anda setiap pagi",
        "allergy_which": "Ubat yang anda alah",
        "thinner_which": "Ubat cair darah yang anda makan",
        "discharge_letter": "Surat hospital anda",
        "cholesterol_result": "Ujian kolesterol anda yang terakhir",
        "sugar_result": "Ujian gula anda yang terakhir",
        "kidney_result": "Ujian buah pinggang anda yang terakhir",
        "next_visit": "Lawatan anda yang seterusnya ke {doctor}",
        "last_visit": "Lawatan terakhir anda ke {doctor}",
        "insurance": "Kad insurans anda",
        "meal_times": "Waktu sarapan anda",
        "someone_to_see": "Seseorang yang boleh melihat surat-surat anda",
    },
    "zh": {
        "medicines": "您的药和吃多少",
        "bp_numbers": "您平时的血压数字",
        "weight": "您每天早上的体重",
        "allergy_which": "您过敏的药",
        "thinner_which": "您吃的薄血药",
        "discharge_letter": "您的出院信",
        "cholesterol_result": "您上一次的胆固醇检查",
        "sugar_result": "您上一次的血糖检查",
        "kidney_result": "您上一次的肾功能检查",
        "next_visit": "您下次看{doctor}",
        "last_visit": "您上次看{doctor}",
        "insurance": "您的保险卡",
        "meal_times": "您的早餐时间",
        "someone_to_see": "可以看您文件的人",
    },
}

# @patient
PROMPT_UNLOCK: Mapping[str, Mapping[str, str]] = {
    "en": {
        "medicines": "With it, Nura can look at all your tablets together.",
        "bp_numbers": "With them, Nura can tell what is normal for you.",
        "weight": "With it, Nura can show how your weight changes each week.",
        "allergy_which": "With it, Nura can put it on your emergency card.",
        "thinner_which": "With it, Nura can look at it next to your other tablets.",
        "discharge_letter": "With it, Nura can see what changed in hospital.",
        "cholesterol_result": "With it, Nura can show if your cholesterol is going up or down.",
        "sugar_result": "With it, Nura can show if your sugar is going up or down.",
        "kidney_result": "With it, Nura can ask about each new tablet and your kidneys.",
        "next_visit": "With it, Nura can get your questions ready 3 days before.",
        "last_visit": "With it, Nura knows when you last saw {doctor}.",
        "insurance": "With it, Nura can tell which hospitals are on your insurance.",
        "meal_times": "With it, reminders come with your meals.",
        "someone_to_see": "With it, Nura can let them know if something changes.",
    },
    "ms": {
        "medicines": "Dengan itu, Nura boleh lihat semua ubat anda bersama.",
        "bp_numbers": "Dengan itu, Nura tahu apa yang biasa bagi anda.",
        "weight": "Dengan itu, Nura boleh tunjuk perubahan berat badan anda setiap minggu.",
        "allergy_which": "Dengan itu, Nura boleh letak di kad kecemasan anda.",
        "thinner_which": "Dengan itu, Nura boleh lihat bersama ubat lain anda.",
        "discharge_letter": "Dengan itu, Nura boleh nampak apa yang berubah di hospital.",
        "cholesterol_result": "Dengan itu, Nura boleh tunjuk sama ada kolesterol anda naik atau turun.",
        "sugar_result": "Dengan itu, Nura boleh tunjuk sama ada gula anda naik atau turun.",
        "kidney_result": "Dengan itu, Nura boleh tanya tentang setiap ubat baru dan buah pinggang anda.",
        "next_visit": "Dengan itu, Nura boleh sediakan soalan anda 3 hari sebelumnya.",
        "last_visit": "Dengan itu, Nura tahu bila anda terakhir jumpa {doctor}.",
        "insurance": "Dengan itu, Nura boleh tahu hospital mana dalam insurans anda.",
        "meal_times": "Dengan itu, peringatan datang bersama waktu makan anda.",
        "someone_to_see": "Dengan itu, Nura boleh beritahu mereka jika ada perubahan.",
    },
    "zh": {
        "medicines": "有了它，Nura可以一起看您所有的药。",
        "bp_numbers": "有了它，Nura知道什么对您来说是正常的。",
        "weight": "有了它，Nura可以显示您每周体重的变化。",
        "allergy_which": "有了它，Nura可以把它写在您的急救卡上。",
        "thinner_which": "有了它，Nura可以把它和您的其他药放在一起看。",
        "discharge_letter": "有了它，Nura可以看到住院时改了什么。",
        "cholesterol_result": "有了它，Nura可以显示您的胆固醇是升还是降。",
        "sugar_result": "有了它，Nura可以显示您的血糖是升还是降。",
        "kidney_result": "有了它，Nura可以问每种新药和您的肾有没有关系。",
        "next_visit": "有了它，Nura可以提前3天准备好您的问题。",
        "last_visit": "有了它，Nura知道您上次什么时候看{doctor}。",
        "insurance": "有了它，Nura可以知道哪些医院在您的保险里。",
        "meal_times": "有了它，提醒会跟着您的三餐来。",
        "someone_to_see": "有了它，有变化时Nura可以告诉他们。",
    },
}

# @patient action
PROMPT_ACTION: Mapping[str, Mapping[str, str]] = {
    "en": {
        "medicines": "Today, take a photo of the medicine bag.",
        "bp_numbers": "Today, take a photo of your blood pressure machine.",
        "weight": "Today, stand on your scale and take a photo.",
        "allergy_which": "Today, tap the medicine you are allergic to.",
        "thinner_which": "Today, take a photo of the blood thinner box.",
        "discharge_letter": "Today, take a photo of your hospital letter.",
        "cholesterol_result": "Today, take a photo of any blood test.",
        "sugar_result": "Today, take a photo of any blood test.",
        "kidney_result": "Today, take a photo of any blood test.",
        "next_visit": "Today, take a photo of your appointment card.",
        "last_visit": "Today, take a photo of your last visit slip.",
        "insurance": "Today, take a photo of your insurance card.",
        "meal_times": "Today, tap the time you have breakfast.",
        "someone_to_see": "Today, invite one person to see your papers.",
    },
    "ms": {
        "medicines": "Hari ini, ambil gambar beg ubat.",
        "bp_numbers": "Hari ini, ambil gambar mesin tekanan darah anda.",
        "weight": "Hari ini, berdiri di atas penimbang dan ambil gambar.",
        "allergy_which": "Hari ini, tekan ubat yang anda alah.",
        "thinner_which": "Hari ini, ambil gambar kotak ubat cair darah.",
        "discharge_letter": "Hari ini, ambil gambar surat hospital anda.",
        "cholesterol_result": "Hari ini, ambil gambar mana-mana ujian darah.",
        "sugar_result": "Hari ini, ambil gambar mana-mana ujian darah.",
        "kidney_result": "Hari ini, ambil gambar mana-mana ujian darah.",
        "next_visit": "Hari ini, ambil gambar kad temu janji anda.",
        "last_visit": "Hari ini, ambil gambar slip lawatan terakhir anda.",
        "insurance": "Hari ini, ambil gambar kad insurans anda.",
        "meal_times": "Hari ini, tekan waktu anda bersarapan.",
        "someone_to_see": "Hari ini, jemput seorang untuk melihat surat-surat anda.",
    },
    "zh": {
        "medicines": "今天，请拍下药袋。",
        "bp_numbers": "今天，请拍下您的血压计。",
        "weight": "今天，请站上体重秤，然后拍照。",
        "allergy_which": "今天，请点一下您过敏的药。",
        "thinner_which": "今天，请拍下薄血药的盒子。",
        "discharge_letter": "今天，请拍下您的出院信。",
        "cholesterol_result": "今天，请拍下任何一份验血报告。",
        "sugar_result": "今天，请拍下任何一份验血报告。",
        "kidney_result": "今天，请拍下任何一份验血报告。",
        "next_visit": "今天，请拍下您的预约卡。",
        "last_visit": "今天，请拍下上次看诊的单子。",
        "insurance": "今天，请拍下您的保险卡。",
        "meal_times": "今天，请点一下您吃早餐的时间。",
        "someone_to_see": "今天，请邀请一个人来看您的文件。",
    },
}

# --- the summary at the close of the biography --------------------------------------------

# @patient
SUMMARY: Mapping[str, Mapping[str, str]] = {
    "en": {
        "papers_none": "No papers were added this time.",
        "papers_one": "Nura saved one of your papers.",
        "papers_many": "Nura saved {count} of your papers.",
        "facts_one": "Nura wrote down one thing from your papers.",
        "facts_many": "Nura wrote down {count} things from your papers.",
        "disputes_one": "You said one line was not right.",
        "disputes_many": "You said {count} lines were not right.",
        "plan_first": "Tomorrow at breakfast, Nura will ask for one more thing.",
        "plan_count": "There are {count} things to ask, one each day.",
        "plan_none": "Nura has nothing more to ask for now.",
        "ready": "Your Today page comes from what you told us.",
    },
    "ms": {
        "papers_none": "Tiada surat ditambah kali ini.",
        "papers_one": "Nura simpan satu surat anda.",
        "papers_many": "Nura simpan {count} surat anda.",
        "facts_one": "Nura catat satu perkara daripada surat-surat anda.",
        "facts_many": "Nura catat {count} perkara daripada surat-surat anda.",
        "disputes_one": "Anda kata satu baris tidak betul.",
        "disputes_many": "Anda kata {count} baris tidak betul.",
        "plan_first": "Esok waktu sarapan, Nura akan minta satu perkara lagi.",
        "plan_count": "Ada {count} perkara untuk diminta, satu setiap hari.",
        "plan_none": "Nura tiada apa-apa lagi untuk diminta buat masa ini.",
        "ready": "Halaman Hari Ini anda datang daripada apa yang anda beritahu kami.",
    },
    "zh": {
        "papers_none": "这次没有加入文件。",
        "papers_one": "Nura保存了您的一张文件。",
        "papers_many": "Nura保存了您的{count}张文件。",
        "facts_one": "Nura从您的文件里记下了一样东西。",
        "facts_many": "Nura从您的文件里记下了{count}样东西。",
        "disputes_one": "您说有一行不对。",
        "disputes_many": "您说有{count}行不对。",
        "plan_first": "明天早餐时，Nura会再请您提供一样东西。",
        "plan_count": "一共有{count}样，每天一样。",
        "plan_none": "现在Nura没有别的要问了。",
        "ready": "您的今天页面来自您告诉我们的一切。",
    },
}
