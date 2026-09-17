"""Every word the feeling cloud, its one question and the note say, in his three languages.

Each template is a whole line, filled and never assembled: `{doctor}` is the doctor's name
("Dr Tan", or "your doctor"), `{medicine}` his name for the medicine
(`app.medicines.strings.PLAIN_NAME`), `{date}` "Monday 14 September", `{count}` a digit, and
`{when}` one of `WHEN`, which completes the line it sits in. Every table is tagged `@patient`
so `make plain-words` holds it to docs/plain-words.md; the lines the backend fills at run
time are verified again before they reach him (`app.reasoning.feelings.inference`).

The Malay and Chinese lines are a first translation awaiting a native speaker's pass, as the
boundary's are (`app.safety.boundary`).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.reasoning.feelings.words import Answer, FollowUp
from app.safety.boundary import language_of
from app.safety.red_flags import Feeling

__all__ = ["language_of"]

# @patient phrase
WORDS: Mapping[str, Mapping[Feeling, str]] = {
    "en": {
        Feeling.FALL: "Had a fall",
        Feeling.CHEST_TIGHTNESS: "Chest pain",
        Feeling.BREATHLESS_AT_REST: "Short of breath sitting still",
        Feeling.ONE_SIDED_SWELLING: "One leg swollen",
        Feeling.WORST_HEADACHE: "Worst headache ever",
        Feeling.SUDDEN_BLURRING: "Suddenly blurry eyes",
        Feeling.CONFUSION: "Muddled",
        Feeling.SHAKY_SWEATY: "Shaky and sweaty",
        Feeling.WEIGHT_GAIN: "Heavier",
        Feeling.DIZZY: "Dizzy",
        Feeling.CRAMPS: "Cramps",
        Feeling.THIRSTY: "Very thirsty",
        Feeling.TIRED: "Tired",
        Feeling.ACHES: "Muscle aches",
        Feeling.HEADACHE: "Headache",
        Feeling.PAIN: "Pain",
        Feeling.BREATHLESS: "Short of breath",
        Feeling.LOW: "Sad",
        Feeling.WORRIED: "Worried",
        Feeling.CANT_SLEEP: "Poor sleep",
        Feeling.SWOLLEN_ANKLES: "Swollen ankles",
        Feeling.STOMACH_UPSET: "Upset stomach",
        Feeling.FINE: "Fine today",
    },
    "ms": {
        Feeling.FALL: "Terjatuh",
        Feeling.CHEST_TIGHTNESS: "Sakit dada",
        Feeling.BREATHLESS_AT_REST: "Sesak nafas semasa duduk",
        Feeling.ONE_SIDED_SWELLING: "Sebelah kaki bengkak",
        Feeling.WORST_HEADACHE: "Sakit kepala paling teruk",
        Feeling.SUDDEN_BLURRING: "Mata tiba-tiba kabur",
        Feeling.CONFUSION: "Keliru",
        Feeling.SHAKY_SWEATY: "Menggigil dan berpeluh",
        Feeling.WEIGHT_GAIN: "Berat naik",
        Feeling.DIZZY: "Pening",
        Feeling.CRAMPS: "Kejang otot",
        Feeling.THIRSTY: "Sangat dahaga",
        Feeling.TIRED: "Letih",
        Feeling.ACHES: "Sakit otot",
        Feeling.HEADACHE: "Sakit kepala",
        Feeling.PAIN: "Sakit",
        Feeling.BREATHLESS: "Sesak nafas",
        Feeling.LOW: "Sedih",
        Feeling.WORRIED: "Risau",
        Feeling.CANT_SLEEP: "Susah tidur",
        Feeling.SWOLLEN_ANKLES: "Buku lali bengkak",
        Feeling.STOMACH_UPSET: "Perut tidak selesa",
        Feeling.FINE: "Sihat hari ini",
    },
    "zh": {
        Feeling.FALL: "跌倒了",
        Feeling.CHEST_TIGHTNESS: "胸口痛",
        Feeling.BREATHLESS_AT_REST: "坐着也喘",
        Feeling.ONE_SIDED_SWELLING: "一条腿肿",
        Feeling.WORST_HEADACHE: "最痛的头痛",
        Feeling.SUDDEN_BLURRING: "眼睛突然模糊",
        Feeling.CONFUSION: "糊涂",
        Feeling.SHAKY_SWEATY: "发抖又出汗",
        Feeling.WEIGHT_GAIN: "体重增加",
        Feeling.DIZZY: "头晕",
        Feeling.CRAMPS: "抽筋",
        Feeling.THIRSTY: "很口渴",
        Feeling.TIRED: "累",
        Feeling.ACHES: "肌肉酸痛",
        Feeling.HEADACHE: "头痛",
        Feeling.PAIN: "痛",
        Feeling.BREATHLESS: "气短",
        Feeling.LOW: "心情低落",
        Feeling.WORRIED: "担心",
        Feeling.CANT_SLEEP: "睡不好",
        Feeling.SWOLLEN_ANKLES: "脚踝肿",
        Feeling.STOMACH_UPSET: "肚子不舒服",
        Feeling.FINE: "今天还好",
    },
}
"""The word on the cloud: his word for how he feels, never a condition."""

# @patient
PROMPT: Mapping[str, str] = {
    "en": "How are you feeling today?",
    "ms": "Apa khabar hari ini?",
    "zh": "今天感觉怎么样？",
}
"""The one line above the words. Never a form, never a scale."""


def asks_about_feeling(text: str, language: str) -> bool:
    """Whether `text`, sent in `language`, puts the feeling question to him — `PROMPT`'s own
    words, verbatim, wherever they sit in the message.

    This is what an outbound WhatsApp message is checked against before it is allowed to open
    his answer window (`app.channels.whatsapp.outbound.send.send`,
    `WhatsAppMessage.asks_feeling`, #205): not the name of the template that carried it, which
    is a list a later asker of the same question — a nudge, or anything after it — could
    silently fall outside of. The plain check-in template and the day's check-in nudge both
    carry `PROMPT`'s words today; anything later that asks this question the same way, by
    reusing them, is covered without a line of code changing here.
    """
    prompt = PROMPT.get(language)
    return prompt is not None and prompt in text

# @patient
LEADS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "new_medicine": "{medicine} is new since {date}.",
        "after_discharge": "You came home from hospital on {date}.",
        "reading_trend": "Your last {count} blood pressure numbers went up each time.",
    },
    "ms": {
        "new_medicine": "{medicine} baru sejak {date}.",
        "after_discharge": "Anda pulang dari hospital pada {date}.",
        "reading_trend": "{count} bacaan tekanan darah terakhir anda naik setiap kali.",
    },
    "zh": {
        "new_medicine": "{medicine}从{date}起是新的。",
        "after_discharge": "您{date}从医院回家。",
        "reading_trend": "您最近{count}次的血压一次比一次高。",
    },
}
"""What changed, said before the question when the cloud comes forward after a change. The
same words open the check-in nudge (`app.delivery.nudges.strings`)."""

# @patient
QUESTIONS: Mapping[str, Mapping[FollowUp, str]] = {
    "en": {
        FollowUp.SINCE_WHEN: "When did it begin?",
        FollowUp.MORE_THAN_YESTERDAY: "Is it more than yesterday?",
        FollowUp.AT_REST: "Is it there even when you sit still?",
        FollowUp.ONE_SIDE: "Is only one leg swollen?",
        FollowUp.WORST_EVER: "Is it the worst headache of your life?",
    },
    "ms": {
        FollowUp.SINCE_WHEN: "Bila ia bermula?",
        FollowUp.MORE_THAN_YESTERDAY: "Adakah ia lebih teruk daripada semalam?",
        FollowUp.AT_REST: "Adakah ia berlaku walaupun anda duduk diam?",
        FollowUp.ONE_SIDE: "Adakah hanya sebelah kaki yang bengkak?",
        FollowUp.WORST_EVER: "Adakah ini sakit kepala paling teruk dalam hidup anda?",
    },
    "zh": {
        FollowUp.SINCE_WHEN: "什么时候开始的？",
        FollowUp.MORE_THAN_YESTERDAY: "比昨天更厉害吗？",
        FollowUp.AT_REST: "坐着不动的时候也会这样吗？",
        FollowUp.ONE_SIDE: "是不是只有一条腿肿？",
        FollowUp.WORST_EVER: "这是您这辈子最痛的头痛吗？",
    },
}
"""The one thing a tap asks back (`app.reasoning.feelings.words.FollowUp`)."""

# @patient phrase
ANSWER_WORDS: Mapping[str, Mapping[Answer, str]] = {
    "en": {
        Answer.TODAY: "Today",
        Answer.YESTERDAY: "Since yesterday",
        Answer.FEW_DAYS: "A few days",
        Answer.WEEK_OR_MORE: "A week or more",
        Answer.MORE: "More",
        Answer.SAME: "The same",
        Answer.LESS: "Less",
        Answer.YES: "Yes",
        Answer.NO: "No",
    },
    "ms": {
        Answer.TODAY: "Hari ini",
        Answer.YESTERDAY: "Sejak semalam",
        Answer.FEW_DAYS: "Beberapa hari",
        Answer.WEEK_OR_MORE: "Seminggu atau lebih",
        Answer.MORE: "Lebih teruk",
        Answer.SAME: "Sama",
        Answer.LESS: "Kurang",
        Answer.YES: "Ya",
        Answer.NO: "Tidak",
    },
    "zh": {
        Answer.TODAY: "今天",
        Answer.YESTERDAY: "从昨天开始",
        Answer.FEW_DAYS: "几天了",
        Answer.WEEK_OR_MORE: "一个星期或更久",
        Answer.MORE: "更厉害",
        Answer.SAME: "一样",
        Answer.LESS: "好一点",
        Answer.YES: "是",
        Answer.NO: "不是",
    },
}
"""The buttons under the question."""

# @patient
FINE_LINES: Mapping[str, tuple[str, str]] = {
    "en": ("That is good to hear.", "Nura will ask again when something changes."),
    "ms": ("Baguslah, terima kasih.", "Nura akan tanya lagi bila ada perubahan."),
    "zh": ("那就好。", "有变化的时候，Nura 会再问您。"),
}
"""What "Fine today" says back, and why the cloud goes away."""

# @patient headline
NOTE_HEADLINE: Mapping[str, str] = {
    "en": "Things to tell {doctor}",
    "ms": "Perkara untuk diberitahu kepada {doctor}",
    "zh": "要告诉{doctor}的事",
}

# @patient
TELL: Mapping[str, Mapping[Feeling, str]] = {
    "en": {
        Feeling.DIZZY: "Tell {doctor} you feel dizzy {when}.",
        Feeling.TIRED: "Tell {doctor} you feel tired {when}.",
        Feeling.PAIN: "Tell {doctor} about the pain {when}.",
        Feeling.BREATHLESS: "Tell {doctor} you get short of breath {when}.",
        Feeling.LOW: "Tell {doctor} you feel sad {when}.",
        Feeling.WORRIED: "Tell {doctor} you feel worried {when}.",
        Feeling.CANT_SLEEP: "Tell {doctor} you are not sleeping well {when}.",
        Feeling.CRAMPS: "Tell {doctor} about the cramps {when}.",
        Feeling.THIRSTY: "Tell {doctor} you feel very thirsty {when}.",
        Feeling.ACHES: "Tell {doctor} about the muscle aches {when}.",
        Feeling.HEADACHE: "Tell {doctor} about the headache {when}.",
        Feeling.SWOLLEN_ANKLES: "Tell {doctor} about your swollen ankles {when}.",
        Feeling.STOMACH_UPSET: "Tell {doctor} about your upset stomach {when}.",
    },
    "ms": {
        Feeling.DIZZY: "Beritahu {doctor} bahawa anda rasa pening {when}.",
        Feeling.TIRED: "Beritahu {doctor} bahawa anda rasa letih {when}.",
        Feeling.PAIN: "Beritahu {doctor} tentang rasa sakit itu {when}.",
        Feeling.BREATHLESS: "Beritahu {doctor} bahawa anda sesak nafas {when}.",
        Feeling.LOW: "Beritahu {doctor} bahawa anda rasa sedih {when}.",
        Feeling.WORRIED: "Beritahu {doctor} bahawa anda rasa risau {when}.",
        Feeling.CANT_SLEEP: "Beritahu {doctor} bahawa anda susah tidur {when}.",
        Feeling.CRAMPS: "Beritahu {doctor} tentang kejang otot {when}.",
        Feeling.THIRSTY: "Beritahu {doctor} bahawa anda rasa sangat dahaga {when}.",
        Feeling.ACHES: "Beritahu {doctor} tentang sakit otot {when}.",
        Feeling.HEADACHE: "Beritahu {doctor} tentang sakit kepala {when}.",
        Feeling.SWOLLEN_ANKLES: "Beritahu {doctor} tentang buku lali yang bengkak {when}.",
        Feeling.STOMACH_UPSET: "Beritahu {doctor} bahawa perut anda tidak selesa {when}.",
    },
    "zh": {
        Feeling.DIZZY: "告诉{doctor}：您头晕，{when}。",
        Feeling.TIRED: "告诉{doctor}：您觉得累，{when}。",
        Feeling.PAIN: "告诉{doctor}：您身上痛，{when}。",
        Feeling.BREATHLESS: "告诉{doctor}：您气短，{when}。",
        Feeling.LOW: "告诉{doctor}：您心情低落，{when}。",
        Feeling.WORRIED: "告诉{doctor}：您很担心，{when}。",
        Feeling.CANT_SLEEP: "告诉{doctor}：您睡不好，{when}。",
        Feeling.CRAMPS: "告诉{doctor}：您抽筋，{when}。",
        Feeling.THIRSTY: "告诉{doctor}：您很口渴，{when}。",
        Feeling.ACHES: "告诉{doctor}：您肌肉酸痛，{when}。",
        Feeling.HEADACHE: "告诉{doctor}：您头痛，{when}。",
        Feeling.SWOLLEN_ANKLES: "告诉{doctor}：您脚踝肿，{when}。",
        Feeling.STOMACH_UPSET: "告诉{doctor}：您肚子不舒服，{when}。",
    },
}
"""The first thing to mention: his own word, and when, as he answered the one question — the
cloud's own reply, said once, right when he answers (plain words: "today"/"since yesterday" is
true only at that moment). Never used for what a note goes on to say elsewhere: `TELL_ON`."""

# @patient
TELL_ON: Mapping[str, Mapping[Feeling, str]] = {
    "en": {
        Feeling.DIZZY: "Tell {doctor} you felt dizzy on {date}.",
        Feeling.TIRED: "Tell {doctor} you felt tired on {date}.",
        Feeling.PAIN: "Tell {doctor} about the pain on {date}.",
        Feeling.BREATHLESS: "Tell {doctor} you were short of breath on {date}.",
        Feeling.LOW: "Tell {doctor} you felt sad on {date}.",
        Feeling.WORRIED: "Tell {doctor} you felt worried on {date}.",
        Feeling.CANT_SLEEP: "Tell {doctor} you were not sleeping well on {date}.",
        Feeling.CRAMPS: "Tell {doctor} about the cramps on {date}.",
        Feeling.THIRSTY: "Tell {doctor} you felt very thirsty on {date}.",
        Feeling.ACHES: "Tell {doctor} about the muscle aches on {date}.",
        Feeling.HEADACHE: "Tell {doctor} about the headache on {date}.",
        Feeling.SWOLLEN_ANKLES: "Tell {doctor} about your swollen ankles on {date}.",
        Feeling.STOMACH_UPSET: "Tell {doctor} about your upset stomach on {date}.",
    },
    "ms": {
        Feeling.DIZZY: "Beritahu {doctor} bahawa anda rasa pening pada {date}.",
        Feeling.TIRED: "Beritahu {doctor} bahawa anda rasa letih pada {date}.",
        Feeling.PAIN: "Beritahu {doctor} tentang rasa sakit itu pada {date}.",
        Feeling.BREATHLESS: "Beritahu {doctor} bahawa anda sesak nafas pada {date}.",
        Feeling.LOW: "Beritahu {doctor} bahawa anda rasa sedih pada {date}.",
        Feeling.WORRIED: "Beritahu {doctor} bahawa anda rasa risau pada {date}.",
        Feeling.CANT_SLEEP: "Beritahu {doctor} bahawa anda susah tidur pada {date}.",
        Feeling.CRAMPS: "Beritahu {doctor} tentang kejang otot pada {date}.",
        Feeling.THIRSTY: "Beritahu {doctor} bahawa anda rasa sangat dahaga pada {date}.",
        Feeling.ACHES: "Beritahu {doctor} tentang sakit otot pada {date}.",
        Feeling.HEADACHE: "Beritahu {doctor} tentang sakit kepala pada {date}.",
        Feeling.SWOLLEN_ANKLES: "Beritahu {doctor} tentang buku lali yang bengkak pada {date}.",
        Feeling.STOMACH_UPSET: "Beritahu {doctor} bahawa perut anda tidak selesa pada {date}.",
    },
    "zh": {
        Feeling.DIZZY: "告诉{doctor}：您{date}头晕。",
        Feeling.TIRED: "告诉{doctor}：您{date}觉得累。",
        Feeling.PAIN: "告诉{doctor}：您{date}身上痛。",
        Feeling.BREATHLESS: "告诉{doctor}：您{date}气短。",
        Feeling.LOW: "告诉{doctor}：您{date}心情低落。",
        Feeling.WORRIED: "告诉{doctor}：您{date}很担心。",
        Feeling.CANT_SLEEP: "告诉{doctor}：您{date}睡不好。",
        Feeling.CRAMPS: "告诉{doctor}：您{date}抽筋。",
        Feeling.THIRSTY: "告诉{doctor}：您{date}很口渴。",
        Feeling.ACHES: "告诉{doctor}：您{date}肌肉酸痛。",
        Feeling.HEADACHE: "告诉{doctor}：您{date}头痛。",
        Feeling.SWOLLEN_ANKLES: "告诉{doctor}：您{date}脚踝肿。",
        Feeling.STOMACH_UPSET: "告诉{doctor}：您{date}肚子不舒服。",
    },
}
"""The first thing to mention, day-anchored (PR #233 review, plain words rules 2 and 5): a
question row or a brief line is read back on a day that is not the day he answered, so "today"
and "since yesterday" go stale or false. `{date}` is `app.medicines.strings.say_date` on the
day he answered, fixed at compose time — true however long after that it is read. This is what
`compose_note` actually writes to `FeelingNote.lines`; `TELL` above is the cloud's own reply
alone and is never replayed."""

# @patient phrase
WHEN: Mapping[str, Mapping[Answer, str]] = {
    "en": {
        Answer.TODAY: "today",
        Answer.YESTERDAY: "since yesterday",
        Answer.FEW_DAYS: "for a few days now",
        Answer.WEEK_OR_MORE: "for a week or more",
        Answer.MORE: "and that it is worse than yesterday",
        Answer.SAME: "and that it is the same as yesterday",
        Answer.LESS: "and that it is better than yesterday",
        Answer.NO: "today",
    },
    "ms": {
        Answer.TODAY: "hari ini",
        Answer.YESTERDAY: "sejak semalam",
        Answer.FEW_DAYS: "sejak beberapa hari",
        Answer.WEEK_OR_MORE: "sejak seminggu atau lebih",
        Answer.MORE: "dan ia lebih teruk daripada semalam",
        Answer.SAME: "dan ia sama seperti semalam",
        Answer.LESS: "dan ia lebih baik daripada semalam",
        Answer.NO: "hari ini",
    },
    "zh": {
        Answer.TODAY: "今天开始的",
        Answer.YESTERDAY: "从昨天开始",
        Answer.FEW_DAYS: "已经几天了",
        Answer.WEEK_OR_MORE: "已经一个星期或更久了",
        Answer.MORE: "比昨天更厉害",
        Answer.SAME: "和昨天一样",
        Answer.LESS: "比昨天好一点",
        Answer.NO: "今天开始的",
    },
}
"""How the answer completes the line. A no to a question that tells a red variant apart says
only that it is today."""

# @patient
REASON: Mapping[str, Mapping[str, str]] = {
    "en": {
        "new_medicine": "This can come from {medicine}, new since {date}.",
        "reading_trend": "Your last {count} blood pressure numbers went up each time.",
        "visit": "You went to see a doctor on {date}.",
        "discharge": "You came home from hospital on {date}.",
    },
    "ms": {
        "new_medicine": "Ini boleh berlaku kerana {medicine}, yang baru sejak {date}.",
        "reading_trend": "{count} bacaan tekanan darah terakhir anda naik setiap kali.",
        "visit": "Anda berjumpa doktor pada {date}.",
        "discharge": "Anda pulang dari hospital pada {date}.",
    },
    "zh": {
        "new_medicine": "这可能和{medicine}有关，它从{date}起是新的。",
        "reading_trend": "您最近{count}次的血压一次比一次高。",
        "visit": "您{date}看过医生。",
        "discharge": "您{date}从医院回家。",
    },
}
"""The second thing to mention, when the record has one: what the tap was read against. A
medicine line is said only where its licensed monograph lists this feeling, and never without
`DO_NOT_STOP` straight after it; a direction in his blood pressure only where the arithmetic
shows one. Never a condition, never a diagnosis, never an amount."""

# @patient
DO_NOT_STOP: Mapping[str, tuple[str, str]] = {
    "en": ("Do not stop {medicine} yourself.", "Tell {doctor} how you feel."),
    "ms": ("Jangan berhenti makan {medicine} sendiri.", "Beritahu {doctor} apa yang anda rasa."),
    "zh": ("不要自己停{medicine}。", "告诉{doctor}您的感觉。"),
}
"""Said right after a line that names a medicine (#157): the note names a medicine his
feeling can come from, so it says, in the same breath, that he keeps taking it and the doctor
decides. `{doctor}` is the doctor the note names, or "your doctor". Awaiting the clinician's
and the pharmacist's sign-off (docs/trust/clinical-wording-sign-off.md)."""

# @patient
THEN: Mapping[str, Mapping[str, str]] = {
    "en": {
        "for_the_doctor": "Nura will keep this for your visit to {doctor}.",
        "for_the_next_visit": "Nura wrote this down for you to tell {doctor}.",
        "watch": "Nura will ask you again in a week.",
    },
    "ms": {
        "for_the_doctor": "Nura akan simpan ini untuk lawatan anda ke {doctor}.",
        "for_the_next_visit": "Nura sudah tulis ini untuk anda beritahu {doctor}.",
        "watch": "Nura akan tanya anda lagi dalam seminggu.",
    },
    "zh": {
        "for_the_doctor": "Nura 会把这个留到您看{doctor}的时候。",
        "for_the_next_visit": "Nura 记下了这个，让您告诉{doctor}。",
        "watch": "一个星期后，Nura 会再问您。",
    },
}
"""Who does the next thing, and when (docs/plain-words.md rule 7).

`for_the_doctor` names a visit on the spine: the brief and the questions for that visit read
this note (`app.reasoning.visits.questions.feeling_notes_for`, RE-02), so the promise is kept
by code, not just by these words. `for_the_next_visit` is the honest line for when there is no
visit yet to attach the note to — nothing reads an unattached note onto a visit later, so it
never promises one; it says who does the next thing instead (rule 7): he does, when he next
sees a doctor. Changing this promise to match what the code does, rather than building the
code to match an old promise, is RE-02's own finding."""


def catalogue() -> list[tuple[str, str]]:
    """Every template here as (language, line), for the tests that hold them to the rules."""
    found: list[tuple[str, str]] = []
    for code in ("en", "ms", "zh"):
        found.append((code, PROMPT[code]))
        found.extend((code, line) for line in LEADS[code].values())
        found.extend((code, line) for line in QUESTIONS[code].values())
        found.extend((code, line) for line in FINE_LINES[code])
        found.append((code, NOTE_HEADLINE[code]))
        found.extend((code, line) for line in TELL[code].values())
        found.extend((code, line) for line in TELL_ON[code].values())
        found.extend((code, line) for line in REASON[code].values())
        found.extend((code, line) for line in DO_NOT_STOP[code])
        found.extend((code, line) for line in THEN[code].values())
    return found
