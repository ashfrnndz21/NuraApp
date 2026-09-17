# ADR 0015 — The content library reuses the pharmacist's review queue, but gates on
`review_status`, not on the first-fifty sample

**Date** 2026-09-17 · **Status** accepted · **Decided by** the builder, for the operator ·
**Story** Activities, Care Services, Resources, Community (docs/design-direction.md)

## Context

The owner's design direction adds four content features — Activities ("Stay engaged"), Care
Services ("Professional help"), Resources ("Guides & support") and Community (Local Events,
Volunteer, Support Groups) — and says plainly: *"Yes: curated listings, reviewed before they
show"* / *"reviewed"* for every one of them. The build brief goes further: because the owner
has decided to seek no clinical sign-off for now, a care service or a support group is advice
about where to get help, and an unreviewed item must never be shown as if it were checked. The
brief points at the existing mechanism: ADR 0007's pharmacist review queue, `REVIEWED_TYPES`,
and the guard test that holds a new card type to it.

ADR 0007's queue was built for a different problem: a *rendering* of a card, generated fresh
for a person from his own record, sampled — the first fifty of each type, no more — so a
pharmacist reads a representative slice without having to read every card ever rendered. It
does not hold anything up: card 51 is shown the moment it is made, sampled or not.

The content library is not that. It is a small, hand-curated catalogue (a few dozen rows, not
an endless stream), and none of it may be shown even once before a pharmacist has seen it.

## Decision

1. **Six new `CardType` members** — `ACTIVITY`, `CARE_SERVICE`, `RESOURCE`, `LOCAL_EVENT`,
   `VOLUNTEER`, `SUPPORT_GROUP` — join `SUPPLY_OF` (mapped to `Supply.LEARNING`, the section
   for curated, non-personal explainers) and `REVIEWED_TYPES`/`KEPT_AS_WRITTEN` in
   `app.language.review`. This is what makes `tests/test_review_queue.py`'s existing guard
   (`test_every_card_type_he_is_shown_is_reviewed`) fail loudly if a future content type is
   added to the supply and forgotten here — the brief's own words for what "extend the guard
   test" must achieve. `tests/test_content.py::test_every_content_type_is_in_the_catalogue`
   pins the same equivalence from the content module's side.
2. **A `ContentItem` is queued once, in full, not sampled.** `app.delivery.content.service.
   queue_content_item` runs `app.language.review.deidentify` — the exact function a card's
   first fifty go through — over the item's title, body and summary, and writes a
   `ReviewItem` under `ReviewKind.CARD` and the item's own `card_type`. It reaches the very
   same `GET /review/queue`, `GET /review/status` and `POST /review/items/{id}/approve` a
   pharmacist already uses for cards. What is different is that nothing calls
   `review.sample_card`'s fifty-deep counter: every item is queued, not a sample of them.
3. **Visibility is gated by the content library's own `review_status` column** (`pending`,
   `approved`, `rejected` — the same three states `Source.review_status` already uses for the
   learning-card allowlist), not by `ReviewItem.verdict` read live on every request. A
   `PENDING` row is reconciled against its `ReviewItem`'s verdict on the next read
   (`service._reconcile_pending`, the content module's half of a handshake `review.decide`
   does not know exists — the same shape `review.queue_pending_sources` already uses to catch
   up a `Source` row set pending outside the review flow). `list_content` and `read_content`
   answer `APPROVED` rows only; a row that is missing, still pending, rejected, or held in
   another region all refuse with the same `NoSuchContentItem` — the same reasoning ADR 0007
   itself uses for `NoKey`: the words for "not there" and "not yours yet" must be identical,
   or an unreviewed item's existence leaks by the shape of the refusal.

## Consequences

- `GET /review/status`'s `flag` (first-fifty-reviewed) will read `true` for these six types
  only once fifty items of a type are queued and decided — a bar today's small, curated
  catalogue will not reach for some time. That flag is cosmetic for this module: real gating
  is `ContentItem.review_status`, checked on every read, not `QueueStatus.flag`. A future
  pass that wants the status page itself to say "content is fully reviewed" at a lower bar is
  a follow-up, not a gap in the gate.
- A pharmacist decides a content item exactly where she already works (the review queue), so
  no new staff-facing screen or endpoint was built for this story.
- The content library is global, region-pinned data, not profile data (like `Source`): a
  `ContentItem` row carries no `profile_id` and is read through a profile's `KeyContext` only
  to learn his region and language, under `Scope.PROFILE` — the one scope every key holds.
- **Classification.** `content_item.*` is operational in the PDPA data map (`scripts/
  data_map.py`), not health: it is curated copy shown to everyone in a region, not a fact
  about any one person. The brief asks, rightly, whether a person's *interactions* with this
  content are health data — which support group he opens can say something about a
  condition. This module deliberately does not create a place where that could be recorded:
  no new "viewed" or "saved" table was built, and content routes write no row-level audit
  entry naming a specific item (the existing `audit_entry.target_id`, already classified
  `AUDIT`, is the only trace a read leaves, and it names the route, not the item). If a future
  story adds engagement tracking for this content (a "save for later", a tap-through), that
  table's classification will need to be `health` and the same care ADR 0007 gives review
  samples, at that time — this ADR's decision not to build it now, not that it would be safe
  to build carelessly later.

## Alternatives considered

- **Reuse `sample_card`'s first-fifty sampling as-is.** Rejected: it never holds up rendering
  91, and this content must be held up entirely until a pharmacist has seen it.
- **A dedicated `ReviewKind.CONTENT` with `content_item_id` on `ReviewItem`.** Would let
  `review.decide` sync `ContentItem.review_status` directly, the way it already does for
  `ReviewKind.SOURCE`. Rejected for this pass to avoid widening `app/language/`'s own schema
  and `decide()`'s special-casing for a story outside that module's ownership; the read-time
  reconciliation in `service.py` gets the same effect without it. Worth revisiting if a
  second module wants the same "queued in full, gated on its own status" shape `ContentItem`
  uses, since at that point a shared mechanism earns its keep.
- **Auto-approve seeded fixture content.** Rejected outright: it would make the seed script
  the thing deciding review status, defeating the entire point the owner asked for. Fixture
  content sits `pending`, exactly like anything else, until a pharmacist reads and approves it
  through the real queue (`tests/test_content.py`'s HTTP tests walk this end to end).
