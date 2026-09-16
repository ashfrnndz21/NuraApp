# PDPA data map, breach process and the data protection officer

**Story** E16-05 · **Acceptance** data map covers both countries; breach runbook tested · **Status** data map generated from the models and held current by a test; breach runbook written, tabletop owed before the first family on TestFlight; DPO to be named

Nura holds health data for people in Singapore and Malaysia, one deployment per country. Both countries have a Personal Data Protection Act; both treat health data as needing explicit consent; both now expect a data map, a breach process and a named officer. This document is those three things, written against the code rather than beside it: the inventory below is generated from the SQLAlchemy models and a test fails when the two drift. Statutory windows and section numbers are stated as the team understands them and marked **to be verified by counsel** — they are the questions in §9, not conclusions.

The voice of the other trust documents applies: what the app enforces has a test; what it does not enforce is said plainly.

---

## 1. What is held, and where

One backend, one database and one object store per region (`app/regions.py`; `app/settings.py`). A Person and a Profile are pinned to a region when created and never move; every deployment refuses to read or write a row pinned elsewhere (`guard_region`; `tests/test_memory_review.py:217`, `:979`). Artefact bytes — photos, PDFs, recordings — live in the region's object store under a storage key; the database holds the key and the digest, never the content (`tests/test_ingestion.py:236`).

Three kinds of thing are held:

- **Accounts**: who a person is (`person`, `login_challenge`, `session`) — the phone number or email he signed in with, his display name, his language.
- **The health graph**: one profile per patient, and everything on it — artefacts, events, facts, episodes, providers, appointments, review cards, medicines, State, notes. Every row names its `profile_id`, and every read of it goes through the keys module with a key context (`app/keys/`).
- **The record of reach**: who may see what and on what footing (`key`, `consent`, `stewardship`, `confirmation`), and who did see what (`audit_entry`). The trail never holds the content it guards.

## 2. The inventory, generated from the models

`python3 -m scripts.data_map` walks every table on the metadata and prints this block; `python3 -m scripts.data_map --check` fails when the block below differs from the models, and `tests/test_data_map.py` runs that check. The classification is a person's decision, written once per column in `backend/scripts/data_map.py`, and the script refuses to run with a column nobody has classified. The type is the SQLAlchemy type's name, the same on SQLite and Postgres.

The five classifications:

| Classification | Meaning | Handling |
|---|---|---|
| **identifier** | Points at a person: a phone number, an email, a display name, a person id or a link to one. | Never leaves the region; never in a log outside it; never in a URL. Redacted in structured logs (`backend/CLAUDE.md`). |
| **health** | Says something about the person's health, or is a reference to something that does: a fact, an artefact key, a medicine line, a posture. Sensitive personal data in both Acts. | Read only through a key context; every read on the trail; never to an analytics vendor; nothing trains on it. |
| **consent** | What was agreed to, by whom, in which words, and when it stopped: the record of reach. | Outlives the graph; exportable to the person on request (`app/consent/export.py`). |
| **audit** | Who reached what, when, how, and whether they got it. | Owner-visible; never holds content; retained for the life of the profile and beyond (see §4). |
| **operational** | Timestamps, sequence numbers, hashes, enum states, ids of rows: needed to run, says nothing about a person on its own. | Kept with the row it belongs to. |

A note on the rows that look operational and are not. `profile_id` is an identifier wherever it appears: it is the link from any row to the person it is about. A row's own `id` is classified as the row — a fact id is a reference to health data, a consent id is the consent record — and only a sign-in row's id points at nothing about a person. A reference to a health row (`fact.supersedes_id`, `confirmation.subject_id`), a kind that says what happened (`state_snapshot.trigger`, `medication_line.source_kind`) and a content type that says an artefact is a recording are health, by the rule above. `state_snapshot.family` is an identifier because it names who holds keys; the other five dimensions are health. `review_item` (E22-04, ADR 0007) is the pharmacist's review queue: operator data with no profile and no person in it — a card's lines are stored with every name taken out and his record's own words left out, a source is a publisher, `decided_by` is a staff handle. Its words — `lines`, `proposed` and `reason` — are health, de-identified: a sample keeps his readings, days and plain names for medicines, and a reason is free text a pharmacist may quote a line into (the operator's decision, 2026-09-15). The rest of the row is operational.

<!-- data-map:begin -->
81 tables, 921 columns: 182 identifier, 406 health, 46 consent, 16 audit, 271 operational. Generated by `python3 -m scripts.data_map`; do not edit by hand.

