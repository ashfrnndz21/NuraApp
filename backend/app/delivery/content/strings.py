"""The content library's curated fixture words, in his languages, tagged for `make plain-words`.

This is a small, realistic, curated set for each feature, in Singapore and Malaysia, in
English, Malay and Chinese (docs/design-direction.md). Nothing here names a real
organisation, phone number or address: entries are deliberately generic, and a real
deployment's live source of events and services for a person's own area is an external
dependency (the feature table in docs/design-direction.md says so). Every line is a whole
sentence, checked against docs/plain-words.md like any other patient string, and every
English line has a Malay and a Chinese twin under the same key (`make language`).

`TITLES`, `SUMMARIES` and `BODY` are keyed by item key, the same key `catalogue.ITEMS` uses
to say what region, language-independent slug, content type and category the words belong
to; `app.delivery.content.fixtures` reads all four into the `NewContentItem` rows
`service.seed_content` writes.
"""

from __future__ import annotations

from collections.abc import Mapping

# @patient headline
TITLES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "activity_chair_exercise": "Gentle morning stretches",
        "activity_tai_chi": "Tai chi in the park",
        "activity_tea_chat": "A tea chat for old friends",
        "service_home_nursing": "A nurse who visits your home",
        "service_physio": "Help to move and get stronger",
        "service_meal_delivery": "A hot meal at your door",
        "service_transport": "A ride to see the doctor",
        "resource_falls": "Falls at home: 3 easy checks",
        "resource_doctor_visit": "Talking to your doctor: what to bring",
        "resource_heat": "Staying cool on a hot day",
        "event_market": "A market day near you",
        "volunteer_reading": "Read to children at the library",
        "volunteer_meals": "Deliver a hot meal to someone near you",
        "support_caregivers": "Support for people caring for a parent",
        "support_stroke": "Support after a stroke",
    },
    "ms": {
        "activity_chair_exercise": "Regangan lembut pada waktu pagi",
        "activity_tai_chi": "Tai chi di taman",
        "activity_tea_chat": "Sembang teh untuk kawan lama",
        "service_home_nursing": "Jururawat yang melawat rumah anda",
        "service_physio": "Bantuan untuk bergerak dan menjadi lebih kuat",
        "service_meal_delivery": "Makanan panas di depan pintu anda",
        "service_transport": "Tumpangan untuk berjumpa doktor",
        "resource_falls": "Terjatuh di rumah: 3 semakan mudah",
        "resource_doctor_visit": "Berjumpa doktor anda: apa yang perlu dibawa",
        "resource_heat": "Kekal sejuk pada hari panas",
        "event_market": "Hari pasar berhampiran anda",
        "volunteer_reading": "Membaca untuk kanak-kanak di perpustakaan",
        "volunteer_meals": "Menghantar makanan panas kepada seseorang berhampiran anda",
        "support_caregivers": "Sokongan untuk mereka yang menjaga ibu bapa",
        "support_stroke": "Sokongan selepas strok",
    },
    "zh": {
        "activity_chair_exercise": "轻柔的晨间伸展",
        "activity_tai_chi": "公园太极",
        "activity_tea_chat": "老朋友的茶叙",
        "service_home_nursing": "上门探访的护士",
        "service_physio": "帮助您活动并增强体力",
        "service_meal_delivery": "送到家门口的热食",
        "service_transport": "送您去看医生的车",
        "resource_falls": "居家跌倒:3个简单检查",
        "resource_doctor_visit": "看医生时:该带些什么",
        "resource_heat": "炎热天气保持凉爽",
        "event_market": "您附近的市集日",
        "volunteer_reading": "在图书馆为孩子读故事",
        "volunteer_meals": "为附近的人送一份热食",
        "support_caregivers": "为照顾父母者提供的支持",
        "support_stroke": "中风后的支持",
    },
}

