"""The words a person is asked to agree to, before he has anything to agree on.

The for-me door (`POST /profiles/mine`) records a consent by its wording version, and
refuses a version that is not today's. The client has to show him today's words first, and
they live in one place — `app.consent.texts` — so this route reads them from there rather
than letting a client carry a copy that could drift. It is the same text a claimant is shown
in `GET /profiles/mine/claimable` (`hold_words`), for the person who is opening his own
profile. Nothing personal is read or written: this is the catalogue, in the deployment's
region, in the language asked for.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.channels.api.deps import settings_of
from app.channels.api.schemas import WordingOut
from app.consent.models import ConsentPurpose
from app.consent.texts import current_version, wording
from app.errors import Refusal
from app.medicines.strings import language_of

router = APIRouter(tags=["consent"])

Purpose = Query(default=ConsentPurpose.HOLD_HEALTH_RECORD)
Language = Query(default="en", min_length=2, max_length=16)


class NoWordsInThatLanguage(Refusal):
    """The purpose has no words on file in the language asked for, in this region."""


@router.get("/consent/wording")
async def consent_wording(
    request: Request,
    purpose: ConsentPurpose = Purpose,
    language: str = Language,
) -> WordingOut:
    """Today's words for one purpose, in one of the languages Nura speaks, for this region.

    A per-person purpose (letting someone in) is a template here; the rendered words for a
    named person come back on the consent itself.
    """
    region = settings_of(request).region
    lang = language_of(language)
    version = current_version(purpose)
    text = wording(purpose, version, lang, region)
    if text is None:
        raise NoWordsInThatLanguage(f"no {purpose.value} words in {lang} for {region.value}")
    return WordingOut(
        purpose=purpose, version=version, language=lang, region=region, lines=text.split("\n")
    )
