"""Every card is also a voice script (docs/plain-words.md §4, E22-03).

`script_for(lines, language, boundary=…)` renders a card's lines as the script it is spoken
from: one segment per line, each followed by a pause, and a longer pause before the boundary
line an inferring card ends on, so the card's own words finish before "This is not a doctor's
advice." begins. The script is a function of the verified lines and nothing else — the lines
the card shows (or its voice twin, where it has one), in the card's language — so what he
hears can never be other words than what passed the plain-words verifier. Only what a voice
must say differently from what an eye reads is changed, and only where it is on the line:

- numbers are read as words in the card's language: "138 over 84" is "one hundred and
  thirty-eight over eighty-four", "seratus tiga puluh lapan atas lapan puluh empat",
  "一百三十八比八十四" (the connecting word is the card's own: Malay says "atas" and
  Chinese "比" on every card, so the script does too);
- a day-name date is said as a person says it: "Monday the fourteenth of September",
  "Isnin empat belas September", "九月十四日星期一";
- a unit is said in full ("mg/dL" → "milligrams per decilitre") where the line carries one,
  which on his cards is rare: the verifier keeps units he does not use off them;
- in Chinese, 2 before a measure word is 两 ("2 次" → "两次").

Nothing else changes: no word is added that the line does not imply, none is dropped.

The seam for audio (E11, PR #121, not on main when this was written): `VoiceScript.digest` is
the sha256 of the language and the segments, the same digest for the same words and pauses
wherever they appear. E11's `Voice.speak(text, language)` is given `script.spoken()` — the
segments' words, one per line, which is how that port reads a pause — and its cache keys on
the digest, so a card's audio is rendered once, when the card is made, and read back from the
region's store every time after. No audio provider is named here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

LANGUAGES = ("en", "ms", "zh")
PAUSE_MS = 500
"""After each line: one idea, then a breath, then the next (E11's `PAUSE_SECONDS`)."""
BOUNDARY_PAUSE_MS = 1200
"""Before the boundary line: the card's own words end, then the words every inferring card
ends on."""


@dataclass(frozen=True, slots=True)
class Segment:
    text: str
    pause_ms: int
    """The silence after the words."""


@dataclass(frozen=True, slots=True)
class VoiceScript:
    language: str
    segments: tuple[Segment, ...]

    @property
    def digest(self) -> str:
        """What the audio is kept under: the same words and pauses, the same digest."""
        canonical = json.dumps(
            {"language": self.language, "segments": [[s.text, s.pause_ms] for s in self.segments]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def spoken(self) -> str:
        """The words, one segment per line: what a synthesiser is given."""
        return "\n".join(segment.text for segment in self.segments)

    def as_json(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "digest": self.digest,
            "segments": [{"text": s.text, "pause_ms": s.pause_ms} for s in self.segments],
        }


# --- numbers -----------------------------------------------------------------------------------

_EN_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_EN_ORDINAL = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}


def _en_below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    words: list[str] = []
    if hundreds:
        words.append(f"{_EN_ONES[hundreds]} hundred")
    if rest:
        if hundreds:
            words.append("and")
        if rest < 20:
            words.append(_EN_ONES[rest])
        else:
            tens, ones = divmod(rest, 10)
            words.append(_EN_TENS[tens] + (f"-{_EN_ONES[ones]}" if ones else ""))
    return " ".join(words)


def english_number(n: int) -> str:
    """138 → "one hundred and thirty-eight"; 2026 → "two thousand and twenty-six"."""
    if n < 0:
        return "minus " + english_number(-n)
    if n < 20:
        return _EN_ONES[n]
    if n < 1000:
        return _en_below_thousand(n)
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = f"{english_number(thousands)} thousand"
        if not rest:
            return head
        joiner = " and " if rest < 100 else " "
        return head + joiner + _en_below_thousand(rest)
    return " ".join(_EN_ONES[int(d)] for d in str(n))


def english_ordinal(n: int) -> str:
    """14 → "fourteenth"; 21 → "twenty-first"."""
    words = english_number(n)
    head, sep, last = words.rpartition("-" if "-" in words.split()[-1] else " ")
    if last in _EN_ORDINAL:
        last = _EN_ORDINAL[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}{sep}{last}" if sep else last


def english_year(n: int) -> str:
    """2023 → "twenty twenty-three"; 2005 → "two thousand and five"."""
    if 2000 <= n < 2010 or n % 100 == 0:
        return english_number(n)
    if 1100 <= n < 2100:
        return f"{english_number(n // 100)} {english_number(n % 100)}"
    return english_number(n)


_MS_ONES = "sifar satu dua tiga empat lima enam tujuh lapan sembilan".split()


def malay_number(n: int) -> str:
    """138 → "seratus tiga puluh lapan"; 84 → "lapan puluh empat"; 2026 → "dua ribu dua puluh enam"."""
    if n < 10:
        return _MS_ONES[n]
    if n == 10:
        return "sepuluh"
    if n == 11:
        return "sebelas"
    if n < 20:
        return f"{_MS_ONES[n - 10]} belas"
    if n < 100:
        tens, ones = divmod(n, 10)
        return f"{_MS_ONES[tens]} puluh" + (f" {_MS_ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = "seratus" if hundreds == 1 else f"{_MS_ONES[hundreds]} ratus"
        return head + (f" {malay_number(rest)}" if rest else "")
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = "seribu" if thousands == 1 else f"{malay_number(thousands)} ribu"
        return head + (f" {malay_number(rest)}" if rest else "")
    return " ".join(_MS_ONES[int(d)] for d in str(n))


_ZH_DIGITS = "零一二三四五六七八九"


def chinese_number(n: int) -> str:
    """138 → "一百三十八"; 105 → "一百零五"; 2026 → "两千零二十六"; 12 → "十二"."""
    if n < 10:
        return _ZH_DIGITS[n]
    if n < 20:
        return "十" + (_ZH_DIGITS[n - 10] if n > 10 else "")
    if n >= 100_000_000:
        return "".join(_ZH_DIGITS[int(d)] for d in str(n))
    parts: list[str] = []
    units = ((10000, "万"), (1000, "千"), (100, "百"), (10, "十"))
    rest = n
    zero_pending = False
    for size, name in units:
        digit, rest = divmod(rest, size)
        if digit:
            if zero_pending:
                parts.append("零")
                zero_pending = False
            if size == 10000:
                parts.append(chinese_number(digit) + name)
            else:
                word = "两" if digit == 2 and size >= 100 and not parts else _ZH_DIGITS[digit]
                parts.append(word + name)
        elif parts:
            zero_pending = True
    if rest:
        if zero_pending or (parts and n % 100 < 10 and n >= 100):
            parts.append("零")
        parts.append(_ZH_DIGITS[rest])
    return "".join(parts)


def chinese_digits(n: int) -> str:
    """A year, digit by digit: 2023 → "二零二三"."""
    return "".join(_ZH_DIGITS[int(d)] for d in str(n))


def _decimal(whole: str, fraction: str, language: str) -> str:
    number = say_number(int(whole), language)
    if language == "zh":
        return number + "点" + "".join(_ZH_DIGITS[int(d)] for d in fraction)
    if language == "ms":
        return number + " perpuluhan " + " ".join(_MS_ONES[int(d)] for d in fraction)
    return number + " point " + " ".join(_EN_ONES[int(d)] for d in fraction)


def _digits(number: str, language: str) -> str:
    if language == "zh":
        return "".join(_ZH_DIGITS[int(d)] for d in number)
    names = _MS_ONES if language == "ms" else _EN_ONES
    return " ".join(names[int(d)] for d in number)


def say_number(n: int, language: str) -> str:
    if language == "zh":
        return chinese_number(n)
    if language == "ms":
        return malay_number(n)
    return english_number(n)


# --- dates, units, the reading ------------------------------------------------------------------

_WEEKDAYS = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ms": ("Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"),
}
_MONTHS = {
    "en": (
        "January February March April May June July August September October November December"
    ).split(),
    "ms": "Januari Februari Mac April Mei Jun Julai Ogos September Oktober November Disember".split(),
}


def _date_pattern(language: str) -> re.Pattern[str]:
    days = "|".join(_WEEKDAYS[language])
    months = "|".join(_MONTHS[language])
    return re.compile(
        rf"\b(?P<weekday>{days})\s+(?P<day>\d{{1,2}})\s+(?P<month>{months})\b"
        rf"(?:\s+(?P<year>(?:19|20)\d\d)\b)?"
    )


_DATES = {code: _date_pattern(code) for code in ("en", "ms")}
_ZH_DATE = re.compile(r"(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})[日号]")
_READING = re.compile(r"(?<![A-Za-z0-9])(\d{2,3})\s*/\s*(\d{2,3})(?![A-Za-z0-9])")
_OVER = {"en": " over ", "ms": " atas ", "zh": "比"}

UNITS: dict[str, dict[str, tuple[str, str]]] = {
    # unit → (one, many); Chinese has no plural and puts 百分之 before the number.
    "en": {
        "mg/dL": ("milligram per decilitre", "milligrams per decilitre"),
        "mmol/L": ("millimole per litre", "millimoles per litre"),
        "mmHg": ("millimetre of mercury", "millimetres of mercury"),
        "mcg": ("microgram", "micrograms"),
        "mg": ("milligram", "milligrams"),
        "mL": ("millilitre", "millilitres"),
        "ml": ("millilitre", "millilitres"),
        "kg": ("kilo", "kilos"),
        "cm": ("centimetre", "centimetres"),
        "%": ("percent", "percent"),
    },
    "ms": {
        "mg/dL": ("miligram per desiliter", "miligram per desiliter"),
        "mmol/L": ("milimol per liter", "milimol per liter"),
        "mmHg": ("milimeter merkuri", "milimeter merkuri"),
        "mcg": ("mikrogram", "mikrogram"),
        "mg": ("miligram", "miligram"),
        "mL": ("mililiter", "mililiter"),
        "ml": ("mililiter", "mililiter"),
        "kg": ("kilo", "kilo"),
        "cm": ("sentimeter", "sentimeter"),
        "%": ("peratus", "peratus"),
    },
    "zh": {
        "mg/dL": ("毫克每分升", "毫克每分升"),
        "mmol/L": ("毫摩尔每升", "毫摩尔每升"),
        "mmHg": ("毫米汞柱", "毫米汞柱"),
        "mcg": ("微克", "微克"),
        "mg": ("毫克", "毫克"),
        "mL": ("毫升", "毫升"),
        "ml": ("毫升", "毫升"),
        "kg": ("公斤", "公斤"),
        "cm": ("厘米", "厘米"),
        "%": ("", ""),
    },
}
_UNIT = re.compile(
    r"(?<![A-Za-z0-9.])(?P<number>\d+(?:\.\d+)?)\s?"
    r"(?P<unit>mg/dL|mmol/L|mmHg|mcg|mg|mL|ml|kg|cm|%)(?![A-Za-z0-9/])"
)
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![A-Za-z0-9])")
"""A number standing on its own. Only Latin letters and digits count as its neighbours: in
Chinese a number sits right against the characters ("是138比84")."""
EMERGENCY_NUMBERS = frozenset({"995", "999", "112", "911"})
"""Numbers said digit by digit, the way they are dialled: "nine nine five"."""
_ZH_MEASURE = (
    "公斤|星期|小时|分钟|个|次|片|粒|天|包|勺|喷|滴|件|位|年|周|杯|瓶|盒|份|种|条"
)
_ZH_TWO = re.compile(rf"(?<![\d.])2\s*(?=(?:{_ZH_MEASURE}))")
_CJK = "㐀-鿿　-〿＀-￯"
_CJK_GAP = re.compile(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])")


