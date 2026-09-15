"""The medicine strings: every sentence a patient reads or hears about a medicine.

Each sentence is a template keyed by a monograph rule id from the licensed registry
(`app.drugs`), in English, Malay and Chinese, tagged `@patient` and written to
`docs/plain-words.md`: whole sentences, one idea per line, his names for things — "your blood
pressure tablet", "the water pill" — the chemical name second and small, the doctor's name
every time, no red words, nothing to decode. The registry decides *which* rule applies to a
drug; this file decides only the words. No model writes here, and no line tells him to start,
stop or change a medicine: a dose change is a question for the doctor
(`DOSE_CHANGE`), and so is every interaction (`INTERACTION`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

LANGUAGES = ("en", "ms", "zh")
DEFAULT_LANGUAGE = "en"

Lines = Sequence[str]

# @patient phrase
PLAIN_NAME: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood_pressure_tablet": "your blood pressure tablet",
        "sugar_tablet": "the sugar tablet",
        "cholesterol_tablet": "the cholesterol tablet",
        "blood_thinner_tablet": "the blood thinner tablet",
        "insulin": "your insulin",
        "aspirin": "the aspirin",
        "water_pill": "the water pill",
        "stomach_tablet": "the stomach tablet",
        "joint_tablet": "the joint tablet",
        "pain_tablet": "the pain tablet",
    },
    "ms": {
        "blood_pressure_tablet": "ubat tekanan darah anda",
        "sugar_tablet": "ubat gula",
        "cholesterol_tablet": "ubat kolesterol",
        "blood_thinner_tablet": "ubat cair darah",
        "insulin": "insulin anda",
        "aspirin": "aspirin",
        "water_pill": "pil air",
        "stomach_tablet": "ubat perut",
        "joint_tablet": "ubat sendi",
        "pain_tablet": "ubat sakit",
    },
    "zh": {
        "blood_pressure_tablet": "您的血压药",
        "sugar_tablet": "降糖药",
        "cholesterol_tablet": "降胆固醇药",
        "blood_thinner_tablet": "薄血药",
        "insulin": "您的胰岛素",
        "aspirin": "阿司匹林",
        "water_pill": "去水药",
        "stomach_tablet": "胃药",
        "joint_tablet": "关节药",
        "pain_tablet": "止痛药",
    },
}
"""His name for each medicine, by the monograph's `plain_name_id`."""

# @patient
PURPOSE: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "blood_pressure": ("This is {name}.", "It keeps your blood pressure down."),
        "sugar": ("This is {name}.", "It keeps your sugar down."),
        "cholesterol": ("This is {name}.", "It keeps your cholesterol down."),
        "clots": ("This is {name}.", "It keeps your blood thin, so clots do not form."),
        "heart_protect": ("This is {name}.", "It helps protect your heart."),
        "water": ("This is {name}.", "It takes extra water out of your body."),
        "stomach": ("This is {name}.", "It calms the acid in your stomach."),
        "joints": ("This is {name}.", "It calms your joints."),
        "pain": ("This is {name}.", "It eases pain."),
    },
    "ms": {
        "blood_pressure": ("Ini {name}.", "Ia menjaga tekanan darah anda supaya tidak tinggi."),
        "sugar": ("Ini {name}.", "Ia menjaga gula anda supaya tidak tinggi."),
        "cholesterol": ("Ini {name}.", "Ia menjaga kolesterol anda supaya tidak tinggi."),
        "clots": ("Ini {name}.", "Ia menjaga darah anda cair, supaya tidak berketul."),
        "heart_protect": ("Ini {name}.", "Ia membantu melindungi jantung anda."),
        "water": ("Ini {name}.", "Ia mengeluarkan air lebihan dari badan anda."),
        "stomach": ("Ini {name}.", "Ia menenangkan asid dalam perut anda."),
        "joints": ("Ini {name}.", "Ia menenangkan sendi anda."),
        "pain": ("Ini {name}.", "Ia melegakan sakit."),
    },
    "zh": {
        "blood_pressure": ("这是{name}。", "它让您的血压不会太高。"),
        "sugar": ("这是{name}。", "它让您的血糖不会太高。"),
        "cholesterol": ("这是{name}。", "它让您的胆固醇不会太高。"),
        "clots": ("这是{name}。", "它让您的血不会结块。"),
        "heart_protect": ("这是{name}。", "它帮助保护您的心脏。"),
        "water": ("这是{name}。", "它把身体里多余的水排出去。"),
        "stomach": ("这是{name}。", "它让您胃里的酸少一点。"),
        "joints": ("这是{name}。", "它让您的关节舒服一点。"),
        "pain": ("这是{name}。", "它减轻疼痛。"),
    },
}
"""What it is for, tied to the thing he has a word for, by the monograph's `purpose_id`."""

