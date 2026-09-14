"""What closing his account means, in his words (#143): the lines the confirm step shows, and
that his yes binds to (`app.drafts.CloseDraft`). Awaiting counsel's sign-off, with the
retention window (`docs/trust/account-closure.md`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.channels.strings import language_of
from app.medicines.strings import say_date

# @patient
CLOSING: Mapping[str, tuple[str, ...]] = {
    "en": (
        "Nura will stop keeping your papers.",
        "Nobody can open them from now on, not even you.",
        "Nura will not remind you about your medicines.",
        "Your family will not be told when you are unwell.",
        "If you are unwell, call {emergency_number}.",
        "Your papers will be deleted after {day}.",
        "Until then, you can change your mind.",
    ),
    "ms": (
        "Nura akan berhenti menyimpan surat-surat anda.",
        "Tiada sesiapa boleh bukanya mulai sekarang, termasuk anda.",
        "Nura tidak akan ingatkan anda tentang ubat anda.",
        "Keluarga anda tidak akan diberitahu apabila anda tidak sihat.",
        "Jika anda tidak sihat, telefon {emergency_number}.",
        "Surat-surat anda akan dipadam selepas {day}.",
        "Sebelum itu, anda boleh ubah fikiran.",
    ),
    "zh": (
        "Nura 会停止保存您的文件。",
        "从现在起，谁都不能打开，包括您自己。",
        "Nura 不会再提醒您用药。",
        "您不舒服时，不会再通知您的家人。",
        "如果您不舒服，请拨打 {emergency_number}。",
        "您的文件会在{day}之后删除。",
        "在那之前，您可以改变主意。",
    ),
}
"""What stops, who can no longer open them, who to call, and the day his papers go."""


def closing_lines(language: str | None, delete_on: date, emergency_number: str) -> tuple[str, ...]:
    code = language_of(language)
    day = say_date(delete_on, code)
    return tuple(line.format(day=day, emergency_number=emergency_number) for line in CLOSING[code])
