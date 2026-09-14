# ADR 0009 — Times are stored as UTC

**Date** 2026-09-15 · **Status** proposed · **Decided by** a builder, for the operator's review

## Context

Every datetime column was typed `DateTime(timezone=True)` through the declarative type map.
Postgres keeps the offset; SQLite, the laptop's and CI's database, does not. SQLAlchemy's
SQLite type writes the wall-clock fields and drops the offset, and `as_utc` read the bare
value back as UTC. So a visit booked at 09:00+08:00 was stored as 09:00, came back as 09:00
UTC, and was said to the patient as 5 in the afternoon. Every datetime column was affected:
appointments, events, the validity of facts, delivery times, audit timestamps.

## Decisions

1. **One column type, `app.db.UTCDateTime`, for every datetime.** A `TypeDecorator` over
   `DateTime(timezone=True)`, named in the type map for `datetime`, so every
   `Mapped[datetime]` column uses it with no change to a model.
2. **On the way in, an aware datetime becomes UTC** before the database sees it. SQLite then
   stores the UTC wall clock; Postgres stores the same instant it always did.
3. **A naive datetime is refused** with `NaiveDatetime`, never assumed to be UTC. A time with
   no offset is a bug in the caller: the fix is `app.clock` or an aware value.
4. **On the way out, every value is aware UTC.** A bare value from SQLite is UTC by
   construction (point 2), so it gets `timezone.utc`; an aware one is converted to UTC.
5. **No migration.** The SQL type is unchanged (`DATETIME` / `TIMESTAMP WITH TIME ZONE`), so
   Alembic's autogenerate shows no diff, and the PDPA data map still names the column type
   `DateTime` (`scripts.data_map` names a decorated type by the type it wraps).
6. **Clients send times with an offset.** Input models take `AwareDatetime`, so a naive time
   from a client is a 422 at the door rather than a refusal at the database.

## Consequences

- Rows already on a laptop's `dev.db` written at a non-UTC offset keep their wrong instant;
  `make reset-db` starts over. Postgres rows were always right.
- `as_utc` is now a no-op on anything read from a column. It stays for values that did not
  come from one.
- A new migration that autogenerates a datetime column should spell it
  `sa.DateTime(timezone=True)`, as every existing migration does.