# @patient phrase
UNIT_WORDS: Mapping[str, Mapping[str, tuple[str, str, str]]] = {
    # (half, one, many) — the amount line is built from these.
    "en": {
        "tablet": ("half a tablet", "1 tablet", "{n} tablets"),
        "capsule": ("half a capsule", "1 capsule", "{n} capsules"),
        "unit": ("half a unit", "1 unit", "{n} units"),
        "ml": ("half a spoon", "1 spoon", "{n} spoons"),
        "puff": ("half a puff", "1 puff", "{n} puffs"),
        "drop": ("half a drop", "1 drop", "{n} drops"),
        "sachet": ("half a sachet", "1 sachet", "{n} sachets"),
    },
    "ms": {
        "tablet": ("setengah biji", "1 biji", "{n} biji"),
        "capsule": ("setengah kapsul", "1 kapsul", "{n} kapsul"),
        "unit": ("setengah unit", "1 unit", "{n} unit"),
        "ml": ("setengah sudu", "1 sudu", "{n} sudu"),
        "puff": ("setengah sedutan", "1 sedutan", "{n} sedutan"),
        "drop": ("setengah titis", "1 titis", "{n} titis"),
        "sachet": ("setengah paket", "1 paket", "{n} paket"),
    },
    "zh": {
        "tablet": ("半片", "1 片", "{n} 片"),
        "capsule": ("半粒", "1 粒", "{n} 粒"),
        "unit": ("半单位", "1 单位", "{n} 单位"),
        "ml": ("半勺", "1 勺", "{n} 勺"),
        "puff": ("半喷", "1 喷", "{n} 喷"),
        "drop": ("半滴", "1 滴", "{n} 滴"),
        "sachet": ("半包", "1 包", "{n} 包"),
    },
}

# @patient phrase
ANCHOR_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {
        "breakfast": "with breakfast",
        "lunch": "with lunch",
        "dinner": "with dinner",
        "bed": "before bed",
    },
    "ms": {
        "breakfast": "bersama sarapan",
        "lunch": "bersama makan tengah hari",
        "dinner": "bersama makan malam",
        "bed": "sebelum tidur",
    },
    "zh": {"breakfast": "早餐时", "lunch": "午餐时", "dinner": "晚餐时", "bed": "睡前"},
}