| Table | Column | Type | Nullable | Classification |
|---|---|---|---|---|
| `erasure_record` | `id` | Uuid | no | audit |
| `erasure_record` | `profile_id` | Uuid | no | identifier |
| `erasure_record` | `region` | Enum | no | operational |
| `erasure_record` | `requested_by_person_id` | Uuid | no | identifier |
| `erasure_record` | `requested_at` | DateTime | no | audit |
| `erasure_record` | `erased_at` | DateTime | no | audit |
| `erasure_record` | `consents` | JSON | no | consent |
| `erasure_record` | `removed` | JSON | no | audit |
| `person` | `id` | Uuid | no | identifier |
| `person` | `region` | Enum | no | operational |
| `person` | `display_name` | String | no | identifier |
| `person` | `language` | String | no | operational |
| `person` | `phone_e164` | String | yes | identifier |
| `person` | `email` | String | yes | identifier |
| `person` | `created_at` | DateTime | no | operational |
| `person` | `named_by_person_id` | Uuid | yes | identifier |
| `source` | `id` | Uuid | no | operational |
| `source` | `name` | String | no | operational |
| `source` | `domain` | String | no | operational |
| `source` | `kind` | Enum | no | operational |
| `source` | `regions` | JSON | no | operational |
| `source` | `languages` | JSON | no | operational |
| `source` | `allowlisted` | Boolean | no | operational |
| `source` | `review_status` | Enum | no | operational |
| `source` | `added_at` | DateTime | no | operational |
| `whatsapp_receipt` | `id` | Uuid | no | operational |
| `whatsapp_receipt` | `provider_message_id` | String | no | operational |
| `whatsapp_receipt` | `first_seen_at` | DateTime | no | operational |
| `whatsapp_receipt` | `handled_at` | DateTime | yes | operational |
| `whatsapp_receipt` | `failures` | Integer | no | operational |
| `whatsapp_receipt` | `last_failed_at` | DateTime | yes | operational |
| `whatsapp_receipt` | `last_failure` | String | yes | operational |
| `login_challenge` | `id` | Uuid | no | operational |
| `login_challenge` | `region` | Enum | no | operational |
| `login_challenge` | `channel` | Enum | no | operational |
| `login_challenge` | `phone_e164` | String | yes | identifier |
| `login_challenge` | `email` | String | yes | identifier |
| `login_challenge` | `code_hash` | String | no | operational |
| `login_challenge` | `display_name` | String | yes | identifier |
| `login_challenge` | `language` | String | yes | operational |
| `login_challenge` | `issued_at` | DateTime | no | operational |
| `login_challenge` | `expires_at` | DateTime | no | operational |
| `login_challenge` | `attempts` | Integer | no | operational |
| `login_challenge` | `consumed_at` | DateTime | yes | operational |
| `login_challenge` | `person_id` | Uuid | yes | identifier |
| `profile` | `id` | Uuid | no | identifier |
| `profile` | `region` | Enum | no | operational |
| `profile` | `display_name` | String | no | identifier |
| `profile` | `language` | String | no | operational |
| `profile` | `owner_person_id` | Uuid | yes | identifier |
| `profile` | `patient_phone_e164` | String | yes | identifier |
| `profile` | `created_at` | DateTime | no | operational |
| `review_item` | `id` | Uuid | no | operational |
| `review_item` | `kind` | Enum | no | operational |
| `review_item` | `card_type` | String | yes | operational |
| `review_item` | `sample_number` | Integer | yes | operational |
| `review_item` | `source_id` | Uuid | yes | operational |
| `review_item` | `language` | String | yes | operational |
| `review_item` | `lines` | JSON | no | health |
| `review_item` | `catalogue_ids` | JSON | no | operational |
| `review_item` | `digest` | String | no | operational |
| `review_item` | `verdict` | Enum | no | operational |
| `review_item` | `reason` | String | yes | health |
| `review_item` | `proposed` | JSON | yes | health |
| `review_item` | `decided_by` | String | yes | operational |
| `review_item` | `created_at` | DateTime | no | operational |
| `review_item` | `decided_at` | DateTime | yes | operational |
| `session` | `id` | Uuid | no | operational |
| `session` | `region` | Enum | no | operational |
| `session` | `person_id` | Uuid | no | identifier |
| `session` | `token_hash` | String | no | operational |
| `session` | `created_at` | DateTime | no | operational |
| `session` | `expires_at` | DateTime | no | operational |
| `session` | `revoked_at` | DateTime | yes | operational |
| `account_closure` | `id` | Uuid | no | operational |
| `account_closure` | `requested_by_person_id` | Uuid | no | identifier |
| `account_closure` | `requested_at` | DateTime | no | operational |
| `account_closure` | `delete_after` | DateTime | no | operational |
| `account_closure` | `undone_at` | DateTime | yes | operational |
| `account_closure` | `undone_by_person_id` | Uuid | yes | identifier |
| `account_closure` | `profile_id` | Uuid | no | identifier |
| `artifact` | `id` | Uuid | no | health |
| `artifact` | `kind` | Enum | no | health |
| `artifact` | `storage_key` | String | no | health |
| `artifact` | `content_type` | String | no | health |
| `artifact` | `sha256` | String | no | operational |
| `artifact` | `captured_at` | DateTime | no | health |
| `artifact` | `source_channel` | Enum | no | operational |
| `artifact` | `region` | Enum | no | operational |
| `artifact` | `stored_at` | DateTime | no | operational |
| `artifact` | `profile_id` | Uuid | no | identifier |
| `artifact` | `written_scope` | Enum | no | consent |
| `biography_session` | `id` | Uuid | no | health |
| `biography_session` | `opened_by_person_id` | Uuid | no | identifier |
| `biography_session` | `opened_at` | DateTime | no | operational |
| `biography_session` | `read_back_at` | DateTime | yes | operational |
| `biography_session` | `read_back_by_person_id` | Uuid | yes | identifier |
| `biography_session` | `closed_at` | DateTime | yes | operational |
| `biography_session` | `closed_by_person_id` | Uuid | yes | identifier |
| `biography_session` | `profile_id` | Uuid | no | identifier |
| `confirmation` | `id` | Uuid | no | consent |
| `confirmation` | `person_id` | Uuid | no | identifier |
| `confirmation` | `subject` | Enum | no | health |
| `confirmation` | `subject_id` | Uuid | yes | health |
| `confirmation` | `content_digest` | String | no | operational |
| `confirmation` | `created_at` | DateTime | no | operational |
| `confirmation` | `expires_at` | DateTime | no | operational |
| `confirmation` | `consumed_at` | DateTime | yes | operational |
| `confirmation` | `channel` | Enum | no | operational |
| `confirmation` | `profile_id` | Uuid | no | identifier |
| `delivery_settings` | `id` | Uuid | no | operational |
| `delivery_settings` | `skip_quiet_days` | Boolean | no | operational |
| `delivery_settings` | `quiet_from` | Time | yes | operational |
| `delivery_settings` | `quiet_until` | Time | yes | operational |
| `delivery_settings` | `channels` | JSON | no | operational |
| `delivery_settings` | `caps` | JSON | no | operational |
| `delivery_settings` | `set_by_person_id` | Uuid | no | identifier |
| `delivery_settings` | `set_at` | DateTime | no | operational |
| `delivery_settings` | `profile_id` | Uuid | no | identifier |
| `episode` | `id` | Uuid | no | health |
| `episode` | `kind` | Enum | no | health |
| `episode` | `label` | String | no | health |
| `episode` | `opened_at` | DateTime | no | health |
| `episode` | `closed_at` | DateTime | yes | health |
| `episode` | `profile_id` | Uuid | no | identifier |
| `feed_page` | `id` | Uuid | no | operational |
| `feed_page` | `person_id` | Uuid | no | identifier |
| `feed_page` | `audience` | Enum | no | operational |
| `feed_page` | `item_ids` | JSON | no | health |
| `feed_page` | `cursor` | String | yes | operational |
| `feed_page` | `next_cursor` | String | yes | operational |
| `feed_page` | `quiet` | Boolean | no | operational |
| `feed_page` | `held_by_caps` | JSON | no | operational |
| `feed_page` | `rendered_at` | DateTime | no | operational |
| `feed_page` | `profile_id` | Uuid | no | identifier |
| `last_looked` | `id` | Uuid | no | operational |
| `last_looked` | `person_id` | Uuid | no | identifier |
| `last_looked` | `looked_at` | DateTime | no | operational |
| `last_looked` | `appointments` | JSON | no | health |
| `last_looked` | `profile_id` | Uuid | no | identifier |
| `note` | `id` | Uuid | no | health |
| `note` | `text` | String | no | health |
| `note` | `written_at` | DateTime | no | health |
| `note` | `profile_id` | Uuid | no | identifier |
| `privacy` | `id` | Uuid | no | consent |
| `privacy` | `scope` | Enum | no | consent |
| `privacy` | `marked_by_person_id` | Uuid | no | identifier |
| `privacy` | `marked_at` | DateTime | no | consent |
| `privacy` | `lifted_at` | DateTime | yes | consent |
| `privacy` | `lifted_by_person_id` | Uuid | yes | identifier |
| `privacy` | `profile_id` | Uuid | no | identifier |
| `provider` | `id` | Uuid | no | health |
| `provider` | `name` | String | no | health |
| `provider` | `kind` | Enum | no | health |
| `provider` | `phone_e164` | String | yes | health |
| `provider` | `address` | String | yes | health |
| `provider` | `region` | Enum | no | operational |
| `provider` | `added_at` | DateTime | no | operational |
| `provider` | `panel` | Boolean | no | health |
| `provider` | `opens_at` | Time | yes | operational |
| `provider` | `closes_at` | Time | yes | operational |
| `provider` | `profile_id` | Uuid | no | identifier |
| `push_subscription` | `id` | Uuid | no | operational |
| `push_subscription` | `person_id` | Uuid | no | identifier |
| `push_subscription` | `session_id` | Uuid | no | operational |
| `push_subscription` | `endpoint` | String | no | identifier |
| `push_subscription` | `p256dh` | String | no | operational |
| `push_subscription` | `auth` | String | no | operational |
| `push_subscription` | `created_at` | DateTime | no | operational |
| `push_subscription` | `revoked_at` | DateTime | yes | operational |
| `push_subscription` | `gone_at` | DateTime | yes | operational |
| `push_subscription` | `profile_id` | Uuid | no | identifier |
| `roster_slot` | `id` | Uuid | no | identifier |
| `roster_slot` | `person_id` | Uuid | no | identifier |
| `roster_slot` | `role` | Enum | no | identifier |
| `roster_slot` | `weekdays` | JSON | yes | operational |
| `roster_slot` | `starts_on` | Date | yes | operational |
| `roster_slot` | `ends_on` | Date | yes | operational |
| `roster_slot` | `from_time` | Time | no | operational |
| `roster_slot` | `to_time` | Time | no | operational |
| `roster_slot` | `added_by_person_id` | Uuid | no | identifier |
| `roster_slot` | `added_at` | DateTime | no | operational |
| `roster_slot` | `ended_at` | DateTime | yes | operational |
| `roster_slot` | `profile_id` | Uuid | no | identifier |
| `routine` | `id` | Uuid | no | health |
| `routine` | `anchors` | JSON | no | health |
| `routine` | `reading_prompts` | JSON | no | health |
| `routine` | `walks` | JSON | no | health |
| `routine` | `morning_card_at` | String | no | operational |
| `routine` | `supersedes_id` | Uuid | yes | health |
| `routine` | `superseded_at` | DateTime | yes | operational |
| `routine` | `set_by_person_id` | Uuid | no | identifier |
| `routine` | `set_at` | DateTime | no | operational |
| `routine` | `profile_id` | Uuid | no | identifier |
| `search_job` | `id` | Uuid | no | health |
| `search_job` | `kind` | Enum | no | operational |
| `search_job` | `terms` | JSON | no | health |
| `search_job` | `source_ids` | JSON | no | operational |
| `search_job` | `cadence` | String | no | operational |
| `search_job` | `reason` | JSON | no | health |
| `search_job` | `status` | Enum | no | operational |
| `search_job` | `results` | JSON | no | health |
| `search_job` | `enabled` | Boolean | no | operational |
| `search_job` | `created_by_person_id` | Uuid | no | identifier |
| `search_job` | `created_at` | DateTime | no | operational |
| `search_job` | `last_run_at` | DateTime | yes | operational |
| `search_job` | `profile_id` | Uuid | no | identifier |
| `whatsapp_group` | `id` | Uuid | no | health |
| `whatsapp_group` | `provider_group_id` | String | no | identifier |
| `whatsapp_group` | `opened_by_person_id` | Uuid | no | identifier |
| `whatsapp_group` | `opened_at` | DateTime | no | operational |
| `whatsapp_group` | `members_digest` | String | yes | identifier |
| `whatsapp_group` | `profile_id` | Uuid | no | identifier |
| `whatsapp_thread` | `id` | Uuid | no | health |
| `whatsapp_thread` | `person_id` | Uuid | no | identifier |
| `whatsapp_thread` | `is_patient` | Boolean | no | identifier |
| `whatsapp_thread` | `opened_at` | DateTime | no | operational |
| `whatsapp_thread` | `last_inbound_at` | DateTime | yes | operational |
| `whatsapp_thread` | `last_outbound_at` | DateTime | yes | operational |
| `whatsapp_thread` | `profile_id` | Uuid | no | identifier |
| `activation_plan` | `id` | Uuid | no | health |
| `activation_plan` | `session_id` | Uuid | yes | health |
| `activation_plan` | `breakfast_time` | String | no | health |
| `activation_plan` | `first_day` | Date | no | operational |
| `activation_plan` | `created_by_person_id` | Uuid | no | identifier |
| `activation_plan` | `created_at` | DateTime | no | operational |
| `activation_plan` | `profile_id` | Uuid | no | identifier |
| `appointment` | `id` | Uuid | no | health |
| `appointment` | `provider_id` | Uuid | no | health |
| `appointment` | `scheduled_at` | DateTime | no | health |
| `appointment` | `status` | Enum | no | health |
| `appointment` | `purpose` | String | no | health |
| `appointment` | `episode_id` | Uuid | yes | health |
| `appointment` | `confirmed_by_person_id` | Uuid | no | identifier |
| `appointment` | `status_changed_by_person_id` | Uuid | yes | identifier |
| `appointment` | `booked_at` | DateTime | no | operational |
| `appointment` | `profile_id` | Uuid | no | identifier |
| `consent` | `profile_id` | Uuid | no | identifier |
| `consent` | `id` | Uuid | no | consent |
| `consent` | `person_id` | Uuid | no | identifier |
| `consent` | `purpose` | Enum | no | consent |
| `consent` | `holder_person_id` | Uuid | yes | identifier |
| `consent` | `scopes` | JSON | yes | consent |
| `consent` | `text_version` | String | no | consent |
| `consent` | `language` | String | no | consent |
| `consent` | `wording_text` | Text | no | consent |
| `consent` | `captured_via` | Enum | no | consent |
| `consent` | `basis` | Enum | no | consent |
| `consent` | `basis_artifact_id` | Uuid | yes | consent |
| `consent` | `witness_person_id` | Uuid | yes | identifier |
| `consent` | `granted_at` | DateTime | no | consent |
| `consent` | `revoked_at` | DateTime | yes | consent |
| `consent` | `revoked_by_person_id` | Uuid | yes | identifier |
| `document` | `id` | Uuid | no | health |
| `document` | `artifact_id` | Uuid | no | health |
| `document` | `tag` | Enum | no | health |
| `document` | `added_by_person_id` | Uuid | no | identifier |
| `document` | `added_at` | DateTime | no | operational |
| `document` | `profile_id` | Uuid | no | identifier |
| `event` | `id` | Uuid | no | health |
| `event` | `kind` | Enum | no | health |
| `event` | `occurred_at` | DateTime | no | health |
| `event` | `source_channel` | Enum | no | operational |
| `event` | `label` | String | yes | health |
| `event` | `artifact_id` | Uuid | yes | health |
| `event` | `episode_id` | Uuid | yes | health |
| `event` | `recorded_at` | DateTime | no | operational |
| `event` | `profile_id` | Uuid | no | identifier |
| `event` | `written_scope` | Enum | no | consent |
| `insurer` | `id` | Uuid | no | identifier |
| `insurer` | `name` | String | yes | identifier |
| `insurer` | `policy_reference` | String | yes | identifier |
| `insurer` | `set_by_person_id` | Uuid | no | identifier |
| `insurer` | `confirmation_id` | Uuid | no | consent |
| `insurer` | `set_at` | DateTime | no | operational |
| `insurer` | `profile_id` | Uuid | no | identifier |
| `provider_note` | `id` | Uuid | no | health |
| `provider_note` | `provider_id` | Uuid | no | health |
| `provider_note` | `text` | String | no | health |
| `provider_note` | `written_by_person_id` | Uuid | no | identifier |
| `provider_note` | `written_at` | DateTime | no | operational |
| `provider_note` | `profile_id` | Uuid | no | identifier |
| `review_card` | `id` | Uuid | no | health |
| `review_card` | `artifact_id` | Uuid | no | health |
| `review_card` | `document_kind` | Enum | no | health |
| `review_card` | `document_date` | Date | yes | health |
| `review_card` | `high_risk_class` | String | yes | health |
| `review_card` | `asked_as` | Enum | yes | health |
| `review_card` | `source` | Enum | yes | operational |
| `review_card` | `created_at` | DateTime | no | operational |
| `review_card` | `confirmed_at` | DateTime | yes | operational |
| `review_card` | `confirmed_by_person_id` | Uuid | yes | identifier |
| `review_card` | `profile_id` | Uuid | no | identifier |
| `whatsapp_dose_question` | `id` | Uuid | no | health |
| `whatsapp_dose_question` | `thread_id` | Uuid | no | health |
| `whatsapp_dose_question` | `asked_at` | DateTime | no | operational |
| `whatsapp_dose_question` | `expires_at` | DateTime | no | operational |
| `whatsapp_dose_question` | `doses` | JSON | no | health |
| `whatsapp_dose_question` | `answered_at` | DateTime | yes | operational |
| `whatsapp_dose_question` | `profile_id` | Uuid | no | identifier |
| `attachment` | `id` | Uuid | no | health |
| `attachment` | `artifact_id` | Uuid | no | health |
| `attachment` | `episode_id` | Uuid | yes | health |
| `attachment` | `appointment_id` | Uuid | yes | health |
| `attachment` | `how` | Enum | no | operational |
| `attachment` | `attached_by_person_id` | Uuid | no | identifier |
| `attachment` | `attached_at` | DateTime | no | operational |
| `attachment` | `profile_id` | Uuid | no | identifier |
| `biography_paper` | `id` | Uuid | no | health |
| `biography_paper` | `session_id` | Uuid | no | health |
| `biography_paper` | `position` | Integer | no | operational |
| `biography_paper` | `artifact_id` | Uuid | no | health |
| `biography_paper` | `card_id` | Uuid | no | health |
| `biography_paper` | `paper` | Enum | no | health |
| `biography_paper` | `added_by_person_id` | Uuid | no | identifier |
| `biography_paper` | `added_at` | DateTime | no | operational |
| `biography_paper` | `profile_id` | Uuid | no | identifier |
| `connector` | `id` | Uuid | no | consent |
| `connector` | `kind` | Enum | no | consent |
| `connector` | `source` | Enum | no | operational |
| `connector` | `consent_id` | Uuid | no | consent |
| `connector` | `connected_by_person_id` | Uuid | no | identifier |
| `connector` | `connected_at` | DateTime | no | consent |
| `connector` | `profile_id` | Uuid | no | identifier |
| `consult_recording` | `id` | Uuid | no | health |
| `consult_recording` | `appointment_id` | Uuid | no | health |
| `consult_recording` | `artifact_id` | Uuid | no | health |
| `consult_recording` | `transcript_artifact_id` | Uuid | yes | health |
| `consult_recording` | `consent_id` | Uuid | no | consent |
| `consult_recording` | `duration_s` | Float | no | health |
| `consult_recording` | `started_at` | DateTime | no | health |
| `consult_recording` | `notice_language` | String | no | operational |
| `consult_recording` | `doctor_named` | Boolean | no | consent |
| `consult_recording` | `heard_confidence` | Float | yes | operational |
| `consult_recording` | `recorded_by_person_id` | Uuid | no | identifier |
| `consult_recording` | `stored_at` | DateTime | no | operational |
| `consult_recording` | `profile_id` | Uuid | no | identifier |
| `event_note` | `id` | Uuid | no | health |
| `event_note` | `event_id` | Uuid | no | health |
| `event_note` | `artifact_id` | Uuid | no | health |
| `event_note` | `kind` | Enum | no | health |
| `event_note` | `private` | Boolean | no | consent |
| `event_note` | `label` | String | yes | health |
| `event_note` | `transcript_key` | String | yes | health |
| `event_note` | `transcript_sha256` | String | yes | health |
| `event_note` | `transcript_confidence` | Float | yes | operational |
| `event_note` | `transcript_language` | String | yes | operational |
| `event_note` | `written_by_person_id` | Uuid | no | identifier |
| `event_note` | `written_at` | DateTime | no | health |
| `event_note` | `profile_id` | Uuid | no | identifier |
| `fact` | `id` | Uuid | no | health |
| `fact` | `subject` | String | no | health |
| `fact` | `attribute` | String | no | health |
| `fact` | `value` | JSON | no | health |
| `fact` | `unit` | String | yes | health |
| `fact` | `confidence` | Float | no | operational |
| `fact` | `confidence_state` | Enum | no | operational |
| `fact` | `artifact_id` | Uuid | yes | health |
| `fact` | `event_id` | Uuid | yes | health |
| `fact` | `episode_id` | Uuid | yes | health |
| `fact` | `valid_from` | DateTime | no | health |
| `fact` | `valid_to` | DateTime | yes | health |
| `fact` | `asserted_at` | DateTime | no | operational |
| `fact` | `supersedes_id` | Uuid | yes | health |
| `fact` | `superseded_at` | DateTime | yes | operational |
| `fact` | `confirmed_by_person_id` | Uuid | yes | identifier |
| `fact` | `profile_id` | Uuid | no | identifier |
| `key` | `id` | Uuid | no | consent |
| `key` | `holder_person_id` | Uuid | no | identifier |
| `key` | `role` | Enum | no | consent |
| `key` | `scopes` | JSON | no | consent |
| `key` | `consent_id` | Uuid | yes | consent |
| `key` | `granted_by_person_id` | Uuid | no | identifier |
| `key` | `granted_at` | DateTime | no | consent |
| `key` | `expires_at` | DateTime | yes | consent |
| `key` | `revoked_at` | DateTime | yes | consent |
| `key` | `profile_id` | Uuid | no | identifier |
| `profile_settings` | `id` | Uuid | no | health |
| `profile_settings` | `conditions` | JSON | no | health |
| `profile_settings` | `language` | String | no | operational |
| `profile_settings` | `density` | Enum | no | health |
| `profile_settings` | `large_text` | Boolean | no | health |
| `profile_settings` | `high_contrast` | Boolean | no | health |
| `profile_settings` | `voice_on` | Boolean | no | health |
| `profile_settings` | `big_targets` | Boolean | no | health |
| `profile_settings` | `one_thing_per_screen` | Boolean | no | health |
| `profile_settings` | `read_back` | Boolean | no | health |
| `profile_settings` | `repeat_prompts` | Boolean | no | health |
| `profile_settings` | `preferred_name` | String | yes | identifier |
| `profile_settings` | `doctor_name` | String | yes | health |
| `profile_settings` | `breakfast_time` | String | yes | health |
| `profile_settings` | `checkin_time` | String | yes | health |
| `profile_settings` | `birth_decade` | Integer | yes | identifier |
| `profile_settings` | `event_id` | Uuid | no | health |
| `profile_settings` | `set_by_person_id` | Uuid | no | identifier |
| `profile_settings` | `set_at` | DateTime | no | operational |
| `profile_settings` | `supersedes_id` | Uuid | yes | health |
| `profile_settings` | `superseded_at` | DateTime | yes | operational |
| `profile_settings` | `profile_id` | Uuid | no | identifier |
| `red_flag` | `id` | Uuid | no | health |
| `red_flag` | `kind` | Enum | no | health |
| `red_flag` | `code` | String | no | health |
| `red_flag` | `subject` | String | no | health |
| `red_flag` | `feeling` | Enum | yes | health |
| `red_flag` | `event_id` | Uuid | yes | health |
| `red_flag` | `artifact_id` | Uuid | yes | health |
| `red_flag` | `appointment_id` | Uuid | yes | health |
| `red_flag` | `fact_ids` | JSON | no | health |
| `red_flag` | `payload` | JSON | no | health |
| `red_flag` | `raised_by_person_id` | Uuid | no | identifier |
| `red_flag` | `raised_at` | DateTime | no | health |
| `red_flag` | `told` | JSON | no | identifier |
| `red_flag` | `suppressed_because` | String | yes | health |
| `red_flag` | `ambiguous_profile` | Boolean | no | health |
| `red_flag` | `resolved_at` | DateTime | yes | operational |
| `red_flag` | `profile_id` | Uuid | no | identifier |
| `appointment_proposal` | `id` | Uuid | no | health |
| `appointment_proposal` | `connector_id` | Uuid | no | consent |
| `appointment_proposal` | `event_digest` | String | no | operational |
| `appointment_proposal` | `title` | String | no | health |
| `appointment_proposal` | `location` | String | yes | health |
| `appointment_proposal` | `starts_at` | DateTime | no | health |
| `appointment_proposal` | `all_day` | Boolean | no | health |
| `appointment_proposal` | `matched_by` | Enum | no | operational |
| `appointment_proposal` | `keyword` | String | yes | health |
| `appointment_proposal` | `provider_id` | Uuid | yes | health |
| `appointment_proposal` | `provider_name` | String | no | health |
| `appointment_proposal` | `provider_kind` | Enum | no | health |
| `appointment_proposal` | `status` | Enum | no | health |
| `appointment_proposal` | `found_at` | DateTime | no | operational |
| `appointment_proposal` | `decided_at` | DateTime | yes | operational |
| `appointment_proposal` | `decided_by_person_id` | Uuid | yes | identifier |
| `appointment_proposal` | `appointment_id` | Uuid | yes | health |
| `appointment_proposal` | `profile_id` | Uuid | no | identifier |
| `audit_entry` | `id` | Uuid | no | audit |
| `audit_entry` | `at` | DateTime | no | audit |
| `audit_entry` | `actor_person_id` | Uuid | yes | identifier |
| `audit_entry` | `actor_role` | Enum | yes | audit |
| `audit_entry` | `key_id` | Uuid | yes | audit |
| `audit_entry` | `action` | Enum | no | audit |
| `audit_entry` | `scope` | Enum | no | audit |
| `audit_entry` | `channel` | Enum | no | audit |
| `audit_entry` | `target` | String | no | audit |
| `audit_entry` | `target_id` | Uuid | yes | audit |
| `audit_entry` | `rows` | Integer | no | audit |
| `audit_entry` | `outcome` | Enum | no | audit |
| `audit_entry` | `refused_because` | String | yes | audit |
| `audit_entry` | `shared_with_person_id` | Uuid | yes | identifier |
| `audit_entry` | `shared_with_label` | String | yes | identifier |
| `audit_entry` | `profile_id` | Uuid | no | identifier |
| `biography_line` | `id` | Uuid | no | health |
| `biography_line` | `session_id` | Uuid | no | health |
| `biography_line` | `position` | Integer | no | operational |
| `biography_line` | `fact_id` | Uuid | no | health |
| `biography_line` | `answer` | Enum | no | health |
| `biography_line` | `dispute_fact_id` | Uuid | yes | health |
| `biography_line` | `answered_by_person_id` | Uuid | no | identifier |
| `biography_line` | `answered_at` | DateTime | no | operational |
| `biography_line` | `profile_id` | Uuid | no | identifier |
| `consult_segment` | `id` | Uuid | no | health |
| `consult_segment` | `recording_id` | Uuid | no | health |
| `consult_segment` | `position` | Integer | no | operational |
| `consult_segment` | `speaker` | Enum | no | health |
| `consult_segment` | `start_s` | Float | no | health |
| `consult_segment` | `end_s` | Float | no | health |
| `consult_segment` | `char_start` | Integer | no | health |
| `consult_segment` | `char_end` | Integer | no | health |
| `consult_segment` | `profile_id` | Uuid | no | identifier |
| `medication_line` | `id` | Uuid | no | health |
| `medication_line` | `fact_id` | Uuid | no | health |
| `medication_line` | `generic` | String | no | health |
| `medication_line` | `brand` | String | yes | health |
| `medication_line` | `strength` | String | no | health |
| `medication_line` | `form` | String | no | health |
| `medication_line` | `registration_no` | String | yes | health |
| `medication_line` | `drug_class` | String | no | health |
| `medication_line` | `high_risk` | Boolean | no | health |
| `medication_line` | `dose` | JSON | no | health |
| `medication_line` | `prescriber` | String | yes | health |
| `medication_line` | `source_kind` | Enum | no | health |
| `medication_line` | `lead_time_days` | Integer | no | operational |
| `medication_line` | `reorder_threshold_days` | Integer | no | operational |
| `medication_line` | `source_artifact_id` | Uuid | yes | health |
| `medication_line` | `source_event_id` | Uuid | yes | health |
| `medication_line` | `confidence` | Float | no | operational |
| `medication_line` | `confidence_state` | Enum | no | operational |
| `medication_line` | `status` | Enum | no | health |
| `medication_line` | `change_kind` | Enum | no | health |
| `medication_line` | `started_at` | DateTime | no | health |
| `medication_line` | `stopped_at` | DateTime | yes | health |
| `medication_line` | `supersedes_id` | Uuid | yes | health |
| `medication_line` | `superseded_at` | DateTime | yes | operational |
| `medication_line` | `confirmed_by_person_id` | Uuid | no | identifier |
| `medication_line` | `asserted_at` | DateTime | no | operational |
| `medication_line` | `profile_id` | Uuid | no | identifier |
| `notice` | `id` | Uuid | no | health |
| `notice` | `kind` | Enum | no | health |
| `notice` | `to_person_id` | Uuid | no | identifier |
| `notice` | `template` | String | no | health |
| `notice` | `slots` | JSON | no | health |
| `notice` | `language` | String | no | operational |
| `notice` | `flag_id` | Uuid | yes | health |
| `notice` | `event_id` | Uuid | yes | health |
| `notice` | `created_at` | DateTime | no | operational |
| `notice` | `deliver_after` | DateTime | no | operational |
| `notice` | `delivered_at` | DateTime | yes | operational |
| `notice` | `profile_id` | Uuid | no | identifier |
| `plan_prompt` | `id` | Uuid | no | health |
| `plan_prompt` | `plan_id` | Uuid | no | health |
| `plan_prompt` | `day` | Integer | no | operational |
| `plan_prompt` | `gap` | String | no | health |
| `plan_prompt` | `due_at` | DateTime | no | operational |
| `plan_prompt` | `status` | Enum | no | operational |
| `plan_prompt` | `deferred` | Integer | no | operational |
| `plan_prompt` | `done_at` | DateTime | yes | operational |
| `plan_prompt` | `done_by_fact_id` | Uuid | yes | health |
| `plan_prompt` | `skipped_at` | DateTime | yes | operational |
| `plan_prompt` | `skipped_by_person_id` | Uuid | yes | identifier |
| `plan_prompt` | `profile_id` | Uuid | no | identifier |
| `review_field` | `id` | Uuid | no | health |
| `review_field` | `card_id` | Uuid | no | health |
| `review_field` | `position` | Integer | no | operational |
| `review_field` | `subject` | String | no | health |
| `review_field` | `attribute` | String | no | health |
| `review_field` | `value` | JSON | no | health |
| `review_field` | `unit` | String | yes | health |
| `review_field` | `confidence` | Float | no | operational |
| `review_field` | `span` | JSON | yes | operational |
| `review_field` | `state` | Enum | no | health |
| `review_field` | `corrected_value` | JSON | yes | health |
| `review_field` | `corrected_by_person_id` | Uuid | yes | identifier |
| `review_field` | `fact_id` | Uuid | yes | health |
| `review_field` | `decided_at` | DateTime | yes | operational |
| `review_field` | `profile_id` | Uuid | no | identifier |
| `safety_escalation` | `id` | Uuid | no | health |
| `safety_escalation` | `flag_id` | Uuid | no | health |
| `safety_escalation` | `roster` | JSON | no | identifier |
| `safety_escalation` | `told` | JSON | no | identifier |
| `safety_escalation` | `created_at` | DateTime | no | health |
| `safety_escalation` | `profile_id` | Uuid | no | identifier |
| `state_snapshot` | `id` | Uuid | no | health |
| `state_snapshot` | `sequence` | Integer | no | operational |
| `state_snapshot` | `computed_at` | DateTime | no | operational |
| `state_snapshot` | `posture` | Enum | no | health |
| `state_snapshot` | `trigger` | Enum | no | health |
| `state_snapshot` | `trigger_fact_id` | Uuid | yes | health |
| `state_snapshot` | `supersedes_id` | Uuid | yes | health |
| `state_snapshot` | `clinical` | JSON | no | health |
| `state_snapshot` | `functional` | JSON | no | health |
| `state_snapshot` | `cognitive` | JSON | no | health |
| `state_snapshot` | `situational` | JSON | no | health |
| `state_snapshot` | `preference` | JSON | no | health |
| `state_snapshot` | `family` | JSON | no | identifier |
| `state_snapshot` | `computed_from` | JSON | no | health |
| `state_snapshot` | `stale_after` | DateTime | yes | operational |
| `state_snapshot` | `profile_id` | Uuid | no | identifier |
| `stewardship` | `id` | Uuid | no | consent |
| `stewardship` | `steward_person_id` | Uuid | no | identifier |
| `stewardship` | `key_id` | Uuid | no | consent |
| `stewardship` | `consent_id` | Uuid | no | consent |
| `stewardship` | `basis` | Enum | no | consent |
| `stewardship` | `relationship` | String | yes | identifier |
| `stewardship` | `opened_at` | DateTime | no | operational |
| `stewardship` | `closed_at` | DateTime | yes | operational |
| `stewardship` | `claimed_by_person_id` | Uuid | yes | identifier |
| `stewardship` | `profile_id` | Uuid | no | identifier |
| `whatsapp_opt_in` | `id` | Uuid | no | operational |
| `whatsapp_opt_in` | `person_id` | Uuid | no | identifier |
| `whatsapp_opt_in` | `key_id` | Uuid | yes | operational |
| `whatsapp_opt_in` | `said_yes` | Boolean | no | consent |
| `whatsapp_opt_in` | `joins_group` | Boolean | no | consent |
| `whatsapp_opt_in` | `wording_version` | String | no | consent |
| `whatsapp_opt_in` | `language` | String | no | operational |
| `whatsapp_opt_in` | `said_at` | DateTime | no | consent |
| `whatsapp_opt_in` | `profile_id` | Uuid | no | identifier |
| `brief` | `id` | Uuid | no | health |
| `brief` | `appointment_id` | Uuid | no | health |
| `brief` | `language` | String | no | operational |
| `brief` | `since_state_id` | Uuid | yes | health |
| `brief` | `lines` | JSON | no | health |
| `brief` | `sources` | JSON | no | health |
| `brief` | `built_at` | DateTime | no | operational |
| `brief` | `state_id` | Uuid | no | health |
| `brief` | `boundary` | Text | yes | health |
| `brief` | `profile_id` | Uuid | no | identifier |
| `delivery_ladder` | `id` | Uuid | no | health |
| `delivery_ladder` | `subject` | Enum | no | health |
| `delivery_ladder` | `scope` | Enum | no | operational |
| `delivery_ladder` | `dedupe_key` | String | no | health |
| `delivery_ladder` | `day` | String | no | operational |
| `delivery_ladder` | `line_id` | Uuid | yes | health |
| `delivery_ladder` | `anchor` | String | yes | health |
| `delivery_ladder` | `flag_id` | Uuid | yes | health |
| `delivery_ladder` | `note_id` | Uuid | yes | health |
| `delivery_ladder` | `note_from_person_id` | Uuid | yes | identifier |
| `delivery_ladder` | `rungs` | JSON | no | identifier |
| `delivery_ladder` | `started_at` | DateTime | no | health |
| `delivery_ladder` | `next_rung` | Integer | no | operational |
| `delivery_ladder` | `acknowledged_at` | DateTime | yes | health |
| `delivery_ladder` | `acknowledged_by_person_id` | Uuid | yes | identifier |
| `delivery_ladder` | `closed_at` | DateTime | yes | operational |
| `delivery_ladder` | `closed_because` | String | yes | health |
| `delivery_ladder` | `profile_id` | Uuid | no | identifier |
| `dose_taken` | `id` | Uuid | no | health |
| `dose_taken` | `line_id` | Uuid | no | health |
| `dose_taken` | `event_id` | Uuid | no | health |
| `dose_taken` | `anchor` | String | yes | health |
| `dose_taken` | `amount` | Float | no | health |
| `dose_taken` | `taken_at` | DateTime | no | health |
| `dose_taken` | `by_person_id` | Uuid | no | identifier |
| `dose_taken` | `profile_id` | Uuid | no | identifier |
| `emergency_card` | `id` | Uuid | no | health |
| `emergency_card` | `format` | Enum | no | operational |
| `emergency_card` | `language` | String | no | operational |
| `emergency_card` | `fact_ids` | JSON | no | health |
| `emergency_card` | `line_ids` | JSON | no | health |
| `emergency_card` | `rendered_at` | DateTime | no | operational |
| `emergency_card` | `rendered_for_person_id` | Uuid | no | identifier |
| `emergency_card` | `state_id` | Uuid | no | health |
| `emergency_card` | `boundary` | Text | yes | health |
| `emergency_card` | `profile_id` | Uuid | no | identifier |
| `feed_item` | `id` | Uuid | no | health |
| `feed_item` | `type` | Enum | no | health |
| `feed_item` | `supply` | Enum | no | operational |
| `feed_item` | `caps_class` | Enum | no | operational |
| `feed_item` | `deliver_to` | Enum | no | operational |
| `feed_item` | `scope` | Enum | no | operational |
| `feed_item` | `language` | String | no | operational |
| `feed_item` | `format` | Enum | no | operational |
| `feed_item` | `headline` | String | no | health |
| `feed_item` | `body` | JSON | no | health |
| `feed_item` | `voice` | JSON | no | health |
| `feed_item` | `why` | JSON | no | health |
| `feed_item` | `priority` | Integer | no | operational |
| `feed_item` | `autoplay` | Boolean | no | operational |
| `feed_item` | `source_id` | Uuid | yes | operational |
| `feed_item` | `cite` | JSON | yes | health |
| `feed_item` | `search_job_id` | Uuid | yes | health |
| `feed_item` | `day` | String | no | operational |
| `feed_item` | `dedupe_key` | String | no | health |
| `feed_item` | `created_at` | DateTime | no | operational |
| `feed_item` | `expires_at` | DateTime | no | operational |
| `feed_item` | `number` | String | yes | health |
| `feed_item` | `direction` | String | yes | health |
| `feed_item` | `colour` | String | yes | health |
| `feed_item` | `action` | String | yes | operational |
| `feed_item` | `state_id` | Uuid | no | health |
| `feed_item` | `boundary` | Text | yes | health |
| `feed_item` | `profile_id` | Uuid | no | identifier |
| `feeling_tap` | `id` | Uuid | no | health |
| `feeling_tap` | `event_id` | Uuid | no | health |
| `feeling_tap` | `word` | Enum | no | health |
| `feeling_tap` | `red` | Boolean | no | health |
| `feeling_tap` | `flag_id` | Uuid | yes | health |
| `feeling_tap` | `follow_up` | Enum | yes | health |
| `feeling_tap` | `answer` | Enum | yes | health |
| `feeling_tap` | `answered_at` | DateTime | yes | health |
| `feeling_tap` | `emphasised` | Boolean | no | health |
| `feeling_tap` | `reasons` | JSON | no | health |
| `feeling_tap` | `cloud_state_id` | Uuid | yes | health |
| `feeling_tap` | `by_person_id` | Uuid | no | identifier |
| `feeling_tap` | `tapped_at` | DateTime | no | health |
| `feeling_tap` | `profile_id` | Uuid | no | identifier |
| `interaction_flag` | `id` | Uuid | no | health |
| `interaction_flag` | `line_id` | Uuid | no | health |
| `interaction_flag` | `other_line_id` | Uuid | no | health |
| `interaction_flag` | `severity` | Enum | no | health |
| `interaction_flag` | `text_id` | String | no | health |
| `interaction_flag` | `flagged_at` | DateTime | no | operational |
| `interaction_flag` | `profile_id` | Uuid | no | identifier |
| `medication_supply` | `id` | Uuid | no | health |
| `medication_supply` | `line_id` | Uuid | no | health |
| `medication_supply` | `fact_id` | Uuid | no | health |
| `medication_supply` | `quantity` | Integer | no | health |
| `medication_supply` | `dispensed_at` | DateTime | no | health |
| `medication_supply` | `artifact_id` | Uuid | yes | health |
| `medication_supply` | `confirmed_by_person_id` | Uuid | no | identifier |
| `medication_supply` | `recorded_at` | DateTime | no | operational |
| `medication_supply` | `profile_id` | Uuid | no | identifier |
| `memo` | `id` | Uuid | no | health |
| `memo` | `appointment_id` | Uuid | yes | health |
| `memo` | `kind` | Enum | no | health |
| `memo` | `source` | Enum | no | health |
| `memo` | `source_id` | Uuid | yes | health |
| `memo` | `key` | String | no | health |
| `memo` | `slots` | JSON | no | health |
| `memo` | `text` | String | no | health |
| `memo` | `language` | String | no | operational |
| `memo` | `supersedes_id` | Uuid | yes | health |
| `memo` | `superseded_at` | DateTime | yes | operational |
| `memo` | `created_at` | DateTime | no | operational |
| `memo` | `state_id` | Uuid | no | health |
| `memo` | `boundary` | Text | yes | health |
| `memo` | `profile_id` | Uuid | no | identifier |
| `nudge` | `id` | Uuid | no | health |
| `nudge` | `kind` | Enum | no | health |
| `nudge` | `scope` | Enum | no | operational |
| `nudge` | `day` | String | no | operational |
| `nudge` | `language` | String | no | operational |
| `nudge` | `lines` | JSON | no | health |
| `nudge` | `voice` | JSON | no | health |
| `nudge` | `why` | String | no | health |
| `nudge` | `reason` | JSON | no | health |
| `nudge` | `cap_class` | Enum | no | operational |
| `nudge` | `priority` | Integer | no | operational |
| `nudge` | `send_after` | DateTime | no | operational |
| `nudge` | `expires_at` | DateTime | no | operational |
| `nudge` | `dedupe_key` | String | no | health |
| `nudge` | `memo_id` | Uuid | yes | health |
| `nudge` | `handed_over_at` | DateTime | no | operational |
| `nudge` | `handed_over_by_person_id` | Uuid | no | identifier |
| `nudge` | `state_id` | Uuid | no | health |
| `nudge` | `boundary` | Text | yes | health |
| `nudge` | `profile_id` | Uuid | no | identifier |
| `question` | `id` | Uuid | no | health |
| `question` | `appointment_id` | Uuid | no | health |
| `question` | `language` | String | no | operational |
| `question` | `source` | Enum | no | health |
| `question` | `source_kind` | String | yes | health |
| `question` | `source_ids` | JSON | no | health |
| `question` | `key` | String | no | health |
| `question` | `slots` | JSON | no | health |
| `question` | `text` | String | no | health |
| `question` | `priority` | Integer | no | operational |
| `question` | `added_by_person_id` | Uuid | yes | identifier |
| `question` | `removed` | Boolean | no | operational |
| `question` | `supersedes_id` | Uuid | yes | health |
| `question` | `superseded_at` | DateTime | yes | operational |
| `question` | `created_at` | DateTime | no | operational |
| `question` | `state_id` | Uuid | no | health |
| `question` | `boundary` | Text | yes | health |
| `question` | `profile_id` | Uuid | no | identifier |
| `scheduled_push` | `id` | Uuid | no | health |
| `scheduled_push` | `composed_by_person_id` | Uuid | no | identifier |
| `scheduled_push` | `composed_at` | DateTime | no | operational |
| `scheduled_push` | `language` | String | no | operational |
| `scheduled_push` | `template_id` | String | yes | operational |
| `scheduled_push` | `lines` | JSON | no | health |
| `scheduled_push` | `send_at` | DateTime | no | operational |
| `scheduled_push` | `channel` | Enum | no | operational |
| `scheduled_push` | `expires_at` | DateTime | no | operational |
| `scheduled_push` | `state_id` | Uuid | no | health |
| `scheduled_push` | `boundary` | Text | yes | health |
| `scheduled_push` | `profile_id` | Uuid | no | identifier |
| `task` | `id` | Uuid | no | health |
| `task` | `what` | String | no | health |
| `task` | `assigned_person_id` | Uuid | no | identifier |
| `task` | `due_at` | DateTime | yes | operational |
| `task` | `created_by_person_id` | Uuid | no | identifier |
| `task` | `created_at` | DateTime | no | operational |
| `task` | `done_at` | DateTime | yes | operational |
| `task` | `done_by_person_id` | Uuid | yes | identifier |
| `task` | `appointment_id` | Uuid | yes | health |
| `task` | `errand` | Enum | yes | health |
| `task` | `medication_line_id` | Uuid | yes | health |
| `task` | `opened_on` | Date | yes | operational |
| `task` | `profile_id` | Uuid | no | identifier |
| `trend_card` | `id` | Uuid | no | health |
| `trend_card` | `analyte` | String | no | health |
| `trend_card` | `language` | String | no | operational |
| `trend_card` | `fact_ids` | JSON | no | health |
| `trend_card` | `direction` | Enum | no | health |
| `trend_card` | `lines` | JSON | no | health |
| `trend_card` | `rendered_for_person_id` | Uuid | no | identifier |
| `trend_card` | `rendered_at` | DateTime | no | operational |
| `trend_card` | `state_id` | Uuid | no | health |
| `trend_card` | `boundary` | Text | yes | health |
| `trend_card` | `profile_id` | Uuid | no | identifier |
| `visit_summary` | `id` | Uuid | no | health |
| `visit_summary` | `appointment_id` | Uuid | no | health |
| `visit_summary` | `artifact_id` | Uuid | no | health |
| `visit_summary` | `language` | String | no | operational |
| `visit_summary` | `red_flag` | Boolean | no | health |
| `visit_summary` | `lines` | JSON | no | health |
| `visit_summary` | `created_at` | DateTime | no | operational |
| `visit_summary` | `confirmed_at` | DateTime | yes | operational |
| `visit_summary` | `confirmed_by_person_id` | Uuid | yes | identifier |
| `visit_summary` | `recording_artifact_id` | Uuid | yes | health |
| `visit_summary` | `state_id` | Uuid | no | health |
| `visit_summary` | `boundary` | Text | yes | health |
| `visit_summary` | `profile_id` | Uuid | no | identifier |
| `what_to_do_card` | `id` | Uuid | no | health |
| `what_to_do_card` | `kind` | Enum | no | health |
| `what_to_do_card` | `language` | String | no | operational |
| `what_to_do_card` | `line_ids` | JSON | no | health |
| `what_to_do_card` | `flag_id` | Uuid | yes | health |
| `what_to_do_card` | `event_id` | Uuid | no | health |
| `what_to_do_card` | `check_in_at` | DateTime | yes | health |
| `what_to_do_card` | `rendered_at` | DateTime | no | operational |
| `what_to_do_card` | `rendered_for_person_id` | Uuid | no | identifier |
| `what_to_do_card` | `state_id` | Uuid | no | health |
| `what_to_do_card` | `boundary` | Text | yes | health |
| `what_to_do_card` | `profile_id` | Uuid | no | identifier |
| `whatsapp_message` | `id` | Uuid | no | health |
| `whatsapp_message` | `thread_id` | Uuid | no | health |
| `whatsapp_message` | `direction` | Enum | no | operational |
| `whatsapp_message` | `kind` | Enum | no | health |
| `whatsapp_message` | `person_id` | Uuid | no | identifier |
| `whatsapp_message` | `at` | DateTime | no | operational |
| `whatsapp_message` | `provider_message_id` | String | yes | operational |
| `whatsapp_message` | `artifact_id` | Uuid | yes | health |
| `whatsapp_message` | `flag_id` | Uuid | yes | health |
| `whatsapp_message` | `template_name` | String | yes | operational |
| `whatsapp_message` | `catalogue_key` | String | yes | health |
| `whatsapp_message` | `state_id` | Uuid | yes | health |
| `whatsapp_message` | `profile_id` | Uuid | no | identifier |
| `biography_question` | `id` | Uuid | no | health |
| `biography_question` | `session_id` | Uuid | no | health |
| `biography_question` | `gap` | String | no | health |
| `biography_question` | `kept` | Boolean | no | health |
| `biography_question` | `decided_by_person_id` | Uuid | no | identifier |
| `biography_question` | `decided_at` | DateTime | no | operational |
| `biography_question` | `question_id` | Uuid | yes | health |
| `biography_question` | `handed_over_at` | DateTime | yes | operational |
| `biography_question` | `profile_id` | Uuid | no | identifier |
| `delivery` | `id` | Uuid | no | health |
| `delivery` | `trigger_kind` | Enum | no | operational |
| `delivery` | `trigger_type` | Enum | no | health |
| `delivery` | `category` | Enum | no | operational |
| `delivery` | `scope` | Enum | no | operational |
| `delivery` | `rule` | String | no | health |
| `delivery` | `dedupe_key` | String | no | health |
| `delivery` | `why` | JSON | no | health |
| `delivery` | `to_person_id` | Uuid | yes | identifier |
| `delivery` | `for_person_id` | Uuid | yes | identifier |
| `delivery` | `standing` | String | yes | identifier |
| `delivery` | `rung` | Integer | yes | operational |
| `delivery` | `ladder_id` | Uuid | yes | health |
| `delivery` | `channel` | Enum | yes | operational |
| `delivery` | `template_name` | String | yes | operational |
| `delivery` | `outcome` | Enum | no | operational |
| `delivery` | `reason` | String | yes | operational |
| `delivery` | `passed_over` | JSON | no | operational |
| `delivery` | `message_id` | Uuid | yes | health |
| `delivery` | `day` | String | no | operational |
| `delivery` | `due_at` | DateTime | no | operational |
| `delivery` | `recorded_at` | DateTime | no | operational |
| `delivery` | `profile_id` | Uuid | no | identifier |
| `feed_engagement` | `id` | Uuid | no | health |
| `feed_engagement` | `item_id` | Uuid | no | health |
| `feed_engagement` | `person_id` | Uuid | no | identifier |
| `feed_engagement` | `kind` | Enum | no | operational |
| `feed_engagement` | `channel` | Enum | no | operational |
| `feed_engagement` | `event_id` | Uuid | no | health |
| `feed_engagement` | `at` | DateTime | no | operational |
| `feed_engagement` | `profile_id` | Uuid | no | identifier |
| `feeling_note` | `id` | Uuid | no | health |
| `feeling_note` | `tap_id` | Uuid | no | health |
| `feeling_note` | `word` | Enum | no | health |
| `feeling_note` | `answer` | Enum | no | health |
| `feeling_note` | `language` | String | no | operational |
| `feeling_note` | `headline` | String | no | health |
| `feeling_note` | `lines` | JSON | no | health |
| `feeling_note` | `then` | String | no | health |
| `feeling_note` | `voice` | JSON | no | health |
| `feeling_note` | `reasons` | JSON | no | health |
| `feeling_note` | `outcome` | Enum | no | health |
| `feeling_note` | `appointment_id` | Uuid | yes | health |
| `feeling_note` | `created_at` | DateTime | no | operational |
| `feeling_note` | `state_id` | Uuid | no | health |
| `feeling_note` | `boundary` | Text | yes | health |
| `feeling_note` | `profile_id` | Uuid | no | identifier |
| `nudge_response` | `id` | Uuid | no | health |
| `nudge_response` | `nudge_id` | Uuid | no | health |
| `nudge_response` | `person_id` | Uuid | no | identifier |
| `nudge_response` | `kind` | Enum | no | operational |
| `nudge_response` | `event_id` | Uuid | no | health |
| `nudge_response` | `at` | DateTime | no | operational |
| `nudge_response` | `profile_id` | Uuid | no | identifier |
| `summary_item` | `id` | Uuid | no | health |
| `summary_item` | `summary_id` | Uuid | no | health |
| `summary_item` | `position` | Integer | no | operational |
| `summary_item` | `kind` | Enum | no | health |
| `summary_item` | `payload` | JSON | no | health |
| `summary_item` | `span` | JSON | yes | health |
| `summary_item` | `confidence` | Float | no | health |
| `summary_item` | `key` | String | no | health |
| `summary_item` | `text` | String | no | health |
| `summary_item` | `state` | Enum | no | consent |
| `summary_item` | `decided_at` | DateTime | yes | operational |
| `summary_item` | `memo_id` | Uuid | yes | health |
| `summary_item` | `appointment_id` | Uuid | yes | health |
| `summary_item` | `fact_id` | Uuid | yes | health |
| `summary_item` | `flag_id` | Uuid | yes | health |
| `summary_item` | `clip_start_s` | Float | yes | health |
| `summary_item` | `clip_end_s` | Float | yes | health |
| `summary_item` | `profile_id` | Uuid | no | identifier |
| `thread_message` | `id` | Uuid | no | health |
| `thread_message` | `author_person_id` | Uuid | no | identifier |
| `thread_message` | `posted_at` | DateTime | no | operational |
| `thread_message` | `text` | String | yes | health |
| `thread_message` | `state_id` | Uuid | yes | health |
| `thread_message` | `card_kind` | Enum | yes | health |
| `thread_message` | `task_id` | Uuid | yes | health |
| `thread_message` | `profile_id` | Uuid | no | identifier |
| `whatsapp_proposal` | `id` | Uuid | no | health |
| `whatsapp_proposal` | `thread_id` | Uuid | no | health |
| `whatsapp_proposal` | `message_id` | Uuid | no | health |
| `whatsapp_proposal` | `poster_person_id` | Uuid | no | identifier |
| `whatsapp_proposal` | `subject` | String | no | health |
| `whatsapp_proposal` | `attribute` | String | no | health |
| `whatsapp_proposal` | `value` | JSON | no | health |
| `whatsapp_proposal` | `unit` | String | yes | health |
| `whatsapp_proposal` | `event_kind` | Enum | no | health |
| `whatsapp_proposal` | `occurred_at` | DateTime | no | health |
| `whatsapp_proposal` | `said` | String | no | health |
| `whatsapp_proposal` | `created_at` | DateTime | no | operational |
| `whatsapp_proposal` | `expires_at` | DateTime | no | operational |
| `whatsapp_proposal` | `status` | Enum | no | operational |
| `whatsapp_proposal` | `answered_at` | DateTime | yes | operational |
| `whatsapp_proposal` | `fact_id` | Uuid | yes | health |
| `whatsapp_proposal` | `event_id` | Uuid | yes | health |
| `whatsapp_proposal` | `profile_id` | Uuid | no | identifier |
| `thread_photo` | `id` | Uuid | no | health |
| `thread_photo` | `message_id` | Uuid | no | health |
| `thread_photo` | `artifact_id` | Uuid | no | health |
| `thread_photo` | `author_person_id` | Uuid | no | identifier |
| `thread_photo` | `on_his_feed` | Boolean | no | consent |
| `thread_photo` | `posted_at` | DateTime | no | operational |
| `thread_photo` | `withdrawn_at` | DateTime | yes | consent |
| `thread_photo` | `profile_id` | Uuid | no | identifier |
<!-- data-map:end -->


