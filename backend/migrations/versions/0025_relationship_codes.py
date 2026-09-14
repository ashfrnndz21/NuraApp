"""The relationship a stewardship names, as a code (#137's review).

Who the person setting a graph up is to the patient was kept as the words they typed or
tapped, in their language. It is a code now (`app.family.relationships.Relationship`), said
in each reader's language wherever it appears. This names every row written before: the
phrases the doors ever offered or tests wrote, in English, Malay and Chinese, map to their
code; anything else is `other`. Data only: the column is the same `varchar(80)`.

Revision ID: 0025_relationship_codes
Revises: 0024_push_subscription
Create Date: 2026-09-15
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0025_relationship_codes"
down_revision = "0024_push_subscription"
branch_labels = None
depends_on = None

CODES = (
    "daughter",
    "son",
    "spouse",
    "sibling",
    "grandchild",
    "other_family",
    "helper",
    "friend",
    "neighbour",
    "other",
)

SAID: dict[str, str] = {
    # daughter, son
    "anak perempuan": "daughter",
    "女儿": "daughter",
    "anak lelaki": "son",
    "儿子": "son",
    # a husband or a wife
    "wife": "spouse",
    "husband": "spouse",
    "husband or wife": "spouse",
    "isteri": "spouse",
    "suami": "spouse",
    "suami atau isteri": "spouse",
    "妻子": "spouse",
    "丈夫": "spouse",
    "太太": "spouse",
    "老婆": "spouse",
    "老公": "spouse",
    "配偶": "spouse",
    "丈夫或妻子": "spouse",
    # a brother or a sister
    "sister": "sibling",
    "brother": "sibling",
    "brother or sister": "sibling",
    "kakak": "sibling",
    "abang": "sibling",
    "adik": "sibling",
    "adik perempuan": "sibling",
    "adik lelaki": "sibling",
    "adik-beradik": "sibling",
    "kakak atau adik perempuan": "sibling",
    "abang atau adik lelaki": "sibling",
    "姐姐": "sibling",
    "妹妹": "sibling",
    "哥哥": "sibling",
    "弟弟": "sibling",
    "姐妹": "sibling",
    "兄弟": "sibling",
    "兄弟姐妹": "sibling",
    # a grandchild
    "granddaughter": "grandchild",
    "grandson": "grandchild",
    "cucu": "grandchild",
    "cucu perempuan": "grandchild",
    "cucu lelaki": "grandchild",
    "孙女": "grandchild",
    "孙子": "grandchild",
    "外孙": "grandchild",
    "外孙女": "grandchild",
    "孙子或孙女": "grandchild",
    # anyone else in the family, a parent typed where the child was meant included
    "family": "other_family",
    "niece": "other_family",
    "nephew": "other_family",
    "cousin": "other_family",
    "aunt": "other_family",
    "uncle": "other_family",
    "in-law": "other_family",
    "daughter-in-law": "other_family",
    "son-in-law": "other_family",
    "father": "other_family",
    "mother": "other_family",
    "anak saudara": "other_family",
    "anak saudara perempuan": "other_family",
    "anak saudara lelaki": "other_family",
    "sepupu": "other_family",
    "menantu": "other_family",
    "ibu saudara": "other_family",
    "bapa saudara": "other_family",
    "ahli keluarga": "other_family",
    "bapa": "other_family",
    "ayah": "other_family",
    "ibu": "other_family",
    "emak": "other_family",
    "侄女": "other_family",
    "侄子": "other_family",
    "外甥": "other_family",
    "外甥女": "other_family",
    "家人": "other_family",
    "父亲": "other_family",
    "母亲": "other_family",
    "someone in the family": "other_family",
    # a helper, a friend, a neighbour
    "maid": "helper",
    "domestic helper": "helper",
    "pembantu": "helper",
    "pembantu rumah": "helper",
    "帮手": "helper",
    "女佣": "helper",
    "保姆": "helper",
    "kawan": "friend",
    "sahabat": "friend",
    "朋友": "friend",
    "neighbor": "neighbour",
    "jiran": "neighbour",
    "邻居": "neighbour",
}

_OWNERS = ("your ", "my ", "their ", "his ", "her ")
_MALAY_OWNERS = (" anda", " saya", " mereka", " dia")
_CHINESE_OWNERS = ("您的", "你的", "我的", "他们的", "他的", "她的")


def code_of(phrase: str | None) -> str | None:
    """The code for what was kept: the code itself, a phrase this knows (with "your", "anda"
    or "您的" and the like taken off), or `other`."""
    if phrase is None:
        return None
    words = re.sub(r"[\s.,;:!?，。！？（）()]+", " ", phrase).strip().lower()
    if words in CODES:
        return words
    for owner in _OWNERS:
        words = words.removeprefix(owner)
    for owner in _MALAY_OWNERS:
        words = words.removesuffix(owner)
    for owner in _CHINESE_OWNERS:
        words = words.removeprefix(owner)
    words = words.strip()
    if words in CODES:
        return words
    return SAID.get(words, "other")


def _stewardship() -> sa.TableClause:
    return sa.table(
        "stewardship", sa.column("id", sa.Uuid()), sa.column("relationship", sa.String())
    )


def upgrade() -> None:
    bind = op.get_bind()
    table = _stewardship()
    rows = bind.execute(
        sa.select(table.c.id, table.c.relationship).where(table.c.relationship.is_not(None))
    ).all()
    for row_id, kept in rows:
        code = code_of(kept)
        if code != kept:
            bind.execute(table.update().where(table.c.id == row_id).values(relationship=code))


def downgrade() -> None:
    """The codes are words already, and the phrases they replaced are not kept: a downgrade
    leaves them as they are, which the code before this revision reads as it read any words."""