# @patient
HOW_OFTEN: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "od": ("Take {amount} once a day.", "Take it {anchor1}."),
        "bd": ("Take {amount} 2 times a day.", "Take one {anchor1} and one {anchor2}."),
        "tds": (
            "Take {amount} 3 times a day.",
            "Take one {anchor1}, one {anchor2} and one {anchor3}.",
        ),
        "qds": (
            "Take {amount} 4 times a day.",
            "Take one {anchor1}, one {anchor2}, one {anchor3} and one {anchor4}.",
        ),
        "weekly": ("Take {amount} once a week.", "Take it {anchor1}, on the same day each week."),
        "prn": ("Take {amount} only when you need it.",),
    },
    "ms": {
        "od": ("Ambil {amount} sekali sehari.", "Ambil {anchor1}."),
        "bd": ("Ambil {amount} 2 kali sehari.", "Ambil satu {anchor1} dan satu {anchor2}."),
        "tds": (
            "Ambil {amount} 3 kali sehari.",
            "Ambil satu {anchor1}, satu {anchor2} dan satu {anchor3}.",
        ),
        "qds": (
            "Ambil {amount} 4 kali sehari.",
            "Ambil satu {anchor1}, satu {anchor2}, satu {anchor3} dan satu {anchor4}.",
        ),
        "weekly": (
            "Ambil {amount} sekali seminggu.",
            "Ambil {anchor1}, pada hari yang sama setiap minggu.",
        ),
        "prn": ("Ambil {amount} hanya bila anda perlu.",),
    },
    "zh": {
        "od": ("每天吃一次，{amount}。", "{anchor1}吃。"),
        "bd": ("每天吃 2 次，每次{amount}。", "{anchor1}吃一次，{anchor2}吃一次。"),
        "tds": ("每天吃 3 次，每次{amount}。", "{anchor1}、{anchor2}、{anchor3}各吃一次。"),
        "qds": (
            "每天吃 4 次，每次{amount}。",
            "{anchor1}、{anchor2}、{anchor3}、{anchor4}各吃一次。",
        ),
        "weekly": ("每星期吃一次，{amount}。", "{anchor1}吃，每星期同一天。"),
        "prn": ("需要时才吃，每次{amount}。",),
    },
}
"""How often, with one slot per moment of his day: whole lines, never joined at run time."""

# @patient
FOOD: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "with_or_without_food": ("Food does not matter for this one.",),
        "with_meals": ("Take it with food.",),
        "with_food": ("Take it with food.",),
        "before_breakfast": ("Take it before breakfast, before any food.",),
        "with_breakfast": ("Take it with breakfast.",),
        "same_time_each_day": ("Take it at the same time every day.",),
        "morning": ("Take it in the morning, so you are not up at night.",),
        "once_a_week": ("This one is once a week, always on the same day.",),
    },
    "ms": {
        "with_or_without_food": ("Makan atau tidak, tidak mengapa untuk ubat ini.",),
        "with_meals": ("Ambil bersama makanan.",),
        "with_food": ("Ambil bersama makanan.",),
        "before_breakfast": ("Ambil sebelum sarapan, semasa perut kosong.",),
        "with_breakfast": ("Ambil bersama sarapan.",),
        "same_time_each_day": ("Ambil pada waktu yang sama setiap hari.",),
        "morning": ("Ambil pada waktu pagi, supaya anda tidak terjaga malam.",),
        "once_a_week": ("Ubat ini sekali seminggu, sentiasa pada hari yang sama.",),
    },
    "zh": {
        "with_or_without_food": ("这个药吃饭前后都可以。",),
        "with_meals": ("和食物一起吃。",),
        "with_food": ("和食物一起吃。",),
        "before_breakfast": ("早餐前空腹吃。",),
        "with_breakfast": ("和早餐一起吃。",),
        "same_time_each_day": ("每天在同一个时间吃。",),
        "morning": ("早上吃，晚上就不用起来。",),
        "once_a_week": ("这个药一星期一次，每次同一天。",),
    },
}

