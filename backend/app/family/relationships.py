"""Who the person let in, or setting up, is to him: a code, said in each reader's language.

The relationship is kept as one of these codes (#137's review), never as the words someone
typed or tapped, so it can be said to whoever reads it in their own language — "your
daughter", "anak perempuan anda", "您的女儿" — wherever it appears: the words of an agreement
to let someone in (`app.consent.texts.named_words`), the claim ("Mei, your daughter, made
this for you."), the stewardship. Rows written before the codes were named by revision
0024, which maps the phrases it knows and sets anything else to `other`.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class Relationship(StrEnum):
    """Who the person is to the patient. A closed set: anything else is `OTHER`."""

    DAUGHTER = "daughter"
    SON = "son"
    SPOUSE = "spouse"
    SIBLING = "sibling"
    GRANDCHILD = "grandchild"
    OTHER_FAMILY = "other_family"
    HELPER = "helper"
    FRIEND = "friend"
    NEIGHBOUR = "neighbour"
    OTHER = "other"


# @patient phrase
RELATIONSHIP_WORDS: Mapping[str, Mapping[Relationship, str]] = {
    "en": {
        Relationship.DAUGHTER: "your daughter",
        Relationship.SON: "your son",
        Relationship.SPOUSE: "your husband or wife",
        Relationship.SIBLING: "your brother or sister",
        Relationship.GRANDCHILD: "your grandchild",
        Relationship.OTHER_FAMILY: "someone in your family",
        Relationship.HELPER: "your helper",
        Relationship.FRIEND: "your friend",
        Relationship.NEIGHBOUR: "your neighbour",
        Relationship.OTHER: "someone you know",
    },
    "ms": {
        Relationship.DAUGHTER: "anak perempuan anda",
        Relationship.SON: "anak lelaki anda",
        Relationship.SPOUSE: "suami atau isteri anda",
        Relationship.SIBLING: "adik-beradik anda",
        Relationship.GRANDCHILD: "cucu anda",
        Relationship.OTHER_FAMILY: "ahli keluarga anda",
        Relationship.HELPER: "pembantu anda",
        Relationship.FRIEND: "kawan anda",
        Relationship.NEIGHBOUR: "jiran anda",
        Relationship.OTHER: "kenalan anda",
    },
    "zh": {
        Relationship.DAUGHTER: "您的女儿",
        Relationship.SON: "您的儿子",
        Relationship.SPOUSE: "您的丈夫或妻子",
        Relationship.SIBLING: "您的兄弟姐妹",
        Relationship.GRANDCHILD: "您的孙子或孙女",
        Relationship.OTHER_FAMILY: "您的家人",
        Relationship.HELPER: "您的帮手",
        Relationship.FRIEND: "您的朋友",
        Relationship.NEIGHBOUR: "您的邻居",
        Relationship.OTHER: "您认识的人",
    },
}
"""Each code as the patient hears it: who this person is to him."""


def relationship_of(code: str | None) -> Relationship | None:
    """The code as a `Relationship`; anything not in the set is `OTHER`, never an error."""
    if code is None:
        return None
    try:
        return Relationship(code)
    except ValueError:
        return Relationship.OTHER


def relationship_words(code: str | None, language: str | None) -> str | None:
    """Who this person is to him, in `language` (English for one Nura does not speak)."""
    relationship = relationship_of(code)
    if relationship is None:
        return None
    words = RELATIONSHIP_WORDS.get((language or "en")[:2], RELATIONSHIP_WORDS["en"])
    return words[relationship]