## 3. Lawful basis per purpose

Health data is sensitive personal data in both countries and is processed on **explicit consent**, given in words the person read, in his language, versioned and kept on the row (`app/consent/texts.py`, `app/consent/service.py`). There is no research purpose and no marketing purpose: nothing trains on user data, nothing is studied from it, and no analytics vendor receives health data (`CLAUDE.md`).

| Purpose (`ConsentPurpose`) | What it covers | Who gives it | Where it is recorded | How it stops |
|---|---|---|---|---|
| `hold_health_record` | Nura keeping the person's papers, medicines and readings, in his country | The owner at the moment he opens or claims his graph; or a steward on a declared basis until the claim (E01) | `consent` row at claim; `stewardship.consent_id` while stewarded | `revoke_consent`: nothing new is kept from that day; what is held stays until erasure (§4) |
| `share_with_family` (one named person at a time) | Letting one named person see named parts of the record | The owner, naming the person and the parts | `consent` row naming `holder_person_id` and `scopes`; every `key` cut under it names `consent_id` | Withdrawing it closes that person's keys and nobody else's (`tests/test_consent_acceptance.py:330`) |
| `recording` | Listening to a visit and keeping what is said | The owner, or the chief on a recorded basis | `consent` row; the recording is a `voice` artefact; see `recording-consent.md` | `revoke_consent`; no recording starts without it in force (`may_record`) |
| `whatsapp` | Sending the Today page to the person's WhatsApp each morning | The owner | `consent` row | `revoke_consent`; the WhatsApp service (E19) asks the gate before every send |