# @patient
WATCH_OUT: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "swollen_ankles": ("If your ankles swell, tell {doctor}.",),
        "dizzy_standing": (
            "If you feel dizzy when you stand up, sit down first.",
            "Then tell {doctor}.",
        ),
        "tummy_upset": (
            "If your stomach is upset, take it with food.",
            "If it goes on, tell {doctor}.",
        ),
        "muscle_ache": ("If your muscles ache for no reason, tell {doctor}.",),
        "bleeding_signs": ("If you bruise easily or bleed, tell {doctor} today.",),
        "black_stools": (
            "If your stools turn black, this one we do not wait for.",
            "Call {doctor} today.",
        ),
        "shaky_sweaty": (
            "If you feel shaky and sweaty, take something sweet now.",
            "Then tell {doctor}.",
        ),
        "mouth_sores_fever": ("If you get mouth sores or a fever, call {doctor} today.",),
        "cramps": ("If you get leg cramps, tell {doctor}.",),
    },
    "ms": {
        "swollen_ankles": ("Jika buku lali anda bengkak, beritahu {doctor}.",),
        "dizzy_standing": (
            "Jika anda pening semasa berdiri, duduk dahulu.",
            "Kemudian beritahu {doctor}.",
        ),
        "tummy_upset": (
            "Jika perut anda tidak selesa, ambil bersama makanan.",
            "Jika berterusan, beritahu {doctor}.",
        ),
        "muscle_ache": ("Jika otot anda sakit tanpa sebab, beritahu {doctor}.",),
        "bleeding_signs": ("Jika anda mudah lebam atau berdarah, beritahu {doctor} hari ini.",),
        "black_stools": (
            "Jika najis anda menjadi hitam, yang ini kita tidak tunggu.",
            "Telefon {doctor} hari ini.",
        ),
        "shaky_sweaty": (
            "Jika anda menggigil dan berpeluh, ambil sesuatu yang manis sekarang.",
            "Kemudian beritahu {doctor}.",
        ),
        "mouth_sores_fever": ("Jika mulut anda luka atau anda demam, telefon {doctor} hari ini.",),
        "cramps": ("Jika kaki anda kejang, beritahu {doctor}.",),
    },
    "zh": {
        "swollen_ankles": ("如果脚踝肿了，告诉{doctor}。",),
        "dizzy_standing": ("如果站起来头晕，先坐下。", "然后告诉{doctor}。"),
        "tummy_upset": ("如果胃不舒服，和食物一起吃。", "如果一直不舒服，告诉{doctor}。"),
        "muscle_ache": ("如果肌肉无缘无故地痛，告诉{doctor}。",),
        "bleeding_signs": ("如果容易瘀青或流血，今天就告诉{doctor}。",),
        "black_stools": ("如果大便变黑，这个我们不等。", "今天就打电话给{doctor}。"),
        "shaky_sweaty": ("如果发抖又出汗，马上吃点甜的。", "然后告诉{doctor}。"),
        "mouth_sores_fever": ("如果口腔溃疡或发烧，今天就打电话给{doctor}。",),
        "cramps": ("如果小腿抽筋，告诉{doctor}。",),
    },
}

# @patient
AVOID: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "grapefruit": ("Grapefruit does not go with {name}.",),
        "alcohol": ("Alcohol does not go with {name}.",),
        "painkillers_ask": ("Ask the pharmacist before you buy a painkiller.",),
        "leafy_greens_steady": ("Eat about the same amount of green vegetables each week.",),
        "tcm_supplements_ask": ("Ask {doctor} before you take herbal medicine or supplements.",),
        "skipping_meals": ("Have your meals as usual while you take {name}.",),
        "salt_substitutes": ("Ask the pharmacist before you use a salt substitute.",),
        "other_paracetamol": (
            "Ask the pharmacist before you take another pain tablet.",
            "Too much in one day is not safe.",
        ),
        "folic_acid_ask": ("Ask {doctor} which day to take your folic acid.",),
    },
    "ms": {
        "grapefruit": ("Limau gedang tidak sesuai dengan {name}.",),
        "alcohol": ("Arak tidak sesuai dengan {name}.",),
        "painkillers_ask": ("Tanya ahli farmasi sebelum anda beli ubat sakit.",),
        "leafy_greens_steady": ("Makan sayur hijau lebih kurang sama banyak setiap minggu.",),
        "tcm_supplements_ask": ("Tanya {doctor} sebelum anda ambil ubat herba atau suplemen.",),
        "skipping_meals": ("Makan seperti biasa semasa anda ambil {name}.",),
        "salt_substitutes": ("Tanya ahli farmasi sebelum anda guna garam ganti.",),
        "other_paracetamol": (
            "Tanya ahli farmasi sebelum anda ambil ubat sakit lain.",
            "Terlalu banyak dalam satu hari tidak selamat.",
        ),
        "folic_acid_ask": ("Tanya {doctor} hari mana untuk ambil asid folik anda.",),
    },
    "zh": {
        "grapefruit": ("西柚和{name}不能一起吃。",),
        "alcohol": ("酒和{name}不能一起吃。",),
        "painkillers_ask": ("买止痛药之前，先问药剂师。",),
        "leafy_greens_steady": ("每星期吃差不多一样多的绿叶菜。",),
        "tcm_supplements_ask": ("吃中药或补品之前，先问{doctor}。",),
        "skipping_meals": ("吃{name}的时候，三餐照常吃。",),
        "salt_substitutes": ("用代盐之前，先问药剂师。",),
        "other_paracetamol": ("吃别的止痛药之前，先问药剂师。", "一天吃太多不安全。"),
        "folic_acid_ask": ("问{doctor}哪一天吃叶酸。",),
    },
}

