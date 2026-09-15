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
    # A number whose only family is closing its account (#143): nothing is kept and nobody is
    # told through Nura, so the one fixed line always says who to call.
    "closing": {
        "en": (
            "Nura is not keeping these papers any more.",
            "Nura did not keep this message.",
            "If it cannot wait, call {emergency_number} now.",
        ),
        "ms": (
            "Nura tidak lagi menyimpan surat-surat ini.",
            "Nura tidak menyimpan mesej ini.",
            "Kalau tidak boleh tunggu, telefon {emergency_number} sekarang.",
        ),
        "zh": (
            "Nura 已不再保存这些文件。",
            "Nura 没有保存这条消息。",
            "如果不能等，现在就打{emergency_number}。",
        ),
    },
    # A post in a family's group from a number that is not in that family now (#143): nothing
    # is kept, and a red word is answered to the sender alone, with who to call.
    "group_not_kept": {
        "en": (
            "Nura did not keep this message.",
            "If it cannot wait, call {emergency_number} now.",
        ),
        "ms": (
            "Nura tidak menyimpan mesej ini.",
            "Kalau tidak boleh tunggu, telefon {emergency_number} sekarang.",
        ),
        "zh": ("Nura 没有保存这条消息。", "如果不能等，现在就打{emergency_number}。"),
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
    "voice_note_kept": {
        "en": ("Nura kept your voice note.",),
        "ms": ("Nura sudah simpan nota suara anda.",),
        "zh": ("Nura 保存了您的语音留言。",),
    },
    # His voice note kept, but no words heard in it (#158): a red word in it could not be read,
    # so, like its twin `voice_note_not_fetched`, the reply says what to do if he feels unwell,
    # and his chief is told to listen (`inbound._tell_family_unheard`).
    "voice_note_unheard": {
        "en": (
            "Nura kept your voice note.",
            "Nura could not hear this note.",
            "If you feel unwell, call your family now.",
        ),
        "ms": (
            "Nura sudah simpan nota suara anda.",
            "Nura tidak dapat mendengar nota ini.",
            "Jika anda rasa tidak sihat, telefon keluarga anda sekarang.",
        ),
        "zh": (
            "Nura 保存了您的语音留言。",
            "Nura 听不清这段录音。",
            "如果您不舒服，现在就打电话给家人。",
        ),
    },
    "voice_note_not_fetched": {
        "en": ("Nura could not hear your voice note.", "If you feel unwell, call your family now."),
        "ms": (
            "Nura tidak dapat dengar nota suara anda.",
            "Jika anda rasa tidak sihat, telefon keluarga anda sekarang.",
        ),
        "zh": ("Nura 听不到您的语音留言。", "如果您不舒服，现在就打电话给家人。"),
    },
    # Said in the family's WhatsApp group, which he reads, above a message written in the app
    # (#158): his words for where it was written, the same in every language, and a subject
    # always — `mirror_to_group` fills an unnamed poster as Someone.
    "family_said": {
        "en": ("{who} wrote this in the Nura app:",),
        "ms": ("{who} menulis ini dalam aplikasi Nura:",),
        "zh": ("{who}在 Nura 应用里写道：",),
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
            "That part of {name}'s papers is not open to you.",
            "{name} can change that in the app.",
        ),
        "ms": (
            "Bahagian surat-surat {name} itu tidak dibuka untuk anda.",
            "{name} boleh ubah dalam aplikasi.",
        ),
        "zh": ("{name}文件里的这部分没有开放给您。", "{name}可以在应用里更改。"),
    },
    "red_flag": {
        "en": ("This one we do not wait for.", "Call {doctor} today.", "{names} know now."),
        "ms": ("Yang ini kita tidak tunggu.", "Telefon {doctor} hari ini.", "{names} sudah tahu."),
        "zh": ("这个我们不等。", "今天就打电话给{doctor}。", "{names}已经知道了。"),
    },
    "red_flag_one": {
        "en": ("This one we do not wait for.", "Call {doctor} today.", "{names} knows now."),
        "ms": ("Yang ini kita tidak tunggu.", "Telefon {doctor} hari ini.", "{names} sudah tahu."),
        "zh": ("这个我们不等。", "今天就打电话给{doctor}。", "{names}已经知道了。"),
    },
    "red_flag_alone": {
        "en": ("This one we do not wait for.", "Call {doctor} today."),
        "ms": ("Yang ini kita tidak tunggu.", "Telefon {doctor} hari ini."),
        "zh": ("这个我们不等。", "今天就打电话给{doctor}。"),
    },
    # A flag written but held back (it depends on a fact not on his papers): no alarm, and
    # still the next step for a worried family member.
    "red_flag_held": {
        "en": ("I wrote it down.", "If it gets worse, call {doctor} today."),
        "ms": ("Saya sudah tulis.", "Kalau jadi lebih teruk, telefon {doctor} hari ini."),
        "zh": ("我记下了。", "如果变得更严重，今天就打电话给{doctor}。"),
    },
    "taken_patient": {
        "en": ("Thank you, I wrote it down.", "{who} can see you took it."),
        "ms": ("Terima kasih, saya sudah tulis.", "{who} boleh lihat anda sudah ambil."),
        "zh": ("谢谢，我记下了。", "{who}能看到您吃了。"),
    },
    "taken_alone": {
        "en": ("Thank you, I wrote it down.",),
        "ms": ("Terima kasih, saya sudah tulis.",),
        "zh": ("谢谢，我记下了。",),
    },
    "given": {
        "en": ("Thank you, I wrote it down.", "{name} had {medicine}."),
        "ms": ("Terima kasih, saya sudah tulis.", "{name} sudah ambil {medicine}."),
        "zh": ("谢谢，我记下了。", "{name}吃了{medicine}。"),
    },
    "taken_nothing_due": {
        "en": ("There is no tablet to take right now.", "I did not write anything down."),
        "ms": ("Tiada ubat untuk diambil sekarang.", "Saya tidak tulis apa-apa."),
        "zh": ("现在没有要吃的药。", "我没有记下任何东西。"),
    },
    "flag_seen": {
        "en": ("Thank you, you have it now.", "I will not ask anyone else."),
        "ms": ("Terima kasih, anda uruskan sekarang.", "Saya tidak akan tanya orang lain."),
        "zh": ("谢谢，现在由您来处理。", "我不会再问别人了。"),
    },
    # A red flag heard on a profile whose patient has not agreed to WhatsApp: the flag is
    # raised and put first in the family's app; the poster gets this line and nothing else.
    "red_flag_fixed": {
        "en": (
            "This one we do not wait for.",
            "I put it first in the family's app.",
            "If it cannot wait, call {emergency_number} now.",
        ),
        "ms": (
            "Yang ini kita tidak tunggu.",
            "Saya letak ia paling atas dalam aplikasi keluarga.",
            "Kalau tidak boleh tunggu, telefon {emergency_number} sekarang.",
        ),
        "zh": (
            "这个我们不等。",
            "我把它放在家人应用的最上面。",
            "如果不能等，现在就打{emergency_number}。",
        ),
    },
    # A red-flag word from someone on more than one family's list: raised on each, then asked.
    "red_flag_which": {
        "en": (
            "This one we do not wait for.",
            "I put it first in the family's app for {both}.",
            "Who is it about?",
            "Send me the name, {either}.",
        ),
        "ms": (
            "Yang ini kita tidak tunggu.",
            "Saya letak ia paling atas dalam aplikasi keluarga untuk {both}.",
            "Ini tentang siapa?",
            "Hantar nama kepada saya, {either}.",
        ),
        "zh": (
            "这个我们不等。",
            "我把它放在{both}家人应用的最上面。",
            "是关于谁的？",
            "请把名字发给我：{either}。",
        ),
    },
    "red_flag_which_thanks": {
        "en": ("Thank you, it is about {name}.", "I stopped asking the other family."),
        "ms": ("Terima kasih, ini tentang {name}.", "Saya berhenti bertanya keluarga yang lain."),
        "zh": ("谢谢，是关于{name}的。", "我不再问另一个家庭了。"),
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
GROUP_NAME: Mapping[str, str] = {
    "en": "{name} and family",
    "ms": "{name} dan keluarga",
    "zh": "{name}和家人",
}
"""The name of the family's group on WhatsApp (E11-01), as everyone in it reads it."""

# @patient phrase
YOUR_DOCTOR: Mapping[str, str] = {"en": "your doctor", "ms": "doktor anda", "zh": "您的医生"}
"""When the profile names no doctor yet."""

# @patient phrase
YOU: Mapping[str, str] = {"en": "You", "ms": "Anda", "zh": "您"}
"""The poster, when the next thing is theirs."""

# @patient phrase
AND: Mapping[str, str] = {"en": " and ", "ms": " dan ", "zh": "和"}

# @patient phrase
OR: Mapping[str, str] = {"en": " or ", "ms": " atau ", "zh": "还是"}


def reply(key: str, language: str | None, **params: str) -> str:
    """The catalogue reply, whole lines joined, with its slots filled."""
    lines = REPLIES.get(key)
    if lines is None:
        raise NotACatalogueKey(f"no reply named {key!r}")
    lang = language_of(language)
    return "\n".join(line.format(**params) for line in lines[lang])


def join_names(names: list[str], language: str | None, *, either: bool = False) -> str:
    """'Mei', 'Mei and Kit', 'Mei, Kit and Ash' — or with `either`, 'Pa or Ma'."""
    lang = language_of(language)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + (OR if either else AND)[lang] + names[-1]
