"""The reply catalogue: every sentence the number writes back inside a thread (E19-02).

A reply is free text inside the 24-hour window, so it is not a template; but it is still a
patient-facing string, chosen from here by key and never written at run time. Each is
whole lines in English, Malay and Chinese, tagged `@patient`, checked by `make plain-words`
and again by the send path. The one stranger's reply (`UNKNOWN_NUMBER`) carries no health
content and says nothing about who is or is not on any list.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.channels.whatsapp.templates import language_of
from app.errors import Refusal

Lines = tuple[str, ...]


class NotACatalogueKey(Refusal):
    """No reply by that key in the catalogue."""


# @patient
REPLIES: Mapping[str, Mapping[str, Lines]] = {
    "unknown_number": {
        "en": (
            "Hello, this is Nura.",
            "Nura keeps health papers for families.",
            "This number is not on a family list yet.",
            "Ask your family to add you in the app.",
            "Nura is not a doctor.",
        ),
        "ms": (
            "Helo, ini Nura.",
            "Nura menyimpan surat kesihatan untuk keluarga.",
            "Nombor ini belum ada dalam senarai keluarga.",
            "Minta keluarga anda tambah anda dalam aplikasi.",
            "Nura bukan doktor.",
        ),
        "zh": (
            "您好，我是 Nura。",
            "Nura 帮家人保存健康文件。",
            "这个号码还不在家人名单里。",
            "请家人在应用里把您加进来。",
            "Nura 不是医生。",
        ),
    },
    "more_than_one": {
        "en": ("You are on more than one family list.", "Open the app to say who this is about."),
        "ms": (
            "Anda ada dalam lebih daripada satu senarai keluarga.",
            "Buka aplikasi untuk kata ini tentang siapa.",
        ),
        "zh": ("您在不止一个家人名单里。", "请打开应用，说说这是关于谁的。"),
    },
    "no_whatsapp_yet": {
        "en": (
            "Nura does not send WhatsApp messages for {name} yet.",
            "{name} can turn that on in the app.",
        ),
        "ms": (
            "Nura belum hantar mesej WhatsApp untuk {name}.",
            "{name} boleh buka dalam aplikasi.",
        ),
        "zh": ("Nura 还没有为{name}开通 WhatsApp。", "{name}可以在应用里打开。"),
    },
    "kept_photo": {
        "en": ("I kept the photo.", "{name} can check it in the app."),
        "ms": ("Saya simpan gambar itu.", "{name} boleh semak dalam aplikasi."),
        "zh": ("照片我收好了。", "{name}可以在应用里看。"),
    },
    "kept_letter": {
        "en": ("I kept the letter.", "{name} can check it in the app."),
        "ms": ("Saya simpan surat itu.", "{name} boleh semak dalam aplikasi."),
        "zh": ("信我收好了。", "{name}可以在应用里看。"),
    },
    "kept_for_family": {
        "en": ("I kept this for the family.",),
        "ms": ("Saya simpan ini untuk keluarga.",),
        "zh": ("这个我为家人留着。",),
    },
    "propose_blood_pressure": {
        "en": (
            "Did I get this right?",
            "{name}'s blood pressure was {top} over {bottom}.",
            "Answer yes or no.",
        ),
        "ms": (
            "Betul ke ini?",
            "Tekanan darah {name} ialah {top} atas {bottom}.",
            "Jawab ya atau tidak.",
        ),
        "zh": ("我听对了吗？", "{name}的血压是{top}比{bottom}。", "回答是或不是。"),
    },
    "propose_blood_sugar": {
        "en": ("Did I get this right?", "{name}'s sugar was {value}.", "Answer yes or no."),
        "ms": ("Betul ke ini?", "Gula {name} ialah {value}.", "Jawab ya atau tidak."),
        "zh": ("我听对了吗？", "{name}的血糖是{value}。", "回答是或不是。"),
    },
    "propose_weight": {
        "en": ("Did I get this right?", "{name} weighed {weight} kg.", "Answer yes or no."),
        "ms": ("Betul ke ini?", "Berat {name} ialah {weight} kg.", "Jawab ya atau tidak."),
        "zh": ("我听对了吗？", "{name}的体重是 {weight} 公斤。", "回答是或不是。"),
    },
    "propose_taken": {
        "en": ("Did I get this right?", "{name} took the tablets.", "Answer yes or no."),
        "ms": ("Betul ke ini?", "{name} sudah ambil ubat.", "Jawab ya atau tidak."),
        "zh": ("我听对了吗？", "{name}吃了药。", "回答是或不是。"),
    },
    "propose_feeling": {
        "en": ("Did I get this right?", "{name} is feeling {word}.", "Answer yes or no."),
        "ms": ("Betul ke ini?", "{name} rasa {word}.", "Jawab ya atau tidak."),
        "zh": ("我听对了吗？", "{name}感觉{word}。", "回答是或不是。"),
    },
    "propose_unwell": {
        "en": ("Did I get this right?", "{name} is not well.", "Answer yes or no."),
        "ms": ("Betul ke ini?", "{name} tidak sihat.", "Jawab ya atau tidak."),
        "zh": ("我听对了吗？", "{name}不舒服。", "回答是或不是。"),
    },
    "written_down": {
        "en": ("Thank you for telling me.", "I wrote it down."),
        "ms": ("Terima kasih kerana beritahu saya.", "Saya sudah tulis."),
        "zh": ("谢谢您告诉我。", "我记下了。"),
    },
    "not_written": {
        "en": ("OK, I did not write it down.",),
        "ms": ("OK, saya tidak tulis.",),
        "zh": ("好，我没有记下来。",),
    },
    "nothing_open": {
        "en": ("I have no question open for you.",),
        "ms": ("Saya tidak ada soalan untuk anda sekarang.",),
        "zh": ("我现在没有问您的问题。",),
    },
    "too_old": {
        "en": ("That question is too old.", "Send the message again."),
        "ms": ("Soalan itu sudah lama.", "Hantar mesej itu semula."),
        "zh": ("那个问题太久了。", "请再发一次。"),
    },
    "not_open_to_you": {
        "en": (
            "That part of {name}'s record is not open to you.",
            "{name} can change that in the app.",
        ),
        "ms": (
            "Bahagian rekod {name} itu tidak dibuka untuk anda.",
            "{name} boleh ubah dalam aplikasi.",
        ),
        "zh": ("{name}记录里的这部分没有开放给您。", "{name}可以在应用里更改。"),
    },
    "red_flag": {
        "en": ("This one we do not wait for.", "Call {doctor} today.", "{names} know now."),
        "ms": ("Yang ini kita tidak tunggu.", "Telefon {doctor} hari ini.", "{names} sudah tahu."),
        "zh": ("这个不能等。", "今天就打电话给{doctor}。", "{names}已经知道了。"),
    },
    "red_flag_one": {
        "en": ("This one we do not wait for.", "Call {doctor} today.", "{names} knows now."),
        "ms": ("Yang ini kita tidak tunggu.", "Telefon {doctor} hari ini.", "{names} sudah tahu."),
        "zh": ("这个不能等。", "今天就打电话给{doctor}。", "{names}已经知道了。"),
    },
    "red_flag_alone": {
        "en": ("This one we do not wait for.", "Call {doctor} today."),
        "ms": ("Yang ini kita tidak tunggu.", "Telefon {doctor} hari ini."),
        "zh": ("这个不能等。", "今天就打电话给{doctor}。"),
    },
    "not_understood": {
        "en": ("I did not understand that.", "Send a photo, or your blood pressure as 2 numbers."),
        "ms": ("Saya tidak faham.", "Hantar gambar, atau tekanan darah anda sebagai 2 nombor."),
        "zh": ("我没听懂。", "请发照片，或者把血压的 2 个数字发给我。"),
    },
}
"""Every reply, by key. A key that is not here is not a reply the number can send."""

# @patient phrase
FEELING_WORDS: Mapping[str, Mapping[str, str]] = {
    "en": {"ok": "OK", "tired": "tired", "pain": "in pain"},
    "ms": {"ok": "OK", "tired": "letih", "pain": "sakit"},
    "zh": {"ok": "好", "tired": "累", "pain": "痛"},
}
"""The three feeling words as the read-back says them."""

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}
"""When the profile names no doctor yet."""

# @patient phrase
YOU: Mapping[str, str] = {"en": "You", "ms": "Anda", "zh": "您"}
"""The poster, when the next thing is theirs."""

# @patient phrase
AND: Mapping[str, str] = {"en": " and ", "ms": " dan ", "zh": "和"}


def reply(key: str, language: str | None, **params: str) -> str:
    """The catalogue reply, whole lines joined, with its slots filled."""
    lines = REPLIES.get(key)
    if lines is None:
        raise NotACatalogueKey(f"no reply named {key!r}")
    lang = language_of(language)
    return "\n".join(line.format(**params) for line in lines[lang])


def join_names(names: list[str], language: str | None) -> str:
    """'Mei', 'Mei and Kit', 'Mei, Kit and Ash'."""
    lang = language_of(language)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + AND[lang] + names[-1]