# @patient
IF_FORGOTTEN: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "take_now_unless_next_is_near": (
            "If you forgot, take it when you remember.",
            "If the next one is soon, wait for the next one.",
            "Never take 2 at once.",
        ),
        "skip_and_take_next": (
            "If you forgot, leave it.",
            "Take the next one at the usual time.",
            "Never take 2 at once.",
        ),
        "same_day_or_tell_clinic": (
            "If you forgot and it is still the same day, take it now.",
            "If the day has passed, leave it and tell {doctor}.",
            "Never take 2 at once.",
        ),
        "ask_before_extra": (
            "If you forgot your insulin, call {doctor} before you take any.",
            "Do not take extra to catch up.",
        ),
        "skip_if_late_in_day": (
            "If you forgot in the morning, take it by lunch.",
            "After lunch, leave it until tomorrow.",
        ),
        "weekly_ask_if_late": (
            "If you forgot your weekly tablet, take it within 2 days.",
            "Later than that, leave it and ask {doctor}.",
        ),
        "when_needed_none": ("This one is only when you need it.", "There is nothing to catch up."),
    },
    "ms": {
        "take_now_unless_next_is_near": (
            "Jika anda terlupa, ambil apabila anda teringat.",
            "Jika yang seterusnya sudah dekat, tunggu yang seterusnya.",
            "Jangan sekali-kali ambil dua serentak.",
        ),
        "skip_and_take_next": (
            "Jika anda terlupa, biarkan.",
            "Ambil yang seterusnya pada waktu biasa.",
            "Jangan sekali-kali ambil dua serentak.",
        ),
        "same_day_or_tell_clinic": (
            "Jika anda terlupa dan masih hari yang sama, ambil sekarang.",
            "Jika hari sudah berlalu, biarkan dan beritahu {doctor}.",
            "Jangan sekali-kali ambil dua serentak.",
        ),
        "ask_before_extra": (
            "Jika anda terlupa insulin anda, telefon {doctor} sebelum anda ambil.",
            "Jangan ambil lebih untuk ganti.",
        ),
        "skip_if_late_in_day": (
            "Jika anda terlupa pada waktu pagi, ambil sebelum makan tengah hari.",
            "Selepas itu, biarkan sehingga esok.",
        ),
        "weekly_ask_if_late": (
            "Jika anda terlupa ubat mingguan anda, ambil dalam masa dua hari.",
            "Lewat daripada itu, biarkan dan tanya {doctor}.",
        ),
        "when_needed_none": ("Ubat ini hanya bila anda perlu.", "Tiada apa yang perlu diganti."),
    },
    "zh": {
        "take_now_unless_next_is_near": (
            "如果忘了，想起来就吃。",
            "如果下一次快到了，就等下一次。",
            "千万不要一次吃两份。",
        ),
        "skip_and_take_next": (
            "如果忘了，就不吃了。",
            "下一次照平常的时间吃。",
            "千万不要一次吃两份。",
        ),
        "same_day_or_tell_clinic": (
            "如果忘了，还是同一天，现在就吃。",
            "如果已经过了那一天，就不吃了，告诉{doctor}。",
            "千万不要一次吃两份。",
        ),
        "ask_before_extra": ("如果忘了打胰岛素，先打电话给{doctor}再打。", "不要多打来补。"),
        "skip_if_late_in_day": ("如果早上忘了，午餐前吃。", "午餐后就不吃了，等明天。"),
        "weekly_ask_if_late": ("如果忘了每星期的药，两天内吃。", "超过两天就不吃了，问{doctor}。"),
        "when_needed_none": ("这个药需要时才吃。", "不用补。"),
    },
}

