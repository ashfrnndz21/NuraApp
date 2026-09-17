"""#192/#218: sixteen reads across audit, delivery, safety, identity and WhatsApp ordered
"newest first" by a timestamp column alone, with no tie-breaker. A timestamp is not unique —
two rows written in the same request tie, and every checkpoint, `make web-e2e` and the demo
run on a frozen clock, where far more than two can tie — and a UUID4 primary key cannot break
the tie either, since it carries no order. The CI job built for #192 found this: ten
checkpoints failing, deterministically, only under its frozen clock.

Fixing the sixteen left one checkpoint still failing: checkpoint 13's "Mei reads Pa's notes
as his chief" — word for word the false regression reported on #190. The cause is the same
pattern, one call short of the sixteen: `app.consent.service.require_consent` picks the
consent a key is cut from with `sorted(active, key=lambda row: as_utc(row.granted_at),
reverse=True)`, in Python, so a grep for `.order_by(` never found it. Two consents for Mei
tie under the frozen clock — the claim's, and the one Pa gives moments later naming her
notes too — and the tie let the older, narrower one win, so the "chief" key cut on it opened
everything but the notes it was supposed to add. `Consent` gets `seq` alongside the sixteen.

A wider sweep (`grep -rn granted_at app/`) turned up a dozen more places that sort `Key` rows
by `granted_at` with no tie-breaker or a weak one (two already carry a `str(id)` tiebreak of
their own). All but one only build a list or a line of prose from every key — display, not a
decision, the same as the trail or the self-search queue — and are not touched here; they are
reported, not fixed, in the PR that carries this migration. None of them is proven to break a
checkpoint the way the consent read did.

`app.db.monotonic` (a class decorator) gives every row of a decorated table a `seq`: the
value the database itself hands out, atomically, at insert time — the row's real position in
write order, immune to the clock. Twelve tables get it: the audit trail, whose whole purpose
is telling him what happened in what order, so a mere stable-but-arbitrary tiebreaker is not
enough; `consent`, above; and ten more where a tie makes a *decision* arbitrary (which
delivery settings apply, which login challenge a code was sent for, which tablet a reply
answers, a reader's own last-looked baseline, the newest reading on the emergency card, the
last feed page cached for offline, and the watched feeling note or family message a nudge is
built from, which return on the first match in a loop). Two more tables (red flags, the
self-search queue) only order a listing for someone to browse, every row of it read regardless
of order — a tie there makes the order unstable, not wrong, and ordering by the existing `id`
is enough; they are not touched here.

Existing rows get `seq=0`: every one of them sorts as older than anything written from here
on, which is the safe direction to be wrong in (nothing already on a profile is ever picked
as "newest" over a fresh write) *if* this app has no production data yet to reorder properly —
an assumption, not a settled fact, and this migration does not check it.

Where `seq` actually comes from is the second half of this migration, added after independent
review proved the first version unsafe under load on a real Postgres 16: a shared counter row
taken with `UPDATE ... RETURNING` is held by whichever transaction touched it until that
transaction commits, and this app commits one transaction per HTTP request
(`app.channels.api.deps.db`) that, for nearly every read and write, writes an `audit_entry` —
one of the twelve tables below — through `app.audit.trail.record`. The review reproduced both
failure modes directly: one request's still-open transaction blocked a second, wholly
unrelated request's insert on `audit_entry` for the entire time the first stayed open; and two
transactions taking two tables' counter rows in opposite order deadlocked. `seq_counters`
(kept below, and still built on every dialect so the migrated schema matches what
`Base.metadata.create_all` builds for the tests that don't run migrations at all) is real
insurance for SQLite only, which this app's tests and a laptop's `make dev` are the only users
of and which does not have this problem to begin with — every write there already begins
IMMEDIATE (`app.db.make_engine`), serialising the whole database one writer at a time, so a
row lock over one more row costs nothing that is not already true. Postgres — every real
deployment — instead gets a `SEQUENCE` per table: `nextval()` takes no row lock held for a
transaction's life, so it cannot block a concurrent insert and cannot deadlock against another
table's sequence (both reproduced fixed, the same way they were reproduced broken, in
`tests/test_monotonic_seq_concurrency.py`, Postgres-only, `backend-postgres` CI).

Revision ID: 0040_monotonic_tiebreak
Revises: 0039_feeling_question_marker
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_monotonic_tiebreak"
down_revision = "0039_feeling_question_marker"
branch_labels = None
depends_on = None

SEQUENCED_TABLES = (
    "audit_entry",
    "consent",
    "delivery_settings",
    "login_challenge",
    "whatsapp_dose_question",
    "event",
    "last_looked",
    "feed_page",
    "feeling_tap",
    "feeling_note",
    "thread_message",
)


def _sequence_name(table: str) -> str:
    return f"{table}_seq_seq"


def upgrade() -> None:
    op.create_table(
        "seq_counters",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.BigInteger(), nullable=False, server_default="0"),
    )
    on_postgres = op.get_bind().dialect.name == "postgresql"
    for table in SEQUENCED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("seq", sa.BigInteger(), nullable=False, server_default="0")
            )
        op.create_index(f"ix_{table}_seq", table, ["seq"])
        # `app.db.monotonic` reads `seq` from this sequence on Postgres, never from
        # `seq_counters` (see the docstring above for why); SQLite has no CREATE SEQUENCE,
        # and does not need one.
        if on_postgres:
            op.execute(f"CREATE SEQUENCE {_sequence_name(table)}")


def downgrade() -> None:
    on_postgres = op.get_bind().dialect.name == "postgresql"
    for table in reversed(SEQUENCED_TABLES):
        if on_postgres:
            op.execute(f"DROP SEQUENCE {_sequence_name(table)}")
        op.drop_index(f"ix_{table}_seq", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("seq")
    op.drop_table("seq_counters")