def _en_dates(line: str) -> str:
    def spoken(match: re.Match[str]) -> str:
        said = (
            f"{match['weekday']} the {english_ordinal(int(match['day']))} of {match['month']}"
        )
        return said + (f" {english_year(int(match['year']))}" if match["year"] else "")

    return _DATES["en"].sub(spoken, line)


def _ms_dates(line: str) -> str:
    def spoken(match: re.Match[str]) -> str:
        said = f"{match['weekday']} {malay_number(int(match['day']))} {match['month']}"
        return said + (f" {malay_number(int(match['year']))}" if match["year"] else "")

    return _DATES["ms"].sub(spoken, line)


def _zh_dates(line: str) -> str:
    def spoken(match: re.Match[str]) -> str:
        year = f"{chinese_digits(int(match['year']))}年" if match["year"] else ""
        return f"{year}{chinese_number(int(match['month']))}月{chinese_number(int(match['day']))}日"

    return _ZH_DATE.sub(spoken, line)


def _units(line: str, language: str) -> str:
    table = UNITS[language]

    def spoken(match: re.Match[str]) -> str:
        number, unit = match["number"], match["unit"]
        one, many = table[unit]
        value = float(number)
        if "." in number:
            whole, fraction = number.split(".")
            said = _decimal(whole, fraction, language)
        else:
            said = say_number(int(number), language)
        if language == "zh":
            if unit == "%":
                return f"百分之{said}"
            if number == "2":
                said = "两"
            return f"{said}{one}"
        word = one if value == 1 else many
        return f"{said} {word}"

    return _UNIT.sub(spoken, line)