# @patient
BOUNDARY: Mapping[str, Lines] = {
    "en": (
        "This helps you take what {doctor} prescribed.",
        "Ask {doctor} or the pharmacist before you change anything.",
    ),
    "ms": (
        "Ini membantu anda ambil apa yang {doctor} beri.",
        "Tanya {doctor} atau ahli farmasi sebelum anda ubah apa-apa.",
    ),
    "zh": ("这帮您按{doctor}开的药吃。", "改任何东西之前，先问{doctor}或药剂师。"),
}
"""The boundary on every medicine card (module doc, section 9)."""

# @patient
DOSE_CHANGE: Mapping[str, Lines] = {
    "en": (
        "Your new pack says a different amount from before.",
        "Ask {doctor} about the new amount.",
    ),
    "ms": (
        "Pek baru anda menyatakan jumlah yang berbeza daripada dahulu.",
        "Tanya {doctor} tentang jumlah baru itu.",
    ),
    "zh": ("您的新药盒写的分量和以前不一样。", "问{doctor}新的分量。"),
}
"""A dose change is a question for the doctor. Nothing here tells him which amount to take."""

# @patient
INTERACTION: Mapping[str, Mapping[str, Lines]] = {
    "en": {
        "bleeding_risk": (
            "Ask {doctor} about taking {a} and {b} together.",
            "Together they can make you bleed more easily.",
        ),
        "bleeding_check": (
            "Ask {doctor} about taking {a} and {b} together.",
            "Together they can change your blood test.",
        ),
        "methotrexate_levels": (
            "Ask {doctor} about taking {a} and {b} together.",
            "Together they can be too strong for you.",
        ),
        "low_pressure_kidney": (
            "Ask {doctor} about taking {a} and {b} together.",
            "Together they can make you dizzy when you stand up.",
        ),
        "low_sugar": (
            "Ask {doctor} about taking {a} and {b} together.",
            "Together they can send your sugar too low.",
        ),
        "same_kind_twice": (
            "Ask {doctor} whether you need both {a} and {b}.",
            "They are the same kind of medicine.",
        ),
    },
    "ms": {
        "bleeding_risk": (
            "Tanya {doctor} tentang mengambil {a} dan {b} bersama.",
            "Bersama, ia boleh membuat anda mudah berdarah.",
        ),
        "bleeding_check": (
            "Tanya {doctor} tentang mengambil {a} dan {b} bersama.",
            "Bersama, ia boleh mengubah ujian darah anda.",
        ),
        "methotrexate_levels": (
            "Tanya {doctor} tentang mengambil {a} dan {b} bersama.",
            "Bersama, ia boleh menjadi terlalu kuat untuk anda.",
        ),
        "low_pressure_kidney": (
            "Tanya {doctor} tentang mengambil {a} dan {b} bersama.",
            "Bersama, ia boleh membuat anda pening semasa berdiri.",
        ),
        "low_sugar": (
            "Tanya {doctor} tentang mengambil {a} dan {b} bersama.",
            "Bersama, ia boleh membuat gula anda terlalu rendah.",
        ),
        "same_kind_twice": (
            "Tanya {doctor} sama ada anda perlukan kedua-dua {a} dan {b}.",
            "Ia ubat jenis yang sama.",
        ),
    },
    "zh": {
        "bleeding_risk": ("问{doctor}，{a}和{b}可以一起吃吗。", "一起吃会更容易流血。"),
        "bleeding_check": ("问{doctor}，{a}和{b}可以一起吃吗。", "一起吃会影响您的验血结果。"),
        "methotrexate_levels": ("问{doctor}，{a}和{b}可以一起吃吗。", "一起吃对您可能太强。"),
        "low_pressure_kidney": ("问{doctor}，{a}和{b}可以一起吃吗。", "一起吃站起来会头晕。"),
        "low_sugar": ("问{doctor}，{a}和{b}可以一起吃吗。", "一起吃血糖会太低。"),
        "same_kind_twice": ("问{doctor}，{a}和{b}两个都需要吗。", "它们是同一类的药。"),
    },
}
"""Every interaction the licensed data flags, as a question for the doctor with the two
medicines named in his words and one line on why."""