# @patient
SUMMARIES: Mapping[str, Mapping[str, str]] = {
    "en": {
        "activity_chair_exercise": "A slow class of seated stretches, for older bodies.",
        "activity_tai_chi": "Slow, gentle moves that you do standing up.",
        "activity_tea_chat": "You meet others, and share a cup of tea.",
        "service_home_nursing": "She checks on you and helps with your care.",
        "service_physio": "Someone who helps you move, a little more each week.",
        "service_meal_delivery": "You get good food, with no cooking to do.",
        "service_transport": "A car that takes you to see the doctor.",
        "resource_falls": "Small changes that make your home safer.",
        "resource_doctor_visit": "A short list, so nothing is forgotten.",
        "resource_heat": "Small steps that keep you safe in the heat.",
        "event_market": "Fresh food and a chance to walk and talk.",
        "volunteer_reading": "You read to children for an hour a week.",
        "volunteer_meals": "You bring one hot meal to one person, once a week.",
        "support_caregivers": "Talk with others who look after a parent too.",
        "support_stroke": "Talk with others who are finding their way back.",
    },
    "ms": {
        "activity_chair_exercise": "Kelas regangan perlahan sambil duduk, untuk badan yang lebih tua.",
        "activity_tai_chi": "Pergerakan perlahan dan lembut yang dilakukan sambil berdiri.",
        "activity_tea_chat": "Anda berjumpa orang lain, dan berkongsi secawan teh.",
        "service_home_nursing": "Dia menyemak keadaan anda dan membantu penjagaan anda.",
        "service_physio": "Seseorang yang membantu anda bergerak, sedikit demi sedikit setiap minggu.",
        "service_meal_delivery": "Anda mendapat makanan yang baik, tanpa perlu memasak.",
        "service_transport": "Sebuah kereta yang menghantar anda berjumpa doktor.",
        "resource_falls": "Perubahan kecil yang menjadikan rumah anda lebih selamat.",
        "resource_doctor_visit": "Senarai ringkas, supaya tiada apa yang terlupa.",
        "resource_heat": "Langkah kecil yang menjaga keselamatan anda dalam cuaca panas.",
        "event_market": "Makanan segar, dan peluang untuk berjalan serta berbual.",
        "volunteer_reading": "Anda membaca untuk kanak-kanak selama satu jam seminggu.",
        "volunteer_meals": "Anda menghantar satu makanan panas kepada seorang, sekali seminggu.",
        "support_caregivers": "Berbual dengan mereka yang turut menjaga ibu bapa mereka.",
        "support_stroke": "Berbual dengan mereka yang turut dalam perjalanan pemulihan.",
    },
    "zh": {
        "activity_chair_exercise": "为年长者设计的缓慢坐式伸展班。",
        "activity_tai_chi": "站着进行的缓慢柔和动作。",
        "activity_tea_chat": "您与他人见面,一起喝杯茶。",
        "service_home_nursing": "她会查看您的状况,并协助照顾您。",
        "service_physio": "有人帮助您活动,每周进步一点点。",
        "service_meal_delivery": "您可以吃到好食物,不必自己煮。",
        "service_transport": "有车送您去看医生。",
        "resource_falls": "小小的改变,让您的家更安全。",
        "resource_doctor_visit": "一份简短清单,以免遗漏。",
        "resource_heat": "一些小方法,让您在炎热中保持安全。",
        "event_market": "新鲜的食物,还有散步聊天的机会。",
        "volunteer_reading": "您每周花一小时为孩子读故事。",
        "volunteer_meals": "您每周为一人送一次热食。",
        "support_caregivers": "与其他同样在照顾父母的人交流。",
        "support_stroke": "与正在康复路上的人交流。",
    },
}

