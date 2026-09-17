# ADR 0007 — The pharmacist's review queue is operator scope, and holds no profile

**Date** 2026-09-15 · **Status** accepted · **Decided by** the operator, for the owner · **Stories** E22-04 (with E22-02, E22-03)

## Context

The health feed spec asks for a pharmacist's review before a new source is used and of the first fifty cards (docs/health-feed-spec.md §3.5, §7, §10: "Pharmacist review of the initial allowlist and the first 50 cards"). The backlog row's acceptance line is *nothing from a new source reaches a patient before review*.

Everything else in Nura is reached through a key on one profile (`app/keys/`). A pharmacist is not on anyone's family list, holds no key, and reviews across every profile on the deployment. Giving her a key would put her on each family's list and on each owner's trail; giving her a "staff" flag on a patient key would make every key a possible way into the queue. Neither is what she is.

The first fifty cards are rendered for real people: they carry names ("Mei can see it too."), doctors ("You see Dr Tan on Monday 21 September."), numbers, and — on some cards — his own words.

## Decision

1. **Operator scope, not a patient key.** The queue is served under `/review/*` (and its `/api` twin), outside `/profiles/{id}/`, so no key context is resolved and no profile route matrix includes it. Every route requires a bearer token on the deployment's staff list, `NURA_REVIEW_STAFF_TOKENS` (`handle:token` pairs, from the environment, never the repo; `app/settings.py`). A patient's session token is not on the list and is refused, `NotStaff`, 403 — the same answer as no token. Tokens are compared in constant time against every entry. A token shorter than 24 characters, a malformed handle, a handle listed twice, or a laptop's token (`nura-dev-…`) outside a dev run refuses to start the process. Unset, the queue answers nobody.
2. **No profile in the table.** `review_item` is not `ProfileScoped` and has no column that points at a profile or a person. A decision is signed with the staff handle (`decided_by`), which is not a person on anyone's record. The row is regional like every row: an SG sample stays in the SG database.
3. **De-identified before it is written.** A card sample (`app.language.review.deidentify`) keeps lines only — headline, body, voice, why — and each line is matched back to the catalogue template it was filled from (`app.language.memory`): what went into a person's slot (`{who}`, `{name}`, `{told}`, `{patient}`, …) is written as `{name}`, the doctor as `{doctor}`; numbers, days and his plain words for medicines stay, because those are what the pharmacist is reading. Every name found in a slot anywhere on the card is then taken out of every line, and so is anything shaped like "Dr Tan". A line that matches no template is his record's own words — a memo, a note, a letter — and is not kept (`{words from his papers, not kept}`), except on a learning card or a notice, whose lines are compressed from a public allowlisted page and are exactly what needs a pharmacist's eye. No read of profile data is made to do this: the names come from the card's own slots, so the sampler adds no line to anyone's trail.
4. **The first fifty, per card type, distinct.** `items.create_item` offers every card for a patient to `sample_card`, in a savepoint of its own; until fifty renderings of that type are queued it keeps one more, and never the same de-identified rendering twice. A type whose first fifty are not all decided shows `flag: true` in `GET /review/status`. Card types are not held back while flagged: the spec asks for review of the first fifty, not a gate on them.
5. **A new source is unused until approved.** `POST /review/sources` puts the publisher in `source` as pending and not allowlisted; `feed.sources.usable` already requires allowlisted *and* approved, so no job searches it and no card cites it. Approving allowlists it; rejecting (with a reason) keeps it off. A pending source put in the table any other way is queued the next time the queue is read.
6. **A rewrite is a proposal.** `POST /review/items/{id}/rewrite` stores the reviewer's lines as `proposed` — each changed line, the words now, the words proposed, and the catalogue id of the line it would replace — after every proposed line passes the plain-words verifier. It edits no production text: a person makes the change in the catalogue, where `make plain-words` and `make language` hold it like any other line. `GET /review/proposals` lists them.
7. **Decided once.** An item is approved, rejected or rewritten once (`AlreadyReviewed`, 409); the decision columns may be set and never unset (`app.db.frozen`).

## Consequences

- Staff actions are recorded on the item (who, when, why) and in the log under `nura.review` by item id and handle, never with content. They are not on any owner's trail, because they touch nothing of his.
- In the PDPA data map (`scripts/data_map.py`, `docs/trust/pdpa-data-map.md`) the queue's words — `review_item.lines`, `.proposed` and `.reason` — are **health, de-identified**: a sample keeps his readings, days and plain names for medicines, a rewrite proposes such lines, and a reason is free text a pharmacist may quote a line into. They are handled as health data: in region, never to an analytics vendor, nothing trains on them. The rest of the row — kind, card type, ids, digest, verdict, the staff handle, times — is operational.
- The residual risk of de-identification is in the values kept on purpose — a number, a day, a medicine's plain name. Alone they identify nobody; together, on one card, a determined reader with other data might narrow it down. The queue is operator scope, in region, and read by the pharmacist only; a per-language balance of samples and a shorter retention after the first fifty are decided are follow-ups.
- When a staff identity provider exists (SSO), it replaces the token list behind the same `staff` dependency; nothing else changes.
- The queue is served on the patient app's own origin for now (`/app/review/`, W6 #137) — fine while nothing behind either surface is real. Before real data it moves to its own origin, `NURA_REVIEW_ORIGIN` (#145, ADR 0008 "Before real data", `docs/deploy.md`).

## The clinical-safety review (2026-09-15)

The `clinical-safety-reviewer` pass on this change asked for, and got:

- **A sample never costs him the card.** `items._sample` runs where every card is written, a red flag's included; it now rolls back and logs *any* exception, not only refusals and database errors (`tests/test_review_queue.py::test_a_sample_that_fails_never_costs_him_the_card`).
- **Names with particles are names.** "Ahmad bin Ali", "Siti binti Hassan", "Siva a/l Kumar" fill a person's slot like "Mei" does (`review.NAME_JOINERS`).
- **On a learning card or a notice, a line that is plainly a catalogue template loses its people whatever filled the slot** — when at least 40% of its letters are the template's own (`review.TEMPLATE_SHARE`). A compressed sentence that only brushes a thin template ("{name} is {value}.") is kept as written, so "Blood pressure is how hard your blood pushes." is not mistaken for a name.
- **Amounts are said whole** in the voice script (E22-03): "1,000 mg", "1/2 tablet", "0.5 mg" in all three languages; a fraction with no everyday words stays digits.

Two points were left to the operator:

- **The classification of the queue's words.** The story asked for review items to classify as operational/de-identified; the reviewer recommended *health (de-identified)*, because a sample keeps readings, days and his plain names for medicines. **The operator decided health (de-identified) on 2026-09-15**, for `review_item.lines`, `.proposed` and `.reason` (free text a pharmacist may quote a line into); the data map is regenerated.
- **"Your body salt" for potassium** (`trend_strings.NAMES`, now 您身体的盐 in Chinese as in English and Malay) follows the glossary's own row ("A body salt. Doctors call it potassium."). The reviewer notes that salt substitutes are potassium chloride, so "salt" may mislead someone told to watch his potassium. That is the glossary's wording to settle with the pharmacist; the operator has filed it for the pharmacist, and the wording stays as it is until then.

## Alternatives considered

- **A pharmacist `KeyRole`.** Keys are per profile and cut by the owner; the queue is across profiles and nobody's to cut. Rejected.
- **An admin flag on a patient's account.** Makes every patient session a possible door into operator data. Rejected.
- **Storing samples as templates only** (the catalogue line, slots unfilled). Loses the numbers, days and plain names the pharmacist needs to judge a rendering. Rejected in favour of template-guided de-identification.