# @patient
COUNT: Mapping[str, Lines] = {
    "en": ("You have {amount} of {name} left.", "That is about {days} days."),
    "ms": ("Anda ada {amount} {name} lagi.", "Itu lebih kurang {days} hari."),
    "zh": ("{name}还剩{amount}。", "大概够{days}天。"),
}
"""The running count, in his words. The second line is left out for a when-needed medicine."""

# @patient
REORDER: Mapping[str, Lines] = {
    "en": ("{name} runs out on {date}.", "Ask your family to order more."),
    "ms": ("{name} akan habis pada {date}.", "Minta keluarga anda pesan lagi."),
    "zh": ("{name}到{date}就吃完了。", "请家人再订。"),
}
"""The reorder card, at the threshold. Who does the next thing: the family."""

# @patient
REORDER_ACTIONS: Mapping[str, Mapping[str, str]] = {
    "en": {"ask_to_order": "Ask the family to order.", "i_have_more": "I have more at home."},
    "ms": {"ask_to_order": "Minta keluarga pesan.", "i_have_more": "Saya ada lagi di rumah."},
    "zh": {"ask_to_order": "请家人订。", "i_have_more": "我家里还有。"},
}

# @patient phrase
ORDER_TASK: Mapping[str, str] = {
    "en": "order more of {medicine}",
    "ms": "pesan lagi {medicine}",
    "zh": "再订{medicine}",
}
"""The task on the family's list when he taps "Ask the family to order." (E04-05): a label in
his words, since it reaches him in the digest and on his trail."""

# @patient
ASKED_TO_ORDER: Mapping[str, str] = {
    "en": "Nura asked {who} to order more of {medicine}.",
    "ms": "Nura minta {who} pesan lagi {medicine}.",
    "zh": "Nura已请{who}再订{medicine}。",
}
"""What he reads after the tap: who does the next thing."""

# @patient
KNOWS_NOW: Mapping[str, str] = {
    "en": "{who} knows now.",
    "ms": "{who} sudah tahu.",
    "zh": "{who}已经知道了。",
}
"""Under it, when his chief was told and is not the one asked."""

# @patient
REORDER_NOTICE: Mapping[str, Lines] = {
    "en": ("{patient} asked the family to order more medicine.", "It is on the family's list."),
    "ms": ("{patient} minta keluarga pesan lagi ubat.", "Ia ada dalam senarai keluarga."),
    "zh": ("{patient}请家人再订药。", "这件事在家人的清单上。"),
}
"""The notice to his chief after he asks (E04-05). No medicine is named here: the task on
the family's list names it, and the notice is read wherever a channel delivers it."""

# @patient headline
TAKEN: Mapping[str, str] = {"en": "Taken", "ms": "Sudah ambil", "zh": "吃了"}
"""The one button on a dose card (glossary: adherence is "Taken")."""

# @patient headline
NOW_WORDS: Mapping[str, Mapping[str, tuple[str, str]]] = {
    "en": {
        "breakfast": ("medicine with breakfast", "medicines with breakfast"),
        "lunch": ("medicine with lunch", "medicines with lunch"),
        "dinner": ("medicine with dinner", "medicines with dinner"),
        "bed": ("medicine before bed", "medicines before bed"),
    },
    "ms": {
        "breakfast": ("ubat bersama sarapan", "ubat bersama sarapan"),
        "lunch": ("ubat bersama makan tengah hari", "ubat bersama makan tengah hari"),
        "dinner": ("ubat bersama makan malam", "ubat bersama makan malam"),
        "bed": ("ubat sebelum tidur", "ubat sebelum tidur"),
    },
    "zh": {
        "breakfast": ("种药，早餐时吃", "种药，早餐时吃"),
        "lunch": ("种药，午餐时吃", "种药，午餐时吃"),
        "dinner": ("种药，晚餐时吃", "种药，晚餐时吃"),
        "bed": ("种药，睡前吃", "种药，睡前吃"),
    },
}
"""The words under the one big number on his Today (the hero): what the number counts, for
one and for more than one. The number is his count; the words are never assembled from it."""