**Proxy bases.** Someone other than the owner may agree for him only on a declared basis with something behind it: a lasting power of attorney or a doctor's letter as an artefact on the profile, or his own spoken agreement with the witness named and the recording kept (`ConsentBasis`; `tests/test_consent.py`). Which basis is acceptable when the patient cannot consent and there is no LPA is an open question in `docs/product-reset.md` §10 and question 3 for counsel below.

**Accounts.** Registration data (phone number or email, display name, language) is processed to provide the service the person asked for — the sign-in itself. No password is ever held; codes and tokens are stored hashed (`login_challenge.code_hash`, `session.token_hash`).

**Providers.** A doctor's or clinic's name, number and address on a profile is the patient's own directory entry (`provider`), never linked across profiles. Whether it is the provider's personal data in either Act is question 5 for counsel.

## 4. Retention and deletion

**What the code does today.**

- **Facts are never edited.** A wrong fact is superseded by a new one that points at it; the old row stays, marked with when (`app/db.py: frozen`; `tests/test_memory.py:236`). This is the record's integrity, and it is also why "delete one fact" is not a thing the app can do — deletion is of the graph.
- **Consent outlives the graph.** The `consent` table is the one profile-scoped table whose foreign key is `ondelete="RESTRICT"` rather than `CASCADE` (`app/consent/models.py`). Deleting a profile row while consents point at it is refused by the database (`tests/test_consent_acceptance.py:760`). This is deliberate: the proof of what was agreed and when it was withdrawn must survive the erasure it authorised. The erasure path therefore exports the consents and archives them first, then deletes the graph.
- **Withdrawing `hold_health_record`** means what its words say: "After that day, Nura keeps nothing new. The papers Nura already has stay in your record." It is a stop on collection, not an erasure.
- **Sign-in rows** expire: a code is one use and ten minutes; a session is thirty days or until logged out. Expired rows are not yet swept.