def _numbers(line: str, language: str) -> str:
    if language == "zh":
        line = _ZH_TWO.sub("两", line)

    def spoken(match: re.Match[str]) -> str:
        whole = match.group(1).replace(",", "")
        if whole in EMERGENCY_NUMBERS and not match.group(2):
            return _digits(whole, language)
        if match.group(2):
            return _decimal(whole, match.group(2), language)
        return say_number(int(whole), language)

    return _NUMBER.sub(spoken, line)


def spoken_line(line: str, language: str) -> str:
    """One line as it is said: the same words, with the numbers, the dates and the units read
    the way a voice says them in `language`."""
    code = language if language in LANGUAGES else "en"
    said = line.strip()
    said = _READING.sub(lambda m: f"{m.group(1)}{_OVER[code]}{m.group(2)}", said)
    if code == "en":
        said = _en_dates(said)
    elif code == "ms":
        said = _ms_dates(said)
    else:
        said = _zh_dates(said)
    said = _units(said, code)
    said = _numbers(said, code)
    if code == "zh":
        said = _CJK_GAP.sub("", said)
    said = re.sub(r"[ \t]+", " ", said).strip()
    if line.strip()[:1].isdigit() and code != "zh":
        said = said[:1].upper() + said[1:]
    return said


def script_for(
    lines: Sequence[str], language: str, *, boundary: str | None = None
) -> VoiceScript:
    """The voice script of a card: its lines, said, each followed by a pause, and a longer
    pause before the boundary lines when the card ends on them (`boundary`, the line the row
    carries). The lines are the verified lines; nothing else goes in."""
    code = language if language in LANGUAGES else "en"
    kept = [line for line in lines if line.strip()]
    closing = [line for line in (boundary or "").splitlines() if line.strip()]
    starts_at = (
        len(kept) - len(closing)
        if closing and len(kept) > len(closing) and kept[-len(closing) :] == closing
        else None
    )
    segments: list[Segment] = []
    for index, line in enumerate(kept):
        pause = BOUNDARY_PAUSE_MS if starts_at is not None and index == starts_at - 1 else PAUSE_MS
        segments.append(Segment(spoken_line(line, code), pause))
    return VoiceScript(code, tuple(segments))