# @patient
BODY: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "en": {
        "activity_chair_exercise": (
            "It meets every Monday morning, at 9.",
            "Sit or stand, whatever feels right for your body.",
            "Wear soft shoes and bring a bottle of water.",
        ),
        "activity_chair_exercise_my": (
            "It meets every Tuesday morning, at 9.",
            "Sit or stand, whatever feels right for your body.",
            "Wear soft shoes and bring a bottle of water.",
        ),
        "activity_tai_chi": (
            "It meets every Wednesday morning, at 8.",
            "You can join standing up or sitting down.",
            "Wear soft shoes and bring a bottle of water.",
        ),
        "activity_tea_chat": (
            "It meets every Thursday afternoon, at 3.",
            "New faces are always welcome.",
            "There is no cost to join.",
        ),
        "service_home_nursing": (
            "She checks your blood pressure and your tablets.",
            "Visits are booked in advance, for a day that suits you.",
        ),
        "service_physio": (
            "He comes to your home, or you go to him.",
            "Wear loose clothes that let you move.",
        ),
        "service_meal_delivery": (
            "A hot meal is brought to your door each day.",
            "Tell them what you cannot eat, and they will listen.",
        ),
        "service_transport": (
            "The driver waits, then brings you home again.",
            "Book the ride the day before you need it.",
        ),
        "resource_falls": (
            "Fix any loose mats, and keep the floor clear.",
            "Add a light near the stairs and the bathroom.",
            "Keep a phone close to where you sit.",
        ),
        "resource_doctor_visit": (
            "Bring your tablets and your blood pressure book.",
            "Write your questions down before you go.",
        ),
        "resource_heat": (
            "Drink water often, even when you are not thirsty.",
            "Rest indoors during the hottest part of the day.",
        ),
        "event_market_sg": ("It is held every Saturday morning.", "Bring a bag and take your time."),
        "event_market_my": ("It is held every Sunday morning.", "Bring a bag and take your time."),
        "volunteer_reading": (
            "Anyone can help.",
            "You need no training, just an hour to spare.",
        ),
        "volunteer_meals": (
            "A short round, close to where you live.",
            "You need no training, just an hour to spare.",
        ),
        "support_group": ("It meets once a month, in the evening.", "Family members are welcome to come too."),
    },
    "ms": {
        "activity_chair_exercise": (
            "Ia diadakan setiap pagi Isnin, pada jam 9.",
            "Duduk atau berdiri, ikut apa yang selesa untuk badan anda.",
            "Pakai kasut lembut dan bawa sebotol air.",
        ),
        "activity_chair_exercise_my": (
            "Ia diadakan setiap pagi Selasa, pada jam 9.",
            "Duduk atau berdiri, ikut apa yang selesa untuk badan anda.",
            "Pakai kasut lembut dan bawa sebotol air.",
        ),
        "activity_tai_chi": (
            "Ia diadakan setiap pagi Rabu, pada jam 8.",
            "Anda boleh menyertai sambil berdiri atau duduk.",
            "Pakai kasut lembut dan bawa sebotol air.",
        ),
        "activity_tea_chat": (
            "Ia diadakan setiap petang Khamis, pada jam 3.",
            "Wajah baharu sentiasa dialu-alukan.",
            "Tiada bayaran untuk menyertai.",
        ),
        "service_home_nursing": (
            "Dia menyemak tekanan darah dan ubat anda.",
            "Lawatan ditempah lebih awal, pada hari yang sesuai untuk anda.",
        ),
        "service_physio": (
            "Dia datang ke rumah anda, atau anda pergi berjumpa dia.",
            "Pakai pakaian longgar yang membolehkan anda bergerak.",
        ),
        "service_meal_delivery": (
            "Makanan panas dihantar ke pintu anda setiap hari.",
            "Beritahu mereka makanan yang anda tidak boleh makan, dan mereka akan ambil kira.",
        ),
        "service_transport": (
            "Pemandu akan menunggu, kemudian menghantar anda pulang.",
            "Tempah tumpangan sehari sebelum anda memerlukannya.",
        ),
        "resource_falls": (
            "Betulkan tikar yang longgar, dan pastikan lantai bersih daripada halangan.",
            "Tambah lampu berhampiran tangga dan bilik air.",
            "Letakkan telefon berhampiran tempat anda duduk.",
        ),
        "resource_doctor_visit": (
            "Bawa ubat anda dan buku tekanan darah anda.",
            "Tulis soalan anda sebelum pergi.",
        ),
        "resource_heat": (
            "Minum air dengan kerap, walaupun anda tidak dahaga.",
            "Berehat di dalam rumah pada waktu paling panas.",
        ),
        "event_market_sg": ("Ia diadakan setiap pagi Sabtu.", "Bawa beg, dan tidak perlu tergesa-gesa."),
        "event_market_my": ("Ia diadakan setiap pagi Ahad.", "Bawa beg, dan tidak perlu tergesa-gesa."),
        "volunteer_reading": (
            "Sesiapa sahaja boleh membantu.",
            "Anda tidak memerlukan latihan, hanya satu jam masa lapang.",
        ),
        "volunteer_meals": (
            "Satu pusingan pendek, berhampiran tempat tinggal anda.",
            "Anda tidak memerlukan latihan, hanya satu jam masa lapang.",
        ),
        "support_group": (
            "Ia diadakan sekali sebulan, pada waktu petang.",
            "Ahli keluarga juga dialu-alukan untuk hadir.",
        ),
    },
    "zh": {
        "activity_chair_exercise": (
            "每星期一早上9点举行。",
            "坐着或站着都可以,选择您身体觉得舒服的方式。",
            "穿软鞋,并带一瓶水。",
        ),
        "activity_chair_exercise_my": (
            "每星期二早上9点举行。",
            "坐着或站着都可以,选择您身体觉得舒服的方式。",
            "穿软鞋,并带一瓶水。",
        ),
        "activity_tai_chi": (
            "每星期三早上8点举行。",
            "您可以站着或坐着参加。",
            "穿软鞋,并带一瓶水。",
        ),
        "activity_tea_chat": (
            "每星期四下午3点举行。",
            "欢迎新朋友加入。",
            "参加不需要付费。",
        ),
        "service_home_nursing": (
            "她会检查您的血压和药物。",
            "探访需要提前预约,选择适合您的日子。",
        ),
        "service_physio": (
            "他可以到您家,或您到他那里。",
            "穿宽松的衣服,方便活动。",
        ),
        "service_meal_delivery": (
            "每天都有热食送到您家门口。",
            "告诉他们您不能吃的食物,他们会记住。",
        ),
        "service_transport": (
            "司机会等候,然后送您回家。",
            "请在需要用车的前一天预约。",
        ),
        "resource_falls": (
            "固定松动的地垫,保持地面畅通。",
            "在楼梯和浴室附近加装灯。",
            "把电话放在您坐的地方附近。",
        ),
        "resource_doctor_visit": (
            "带上您的药和血压本。",
            "出发前先写下您的问题。",
        ),
        "resource_heat": (
            "经常喝水,即使不觉得口渴。",
            "在一天中最热的时段,留在室内休息。",
        ),
        "event_market_sg": ("每星期六早上举行。", "带上购物袋,慢慢逛。"),
        "event_market_my": ("每星期日早上举行。", "带上购物袋,慢慢逛。"),
        "volunteer_reading": (
            "任何人都可以帮忙。",
            "不需要培训,只需抽出一小时。",
        ),
        "volunteer_meals": (
            "路线不长,就在您住的附近。",
            "不需要培训,只需抽出一小时。",
        ),
        "support_group": ("每月举行一次,在傍晚时段。", "家人也欢迎一同出席。"),
    },
}