# @patient
DOSE_CARD: Mapping[str, str] = {
    "en": "Take {amount} of {name} {anchor}.",
    "ms": "Ambil {amount} {name} {anchor}.",
    "zh": "{anchor}吃{amount}{name}。",
}
"""One dose card at one anchor of his day."""

# @patient
SOURCE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "label": "This comes from the label you kept on {date}.",
        "typed": "This comes from what was typed in on {date}.",
    },
    "ms": {
        "label": "Ini daripada label yang anda simpan pada {date}.",
        "typed": "Ini daripada apa yang ditaip pada {date}.",
    },
    "zh": {
        "label": "这来自您在{date}保存的标签。",
        "typed": "这来自{date}输入的内容。",
    },
}
"""Where a medicine line came from, and on which day: the source line under every card that
shows it — the label he kept (a photo is behind the line) or what was typed in."""

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}
"""When the label named no doctor."""

DAY_NAMES: Mapping[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ms": ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
}
MONTH_NAMES: Mapping[str, tuple[str, ...]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "ms": (
        "Januari",
        "Februari",
        "Mac",
        "April",
        "Mei",
        "Jun",
        "Julai",
        "Ogos",
        "September",
        "Oktober",
        "November",
        "Disember",
    ),
    "zh": ("1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"),
}


def language_of(asked: str | None) -> str:
    """The language the words come in: one of ours, or English when it is not."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def say_date(day: date, language: str) -> str:
    """'Monday 29 September', never 'the 29th' (plain words, rule 5)."""
    weekday = DAY_NAMES[language][day.weekday()]
    month = MONTH_NAMES[language][day.month - 1]
    if language == "zh":
        return f"{month}{day.day}日{weekday}"
    return f"{weekday} {day.day} {month}"


def say_amount(amount: float, unit: str, language: str) -> str:
    """'half a tablet', '1 tablet', '2 tablets': digits, small and few."""
    half, one, many = UNIT_WORDS[language][unit]
    if amount == 0.5:
        return half
    if amount == 1:
        return one
    number = int(amount) if float(amount).is_integer() else amount
    return many.format(n=number)


def say_doctor(prescriber: str | None, language: str) -> str:
    return prescriber if prescriber else YOUR_DOCTOR[language]


def anchor_slots(anchors: Sequence[str], language: str) -> dict[str, str]:
    """`{anchor1}`, `{anchor2}`… for the HOW_OFTEN line: his words for each moment."""
    return {
        f"anchor{index}": ANCHOR_WORDS[language][anchor]
        for index, anchor in enumerate(anchors, start=1)
    }


def fill(lines: Lines, **values: str) -> list[str]:
    return [line.format(**values) for line in lines]


def catalogue() -> list[str]:
    """Every template in this file, in every language, for the plain-words check."""
    found: list[str] = []
    for table in (PURPOSE, HOW_OFTEN, FOOD, WATCH_OUT, AVOID, IF_FORGOTTEN, INTERACTION):
        for by_id in table.values():
            for lines in by_id.values():
                found.extend(lines)
    for lines_by_language in (BOUNDARY, DOSE_CHANGE, COUNT, REORDER):
        for lines in lines_by_language.values():
            found.extend(lines)
    for words in (TAKEN, DOSE_CARD):
        found.extend(words.values())
    for actions in REORDER_ACTIONS.values():
        found.extend(actions.values())
    for sources in SOURCE.values():
        found.extend(sources.values())
    return found
