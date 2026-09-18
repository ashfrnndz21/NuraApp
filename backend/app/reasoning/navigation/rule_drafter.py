"""The catalogue-only drafter: today's behaviour, unchanged by whichever drafter a
deployment names (`NURA_DRAFTER`, `drafter_provider.py`).

Every word comes from `app.channels.strings.TEXT`, filled only with a name already on the
record — `patient_name`, `doctor` (or a lab's own name), `drafter_name` for a caregiver's own
voice — never a dose, never a diagnosis: there is no template slot for either, so the
question of "did this leak health content" never turns on a model's judgement here. `verify`
(`app.safety.plain_words`) still runs over the filled text before it is handed back, the same
door a memo or a card passes through, so a translation this module carries can never ship a
line the checker itself would fail.
"""

from __future__ import annotations

import re

from app.channels.strings import lines
from app.reasoning.navigation.models import Need, NeedKind
from app.safety.health_words import CONDITIONS
from app.safety.plain_words import verify

_HOME_CARE_KEY = {
    "nursing": "navigation_home_care_nursing",
    "physio": "navigation_home_care_physio",
    "meals": "navigation_home_care_meals",
    "transport": "navigation_home_care_transport",
}

_DOCTOR_FALLBACK = {"en": "the clinic", "ms": "klinik itu", "zh": "诊所"}
_PLACE_FALLBACK = {"en": "the lab", "ms": "makmal itu", "zh": "化验所"}

_DOSE_PATTERN = (
    r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|iu|tablet|tab|tabs|capsule|caps|biji|片|毫克|粒)\b"
)


def names_dose_or_diagnosis(text: str) -> str | None:
    """`"dose"` or `"condition"` if the text carries one, else `None` — the blocklist a draft
    is checked against before it is ever shown, whichever drafter wrote it. Never the word
    itself, the same discipline `app.safety.health_words.names_health` keeps."""
    if re.search(_DOSE_PATTERN, text, re.IGNORECASE):
        return "dose"
    lowered = text.lower()
    for phrases in CONDITIONS.values():
        for phrase in phrases:
            is_cjk = any("一" <= ch <= "鿿" for ch in phrase)
            if (phrase in text) if is_cjk else (phrase.lower() in lowered):
                return "condition"
    return None


def _key_for(need: Need) -> str:
    if need.kind is NeedKind.FOLLOW_UP:
        return "navigation_follow_up"
    if need.kind is NeedKind.NEW_MEDICINE:
        return "navigation_new_medicine"
    if need.kind is NeedKind.TEST_DUE:
        return "navigation_test_due"
    return _HOME_CARE_KEY.get(need.category or "", "navigation_home_care_nursing")


def _fallback(table: dict[str, str], language: str) -> str:
    return table.get(language, table["en"])


class RuleDrafter:
    """Fills the catalogue's own templates from the need's own who/what/when — nothing else."""

    async def draft(
        self,
        *,
        need: Need,
        language: str,
        patient_name: str,
        drafter_name: str | None,
        is_self: bool,
    ) -> str:
        intro_key = "navigation_intro_self" if is_self else "navigation_intro_caregiver"
        intro = "\n".join(lines(intro_key, language)).format(
            patient=patient_name, who=drafter_name or patient_name
        )
        body_lines = lines(_key_for(need), language)
        doctor = need.doctor or _fallback(_DOCTOR_FALLBACK, language)
        place = need.doctor or _fallback(_PLACE_FALLBACK, language)
        body = "\n".join(body_lines).format(patient=patient_name, doctor=doctor, place=place)
        text = f"{intro}\n{body}"
        if any(finding.severity == "fail" for finding in verify(text, language, "line")):
            # The catalogue's own words failed its own check (should never happen; a defect
            # in the template, not in this call) — say the ask alone, still safe, still his
            # language, never silently drop to English.
            text = body
        found = names_dose_or_diagnosis(text)
        if found is not None:  # pragma: no cover - no template carries either today
            raise ValueError(f"a navigation draft named a {found}; this is a defect, not data")
        return text