**Built (#143): closing an account.** The erasure path now exists (`app/identity/closing.py`; the wording and the 30-day window await counsel in `account-closure.md`):
- A closing suspends every key at once, withdraws `hold_health_record`, revokes every push subscription and stops deliveries, except a red flag raised before it.
- After `NURA_ACCOUNT_RETENTION_DAYS`, the erasure job archives the consent rows in an `erasure_record` outside the graph, together with the one line that says the graph was erased, by whom and when.
- It then deletes every profile-scoped row, including the audit trail, and every stored object under the profile's prefixes, and leaves the account.

Step (1) below, sending the person his consent record and audit trail, is still the DPO's, by hand.

**What is still a follow-up.** The erasure path (export and deletion, T2 in `docs/00-MASTER-BUILD-SPEC.md` §3) must: (1) export the consent record and the audit trail to the person; (2) archive the consent rows outside the graph; (3) delete every profile-scoped row (the `CASCADE` does this) and the artefact bytes in the object store by storage key; (4) leave the account unless the person also asks for it to go; (5) write one final audit line to the archive saying the graph was erased, by whom, when. Until it ships, an erasure request is handled by the DPO by hand against this list, and the fact that it was is recorded. Retention periods for each classification — how long an audit trail or an archived consent is kept after erasure, how long a recording is kept once its summary is read — are question 4 for counsel and are not set in code.

## 5. Cross-border

**Pinned.** A person, a profile and every row on it carry a region; artefact bytes carry it too (`artifact.region`), and the service checks the bytes' region against the profile's (`tests/test_ingestion.py:288`). A Singapore deployment serves Singapore profiles and refuses the rest, even if a row is sitting in its database (`tests/test_memory_review.py:242`).

**What never leaves the region.** Health data and identifiers: every row classified health or identifier above, and every artefact byte. No analytics vendor receives health data; no model is trained on it.

**What does leave, and what it carries.** These are the third parties a deployment talks to, and what crosses to each. Every one is an adapter behind a port, so a regional endpoint can be chosen without changing a caller.

| Leaves to | What crosses | Region control |
|---|---|---|
| SMS / WhatsApp provider (login codes; the Today page; helper list) | The phone number, and the message text — which for the Today page is health data in the patient's language | Provider chosen per region (`docs/00-MASTER-BUILD-SPEC.md` §8); templates approved per number; messages are health data and are treated as such |
| Speech and model providers (transcription, the sentence the model writes) | Recording audio; the words of a memo | Region-pinned endpoints; no retention and no training on inputs, by contract; the port is `app/llm/` and `app/channels/whatsapp/provider.py` when they land. The recording notice does not name these providers (`recording-consent.md` §3; question 8 for counsel there) |
| Licensed drug data | Generic names and strengths, never the profile | No identifier is sent; a lookup is not a person |
| Object store | Artefact bytes | One bucket per region, in the region (`LocalObjectStore` today; the cloud store is the same port) |
| Apple / Google push | A device token and a nudge; no health content in a notification payload | Payloads are written to say nothing a lock screen should not |

**Across the causeway.** A provider on a Malaysian profile may be in Singapore (`provider.region`): the row stays with the profile. A recording made in a clinic in the other country stays in the profile's region (see `recording-consent.md` §6, question 7).

## 6. The breach process

A breach is any unauthorised access to, disclosure of, loss of, or alteration of personal data Nura holds — including a key used outside its scope that the keys module did not stop, a lost device with an open session, a misdirected WhatsApp message, an object store made readable, or a provider incident. The audit trail is the first instrument: every read is on it, so "who saw what" is a query, not an investigation.

**Roles.** Incident lead (the on-call engineer, who declares and runs the incident), the DPO (assessment, regulator and individual notification, the record), the owner (decisions that touch families), counsel (the notification call in each country).

| Step | What | Who | Window |
|---|---|---|---|
| **Detect** | Anything that could be a breach is declared as an incident at once — a monitoring alert, a family's report, a provider's notice, an audit-trail anomaly. Over-declare; downgrade later. | anyone → incident lead | immediately |
| **Contain** | Stop the exposure: revoke the sessions or keys involved (`revoke_key`, `LoginSession.revoked_at`), rotate the credential, close the bucket, pause the channel. Preserve the audit trail and logs; do not clean up before they are copied. | incident lead | first hour |
| **Assess** | Which profiles, which classifications (identifier, health, consent, audit), how many people, what harm could follow. Read from the audit trail and the object store's access log. Write the assessment down, with the time each fact was learned. | DPO + incident lead | Singapore: the assessment is to be completed within **30 days** of becoming aware (PDPA 2012, Part VIA, s 26C — to be verified); Malaysia: as soon as practicable (see notify) |
| **Notify the regulator** | Singapore: where the breach is likely to result in significant harm to an individual, or is of significant scale (**500 or more individuals**), notify the PDPC within **3 calendar days** of assessing that it is notifiable (s 26D — to be verified by counsel). Malaysia: under the Personal Data Protection (Amendment) Act 2024 (new s 12B), notify the Commissioner as soon as practicable; the Commissioner's guideline names **72 hours** (to be verified by counsel, including commencement). Health data is sensitive in both, so the significant-harm test is assumed met for any health-classified exposure. | DPO, with counsel | as stated |
| **Notify the people** | Where significant harm is likely: each affected owner, in his language, in plain words, saying what was seen, by whom if known, what Nura did, and what he can do; a key holder is told only about the profile he holds a key to. Singapore: on or after notifying the PDPC, as soon as practicable (s 26D(2) — to be verified). Malaysia: without unnecessary delay; the guideline names **7 days** where significant harm is likely (to be verified). | DPO; the owner reviews the words | as stated |
| **Record** | The incident file: timeline, assessment, decisions, notifications sent, what changed afterwards. Kept whether or not the breach was notifiable, since the decision not to notify has to be defensible. | DPO | closed within 30 days |
| **Fix** | The change that stops the class of breach, with a test where one can be written; a note in `docs/progress/`. | engineering | before the incident is closed |

**Notification content.** Both regulators expect: what happened and when; the categories and approximate number of individuals and records; the likely consequences; what has been done and what will be done; the DPO's contact. Templates for the PDPC form and the Malaysian Commissioner's notice are counsel's to supply and are kept with the incident file.

**Testing the runbook.** The acceptance line asks for the runbook to be tested. The code paths it relies on have tests today: a revoked or expired key closes its reach (`tests/test_keys.py:43`, `:55`; `tests/test_accounts_acceptance.py`), the audit trail records every read and every refusal (`tests/test_audit_acceptance.py`), out-of-region reads are refused (`tests/test_memory_review.py:217`). The human part is a tabletop: two people, one hour, one scenario from the list above (a lost phone with an open session is the first), walked against this table with the clock running, and the gaps written down. The first tabletop is owed before the first family uses Nura with real health information (the TestFlight row in `docs/checkpoints.md`; checkpoint 19's demo holds none, ADR 0008) and recorded here:

| Date | Scenario | Who | Gaps found | Fixed by |
|---|---|---|---|---|
| | | | | |

## 7. The data protection officer

Both Acts want a named person. Singapore's PDPA requires an organisation to designate one or more individuals responsible for compliance and to make their business contact information available (s 11(3)–(5) — to be verified). Malaysia's 2024 amendment requires the appointment of a data protection officer where processing meets the Commissioner's thresholds (new s 12A and the DPO guideline — thresholds and commencement to be verified).

| | |
|---|---|
| Role | Data protection officer for Nura, both regions, until the two deployments need one each |
| Named | *to be named by the owner before the first family on real health information (the TestFlight row)* |
| Contact | *dpo@ (domain to be set) — published in the app's Settings → Privacy, on the listing, and in the printed emergency card's footer* |
| Duties | Owns this document and `recording-consent.md`; runs the assessment and notification steps in §6; answers data subject requests in §8 within the windows; keeps the consent texts' versions and translations reviewed; reviews every PR that touches `app/consent/`, `app/audit/`, `app/keys/` or `app/safety/` (the protected paths in `.github/CODEOWNERS`) |
| Reports to | The owner |

## 8. Data subject requests

| Request | What the person gets | How, today | Window (to be verified) |
|---|---|---|---|
| **Access** — "what do you hold about me and who has seen it" | The consent record (every agreement, in the words read, and when withdrawn) and the audit trail (every reach, by whom, when, allowed or refused) — the two things the Acts most care about. The graph itself he already holds: it is his app. A file export of the graph is the portability item below. | `export_consent_record` (`app/consent/export.py`) and `GET /profiles/{id}/audit`; the DPO sends the rendered page | Singapore: as soon as reasonably possible, within 30 days or a written estimate (s 21 and reg — to be verified); Malaysia: 21 days (s 31 — to be verified) |
| **Correction** — "that number is wrong" | A wrong fact is disputed or superseded; the old row stays with the new one pointing at it, so the record shows both what was read and what he said. Never an edit in place. | The review card's correct, and `supersede_fact` / a dispute (`tests/test_memory_review.py:560`) | Singapore s 22; Malaysia s 34 — to be verified |
| **Withdrawal** — "stop" | Any consent, any time, in the app or by WhatsApp; the words say what stops. Refusals and withdrawals are visible on the trail. | `revoke_consent` at the service; a key is revoked over HTTP (`DELETE /profiles/{id}/keys/{key_id}`); the withdraw route for a consent is owed with the consent screen (E00-02 follow-up) | immediate |
| **Portability** — "give me my record to take elsewhere" | A structured export of the graph: facts with provenance, artefacts, medicines, appointments, consents, trail. | **Follow-up** (T2 export). Until then the DPO assembles it by hand from the region's database and object store under the owner's context, and the export is an audit `SHARE` line. Singapore's Part VIB (data portability obligation) commencement — to be verified. | as agreed with the person |
| **Erasure** — "delete everything" | The graph and its bytes gone; the consent record and the trail archived, as §4 describes; the account gone if he asks. | **Follow-up** (T2 deletion). Until then by hand against §4's list, recorded. | Singapore: retention limitation (s 25) and the cessation obligation; Malaysia: s 10 — to be verified |
| **A key holder's request** | A daughter asking what is held about her: her account row and her keys and the consents naming her; nothing of the patient's graph. | `export_consent_record` addressed to her; the audit lines where she is the actor | as above |

The person asks in the app, by WhatsApp, or by writing to the DPO. Identity is the signed-in session or the phone number the profile was set up against; the DPO does not act on a request from any other channel without a call back to that number.

## 9. Questions for counsel

1. **Breach windows.** Confirm the Singapore windows (30 days to assess; 3 calendar days to notify the PDPC once notifiable; individuals as soon as practicable) and the Malaysian ones (72 hours to the Commissioner; 7 days to individuals), the sections they rest on, and whether the 2024 Malaysian amendments and their guidelines are in force at our launch date.
2. **Significant harm.** Is any exposure of health-classified data presumed to meet the significant-harm test in each country, as this document assumes, or is a case-by-case assessment required?
3. **Proxy consent.** Which bases are acceptable for a steward to agree to `hold_health_record` for a patient who cannot consent and has no LPA — a doctor's letter, a witnessed spoken agreement, a next of kin's declaration — and what must be behind each (`docs/product-reset.md` §10)?
4. **Retention.** How long may — and must — the audit trail and the archived consent record be kept after a graph is erased; how long may a recording be kept once its summary and memo exist; whether expired sign-in rows must be swept on a schedule.
5. **Providers as data subjects.** Is a doctor's name, number and address on a patient's own directory the doctor's personal data under either Act, and does the doctor have access or correction rights against Nura?
6. **Key holders.** A family member's account and keys: is Nura the controller of her data, and does she have the same request rights as the patient over what names her?
7. **DPO.** Whether one officer may serve both deployments; what must be published where; whether the Malaysian thresholds for a mandatory DPO are met at pilot scale.
8. **WhatsApp as a channel.** Sending health data in the patient's language through a Business Solution Provider — what does each Act require of the transfer, and is the provider a data intermediary or a processor with duties of its own under the 2024 Malaysian amendments?
9. **Portability.** Whether Singapore's data portability obligation is in force and applies; whether Malaysia's 2024 amendment's portability right (new s 43A) applies to a graph held for a consumer.
10. **Region pinning.** Whether a Singapore resident's profile pinned to Singapore, whose daughter reads it from Kuala Lumpur through her key, is a transfer of the patient's data out of Singapore (s 26 — to be verified), and what the transfer-limitation obligation then requires of the daughter's reads.
