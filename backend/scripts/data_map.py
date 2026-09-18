"""The data inventory for docs/trust/pdpa-data-map.md, generated from the models (E16-05).

    python3 -m scripts.data_map            # print the table
    python3 -m scripts.data_map --check    # exit 1 if the document's table is out of date

Every table on `app.db.Base.metadata` and every column of it, with the classification the
PDPA data map needs — identifier, health, consent, audit, operational — from `CLASSES` below.
The walk is the code's; the classification is a person's, written here once per column, and
the script refuses to run with a column nobody has classified, so a new column cannot reach
the data map unlabelled. Test-only tables (`test_*`, from tests/support.py) are left out.

The generated block sits between `<!-- data-map:begin -->` and `<!-- data-map:end -->` in the
document; `tests/test_data_map.py` runs `--check` so the document cannot drift from the models.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Table, TypeDecorator
from sqlalchemy.types import TypeEngine

# Every module that declares a table, so the metadata is whole.
import app.models_all  # noqa: F401 — every table, from the one registry
from app.db import Base

DOCUMENT = Path(__file__).resolve().parents[2] / "docs" / "trust" / "pdpa-data-map.md"
BEGIN = "<!-- data-map:begin -->"
END = "<!-- data-map:end -->"

IDENTIFIER = "identifier"
HEALTH = "health"
CONSENT = "consent"
AUDIT = "audit"
OPERATIONAL = "operational"
CLASSIFICATIONS = (IDENTIFIER, HEALTH, CONSENT, AUDIT, OPERATIONAL)

# The classification of every column, by "table.column"; "*.column" is a default for a column
# name found on many tables. The rule is the document's (docs/trust/pdpa-data-map.md §2):
# anything that points at a person is an identifier; anything that says something about
# his health, or is a reference to a row that does — a fact id, a supersession, a card's
# subject, what triggered State, the kind of source a line came from — is health.
# `profile_id` on every profile-scoped table is the link from a row to the person it is
# about: an identifier wherever it appears.
CLASSES: dict[str, str] = {
    "*.profile_id": IDENTIFIER,
    "*.region": OPERATIONAL,
    # The write-order tiebreaker (#192/#218, `app.db.monotonic`): a row's position, not
    # anything about a person or his health.
    "*.seq": OPERATIONAL,
    "seq_counters.name": OPERATIONAL,
    "seq_counters.value": OPERATIONAL,
    # A row's own id is classified as the row: the id of a fact is a reference to health
    # data, the id of a person is an identifier, the id of a consent is the consent record.
    # Only a sign-in row's id points at nothing about a person.
    "person.id": IDENTIFIER,
    "profile.id": IDENTIFIER,
    "stewardship.id": CONSENT,
    "login_challenge.id": OPERATIONAL,
    "session.id": OPERATIONAL,
    "key.id": CONSENT,
    "consent.id": CONSENT,
    "confirmation.id": CONSENT,
    "audit_entry.id": AUDIT,
    "artifact.id": HEALTH,
    "event.id": HEALTH,
    "fact.id": HEALTH,
    "episode.id": HEALTH,
    "provider.id": HEALTH,
    "appointment.id": HEALTH,
    "state_snapshot.id": HEALTH,
    "review_card.id": HEALTH,
    "review_field.id": HEALTH,
    "medication_line.id": HEALTH,
    "medication_supply.id": HEALTH,
    "dose_taken.id": HEALTH,
    "interaction_flag.id": HEALTH,
    "note.id": HEALTH,
    "search_job.id": HEALTH,
    "feed_item.id": HEALTH,
    "feed_engagement.id": HEALTH,
    "red_flag.id": HEALTH,
    "safety_escalation.id": HEALTH,
    "whatsapp_thread.id": HEALTH,
    "whatsapp_message.id": HEALTH,
    "whatsapp_proposal.id": HEALTH,
    "source.id": OPERATIONAL,
    "feed_page.id": OPERATIONAL,
    "thread_message.id": HEALTH,
    "thread_photo.id": HEALTH,
    "whatsapp_group.id": HEALTH,
    "task.id": HEALTH,
    "scheduled_push.id": HEALTH,
    "document.id": HEALTH,
    "roster_slot.id": IDENTIFIER,
    # A call with a family member (design-direction.md, Connect's "Upcoming Call"): who and
    # when, like the roster slot it sits beside — not health content of its own.
    "scheduled_call.id": IDENTIFIER,
    "privacy.id": CONSENT,
    "trend_card.id": HEALTH,
    "routine.id": HEALTH,
    "connector.id": CONSENT,
    "appointment_proposal.id": HEALTH,
    # --- accounts and the graph's ownership -------------------------------------------------
    "person.display_name": IDENTIFIER,
    "person.language": OPERATIONAL,
    "person.phone_e164": IDENTIFIER,
    "person.email": IDENTIFIER,
    "person.created_at": OPERATIONAL,
    "person.named_by_person_id": IDENTIFIER,
    "profile.display_name": IDENTIFIER,
    "profile.language": OPERATIONAL,
    "profile.owner_person_id": IDENTIFIER,
    "profile.patient_phone_e164": IDENTIFIER,
    "profile.created_at": OPERATIONAL,
    # Where he lives, coarsely (a district or a postcode's first digits): it points at a
    # person, so it is an identifier, however coarse (F1, E09-07).
    "profile.area": IDENTIFIER,
    "stewardship.steward_person_id": IDENTIFIER,
    "stewardship.key_id": CONSENT,
    "stewardship.consent_id": CONSENT,
    "stewardship.basis": CONSENT,
    "stewardship.relationship": IDENTIFIER,
    "stewardship.opened_at": OPERATIONAL,
    "stewardship.closed_at": OPERATIONAL,
    "stewardship.claimed_by_person_id": IDENTIFIER,
    # --- signing in ---------------------------------------------------------------------------
    "login_challenge.channel": OPERATIONAL,
    "login_challenge.phone_e164": IDENTIFIER,
    "login_challenge.email": IDENTIFIER,
    "login_challenge.code_hash": OPERATIONAL,
    "login_challenge.display_name": IDENTIFIER,
    "login_challenge.language": OPERATIONAL,
    "login_challenge.issued_at": OPERATIONAL,
    "login_challenge.expires_at": OPERATIONAL,
    "login_challenge.attempts": OPERATIONAL,
    "login_challenge.consumed_at": OPERATIONAL,
    "login_challenge.person_id": IDENTIFIER,
    "session.person_id": IDENTIFIER,
    "session.token_hash": OPERATIONAL,
    "session.created_at": OPERATIONAL,
    "session.expires_at": OPERATIONAL,
    "session.revoked_at": OPERATIONAL,
    # --- keys, consent, confirmations, audit --------------------------------------------------
    "key.holder_person_id": IDENTIFIER,
    "key.role": CONSENT,
    "key.scopes": CONSENT,
    "key.consent_id": CONSENT,
    "key.granted_by_person_id": IDENTIFIER,
    "key.granted_at": CONSENT,
    "key.expires_at": CONSENT,
    "key.revoked_at": CONSENT,
    "consent.person_id": IDENTIFIER,
    "consent.purpose": CONSENT,
    "consent.holder_person_id": IDENTIFIER,
    "consent.scopes": CONSENT,
    "consent.role": CONSENT,
    "consent.window": CONSENT,
    "consent.text_version": CONSENT,
    "consent.language": CONSENT,
    "consent.wording_text": CONSENT,
    "consent.captured_via": CONSENT,
    "consent.basis": CONSENT,
    "consent.basis_artifact_id": CONSENT,
    "consent.witness_person_id": IDENTIFIER,
    "consent.granted_at": CONSENT,
    "consent.revoked_at": CONSENT,
    "consent.revoked_by_person_id": IDENTIFIER,
    "confirmation.person_id": IDENTIFIER,
    "confirmation.subject": HEALTH,
    "confirmation.subject_id": HEALTH,
    "confirmation.content_digest": OPERATIONAL,
    "confirmation.created_at": OPERATIONAL,
    "confirmation.expires_at": OPERATIONAL,
    "confirmation.consumed_at": OPERATIONAL,
    "confirmation.channel": OPERATIONAL,
    "audit_entry.at": AUDIT,
    "audit_entry.actor_person_id": IDENTIFIER,
    "audit_entry.actor_role": AUDIT,
    "audit_entry.key_id": AUDIT,
    "audit_entry.action": AUDIT,
    "audit_entry.scope": AUDIT,
    "audit_entry.channel": AUDIT,
    "audit_entry.target": AUDIT,
    "audit_entry.target_id": AUDIT,
    "audit_entry.rows": AUDIT,
    "audit_entry.outcome": AUDIT,
    "audit_entry.refused_because": AUDIT,
    "audit_entry.shared_with_person_id": IDENTIFIER,
    "audit_entry.shared_with_label": IDENTIFIER,
    # --- the health graph: memory ---------------------------------------------------------------
    "artifact.kind": HEALTH,
    "artifact.storage_key": HEALTH,
    "artifact.content_type": HEALTH,
    "artifact.sha256": OPERATIONAL,
    "artifact.captured_at": HEALTH,
    "artifact.source_channel": OPERATIONAL,
    "artifact.stored_at": OPERATIONAL,
    "event.kind": HEALTH,
    "event.occurred_at": HEALTH,
    "event.source_channel": OPERATIONAL,
    "event.label": HEALTH,
    "event.artifact_id": HEALTH,
    "event.episode_id": HEALTH,
    "event.recorded_at": OPERATIONAL,
    # The scope a row was written under decides who may read it, the way a note's `private`
    # does: a permission on the row, classified with the consent record it enforces.
    "artifact.written_scope": CONSENT,
    "event.written_scope": CONSENT,
    "fact.subject": HEALTH,
    "fact.attribute": HEALTH,
    "fact.value": HEALTH,
    "fact.unit": HEALTH,
    "fact.confidence": OPERATIONAL,
    "fact.confidence_state": OPERATIONAL,
    "fact.artifact_id": HEALTH,
    "fact.event_id": HEALTH,
    "fact.episode_id": HEALTH,
    "fact.valid_from": HEALTH,
    "fact.valid_to": HEALTH,
    "fact.asserted_at": OPERATIONAL,
    "fact.supersedes_id": HEALTH,
    "fact.superseded_at": OPERATIONAL,
    "fact.confirmed_by_person_id": IDENTIFIER,
    "episode.kind": HEALTH,
    "episode.label": HEALTH,
    "episode.opened_at": HEALTH,
    "episode.closed_at": HEALTH,
    "provider.name": HEALTH,
    "provider.kind": HEALTH,
    "provider.phone_e164": HEALTH,
    "provider.address": HEALTH,
    "provider.added_at": OPERATIONAL,
    # Whether a hospital is on his insurance says something about his cover and where he is
    # treated (E19-05): health, like the provider itself. A doctor's hours are the doctor's.
    "provider.panel": HEALTH,
    "provider.opens_at": OPERATIONAL,
    "provider.closes_at": OPERATIONAL,
    # Which of the board's four home-care tiles this provider is listed under — a second
    # grouping beside `kind`, null for every provider outside that grid: still health data,
    # the same reasoning as `provider.kind`.
    "provider.category": HEALTH,
    "appointment.provider_id": HEALTH,
    "appointment.scheduled_at": HEALTH,
    "appointment.status": HEALTH,
    "appointment.purpose": HEALTH,
    "appointment.episode_id": HEALTH,
    "appointment.confirmed_by_person_id": IDENTIFIER,
    "appointment.status_changed_by_person_id": IDENTIFIER,
    "appointment.booked_at": OPERATIONAL,
    # The timeline (E03): a paper hung off a visit or an episode is a reference to health
    # data; a chief's note about a clinic is about a provider he uses; a look is the reader's
    # own act, and the spine it saw is visit ids and statuses.
    "attachment.id": HEALTH,
    "attachment.artifact_id": HEALTH,
    "attachment.episode_id": HEALTH,
    "attachment.appointment_id": HEALTH,
    "attachment.how": OPERATIONAL,
    "attachment.attached_by_person_id": IDENTIFIER,
    "attachment.attached_at": OPERATIONAL,
    "provider_note.id": HEALTH,
    "provider_note.provider_id": HEALTH,
    "provider_note.text": HEALTH,
    "provider_note.written_by_person_id": IDENTIFIER,
    "provider_note.written_at": OPERATIONAL,
    "last_looked.id": OPERATIONAL,
    "last_looked.person_id": IDENTIFIER,
    "last_looked.looked_at": OPERATIONAL,
    "last_looked.appointments": HEALTH,
    # --- State --------------------------------------------------------------------------------
    "state_snapshot.sequence": OPERATIONAL,
    "state_snapshot.computed_at": OPERATIONAL,
    "state_snapshot.posture": HEALTH,
    "state_snapshot.trigger": HEALTH,
    "state_snapshot.trigger_fact_id": HEALTH,
    "state_snapshot.supersedes_id": HEALTH,
    "state_snapshot.clinical": HEALTH,
    "state_snapshot.functional": HEALTH,
    "state_snapshot.cognitive": HEALTH,
    "state_snapshot.situational": HEALTH,
    "state_snapshot.preference": HEALTH,
    "state_snapshot.family": IDENTIFIER,
    "state_snapshot.computed_from": HEALTH,
    "state_snapshot.stale_after": OPERATIONAL,
    # --- ingestion: review cards ----------------------------------------------------------------
    "review_card.artifact_id": HEALTH,
    "review_card.document_kind": HEALTH,
    "review_card.document_date": HEALTH,
    "review_card.high_risk_class": HEALTH,
    "review_card.created_at": OPERATIONAL,
    "review_card.confirmed_at": OPERATIONAL,
    "review_card.confirmed_by_person_id": IDENTIFIER,
    "review_field.card_id": HEALTH,
    "review_field.position": OPERATIONAL,
    "review_field.subject": HEALTH,
    "review_field.attribute": HEALTH,
    "review_field.value": HEALTH,
    "review_field.unit": HEALTH,
    "review_field.confidence": OPERATIONAL,
    "review_field.span": OPERATIONAL,
    "review_field.state": HEALTH,
    "review_field.corrected_value": HEALTH,
    "review_field.fact_id": HEALTH,
    "review_field.decided_at": OPERATIONAL,
    # --- medicines ----------------------------------------------------------------------------
    "medication_line.fact_id": HEALTH,
    "medication_line.generic": HEALTH,
    "medication_line.brand": HEALTH,
    "medication_line.strength": HEALTH,
    "medication_line.form": HEALTH,
    "medication_line.registration_no": HEALTH,
    "medication_line.drug_class": HEALTH,
    "medication_line.high_risk": HEALTH,
    # Whether a product is a prescription medicine, a supplement or a TCM remedy (E04-03) is a
    # fact about the person's health — what he takes — not an operational detail.
    "medication_line.product_kind": HEALTH,
    # The Health Analyst's own question about a line, "is this something to ask about the
    # way a supplement is" (migration 0049): still what he takes, the same standing as
    # `product_kind` above.
    "medication_line.category": HEALTH,
    "medication_line.dose": HEALTH,
    "medication_line.prescriber": HEALTH,
    "medication_line.source_kind": HEALTH,
    "medication_line.lead_time_days": OPERATIONAL,
    "medication_line.reorder_threshold_days": OPERATIONAL,
    "medication_line.source_artifact_id": HEALTH,
    "medication_line.source_event_id": HEALTH,
    "medication_line.confidence": OPERATIONAL,
    "medication_line.confidence_state": OPERATIONAL,
    # How sure the registry was of its own match (#206): a score, the same standing as the
    # fact's own confidence above.
    "medication_line.registry_confidence": OPERATIONAL,
    "medication_line.status": HEALTH,
    "medication_line.change_kind": HEALTH,
    "medication_line.started_at": HEALTH,
    "medication_line.stopped_at": HEALTH,
    "medication_line.supersedes_id": HEALTH,
    "medication_line.superseded_at": OPERATIONAL,
    "medication_line.confirmed_by_person_id": IDENTIFIER,
    "medication_line.asserted_at": OPERATIONAL,
    "medication_supply.line_id": HEALTH,
    "medication_supply.fact_id": HEALTH,
    "medication_supply.quantity": HEALTH,
    "medication_supply.dispensed_at": HEALTH,
    "medication_supply.artifact_id": HEALTH,
    "medication_supply.confirmed_by_person_id": IDENTIFIER,
    "medication_supply.recorded_at": OPERATIONAL,
    "dose_taken.line_id": HEALTH,
    "dose_taken.event_id": HEALTH,
    "dose_taken.anchor": HEALTH,
    "dose_taken.amount": HEALTH,
    "dose_taken.taken_at": HEALTH,
    # Whether the reply landed after the dose's window had closed (#198) is a fact about his
    # day, the same standing as taken_at and anchor above — not an operational detail of how
    # the tap was processed.
    "dose_taken.late": HEALTH,
    "dose_taken.by_person_id": IDENTIFIER,
    "interaction_flag.line_id": HEALTH,
    "interaction_flag.other_line_id": HEALTH,
    "interaction_flag.severity": HEALTH,
    "interaction_flag.text_id": HEALTH,
    # What a pharmacist would check the pair against (E04-03): the clinical basis for a flag
    # on this person's medicines, same standing as severity and text_id.
    "interaction_flag.source": HEALTH,
    # Whether a pharmacist has reviewed the pair yet: review workflow state, not itself a
    # fact about the person's health — the same standing as confidence_state below.
    "interaction_flag.awaiting_review": OPERATIONAL,
    "interaction_flag.flagged_at": OPERATIONAL,
    # --- notes --------------------------------------------------------------------------------
    "note.text": HEALTH,
    "note.written_at": HEALTH,
    # --- the feed (E21) -----------------------------------------------------------------------
    # The allowlist is global and says nothing about anyone: operational throughout.
    "source.name": OPERATIONAL,
    "source.domain": OPERATIONAL,
    "source.kind": OPERATIONAL,
    "source.regions": OPERATIONAL,
    "source.languages": OPERATIONAL,
    "source.allowlisted": OPERATIONAL,
    "source.review_status": OPERATIONAL,
    "source.added_at": OPERATIONAL,
    # A self-search is about his medicines: its terms, its reason and what it found are health.
    "search_job.kind": OPERATIONAL,
    "search_job.terms": HEALTH,
    "search_job.source_ids": OPERATIONAL,
    "search_job.cadence": OPERATIONAL,
    "search_job.reason": HEALTH,
    "search_job.status": OPERATIONAL,
    "search_job.results": HEALTH,
    "search_job.enabled": OPERATIONAL,
    "search_job.created_by_person_id": IDENTIFIER,
    "search_job.created_at": OPERATIONAL,
    "search_job.last_run_at": OPERATIONAL,
    # A card is what was shown to him about his record: its words, its reason, the State and
    # the page it came from, and the boundary line it was shown under (E16-01) are health.
    "feed_item.state_id": HEALTH,
    "feed_item.boundary": HEALTH,
    "feed_item.type": HEALTH,
    "feed_item.supply": OPERATIONAL,
    "feed_item.caps_class": OPERATIONAL,
    "feed_item.deliver_to": OPERATIONAL,
    "feed_item.scope": OPERATIONAL,
    "feed_item.language": OPERATIONAL,
    "feed_item.format": OPERATIONAL,
    "feed_item.headline": HEALTH,
    "feed_item.body": HEALTH,
    "feed_item.voice": HEALTH,
    "feed_item.why": HEALTH,
    "feed_item.priority": OPERATIONAL,
    "feed_item.autoplay": OPERATIONAL,
    "feed_item.source_id": OPERATIONAL,
    "feed_item.cite": HEALTH,
    "feed_item.search_job_id": HEALTH,
    "feed_item.day": OPERATIONAL,
    "feed_item.dedupe_key": HEALTH,
    "feed_item.created_at": OPERATIONAL,
    "feed_item.expires_at": OPERATIONAL,
    # The card grammar (E11-03): the one number is his reading; the colour is State's wash.
    "feed_item.number": HEALTH,
    "feed_item.direction": HEALTH,
    "feed_item.colour": HEALTH,
    "feed_item.action": OPERATIONAL,
    "feed_item.private_to": IDENTIFIER,
    # --- delivery (E11): the settings, every attempt to reach someone, the ladder -------------
    "delivery_settings.id": OPERATIONAL,
    "delivery_settings.skip_quiet_days": OPERATIONAL,
    "delivery_settings.quiet_from": OPERATIONAL,
    "delivery_settings.quiet_until": OPERATIONAL,
    "delivery_settings.channels": OPERATIONAL,
    "delivery_settings.caps": OPERATIONAL,
    "delivery_settings.set_by_person_id": IDENTIFIER,
    "delivery_settings.set_at": OPERATIONAL,
    "delivery.id": HEALTH,
    "delivery.trigger_kind": OPERATIONAL,
    "delivery.trigger_type": HEALTH,
    "delivery.category": OPERATIONAL,
    "delivery.scope": OPERATIONAL,
    "delivery.rule": HEALTH,
    "delivery.dedupe_key": HEALTH,
    "delivery.why": HEALTH,
    "delivery.to_person_id": IDENTIFIER,
    "delivery.for_person_id": IDENTIFIER,
    "delivery.standing": IDENTIFIER,
    "delivery.rung": OPERATIONAL,
    "delivery.ladder_id": HEALTH,
    "delivery.channel": OPERATIONAL,
    "delivery.template_name": OPERATIONAL,
    "delivery.outcome": OPERATIONAL,
    "delivery.reason": OPERATIONAL,
    "delivery.passed_over": OPERATIONAL,
    "delivery.message_id": HEALTH,
    "delivery.day": OPERATIONAL,
    "delivery.due_at": OPERATIONAL,
    "delivery.recorded_at": OPERATIONAL,
    # --- closing an account (#143): the closing, and the record that outlives the graph ----
    "account_closure.id": OPERATIONAL,
    "account_closure.requested_by_person_id": IDENTIFIER,
    "account_closure.requested_at": OPERATIONAL,
    "account_closure.delete_after": OPERATIONAL,
    "account_closure.undone_at": OPERATIONAL,
    "account_closure.undone_by_person_id": IDENTIFIER,
    "erasure_record.id": AUDIT,
    "erasure_record.region": OPERATIONAL,
    "erasure_record.requested_by_person_id": IDENTIFIER,
    "erasure_record.requested_at": AUDIT,
    "erasure_record.erased_at": AUDIT,
    "erasure_record.consents": CONSENT,
    "erasure_record.removed": AUDIT,
    "whatsapp_opt_in.id": OPERATIONAL,
    "whatsapp_opt_in.person_id": IDENTIFIER,
    "whatsapp_opt_in.said_yes": CONSENT,
    "whatsapp_opt_in.said_at": CONSENT,
    "whatsapp_opt_in.joins_group": CONSENT,
    "whatsapp_opt_in.wording_version": CONSENT,
    "whatsapp_opt_in.language": OPERATIONAL,
    "whatsapp_opt_in.key_id": OPERATIONAL,
    # --- web push (ADR 0001): the browsers a person asked to get reminders on ----------------
    "push_subscription.id": OPERATIONAL,
    "push_subscription.person_id": IDENTIFIER,
    "push_subscription.session_id": OPERATIONAL,
    "push_subscription.endpoint": IDENTIFIER,
    "push_subscription.p256dh": OPERATIONAL,
    "push_subscription.auth": OPERATIONAL,
    "push_subscription.created_at": OPERATIONAL,
    "push_subscription.revoked_at": OPERATIONAL,
    "push_subscription.gone_at": OPERATIONAL,
    "delivery_ladder.id": HEALTH,
    "delivery_ladder.subject": HEALTH,
    "delivery_ladder.scope": OPERATIONAL,
    "delivery_ladder.dedupe_key": HEALTH,
    "delivery_ladder.day": OPERATIONAL,
    "delivery_ladder.line_id": HEALTH,
    "delivery_ladder.anchor": HEALTH,
    "delivery_ladder.flag_id": HEALTH,
    "delivery_ladder.note_id": HEALTH,
    "delivery_ladder.note_from_person_id": IDENTIFIER,
    "delivery_ladder.rungs": IDENTIFIER,
    "delivery_ladder.started_at": HEALTH,
    "delivery_ladder.next_rung": OPERATIONAL,
    "delivery_ladder.acknowledged_at": HEALTH,
    "delivery_ladder.acknowledged_by_person_id": IDENTIFIER,
    "delivery_ladder.closed_at": OPERATIONAL,
    "delivery_ladder.closed_because": HEALTH,
    "feed_engagement.item_id": HEALTH,
    "feed_engagement.person_id": IDENTIFIER,
    "feed_engagement.kind": OPERATIONAL,
    "feed_engagement.channel": OPERATIONAL,
    "feed_engagement.event_id": HEALTH,
    "feed_engagement.at": OPERATIONAL,
    # How much of a clip or voice note about his health played: about his health.
    "feed_engagement.seconds": HEALTH,
    # The phone's own id for an event in its queue: says nothing about anyone.
    "feed_engagement.client_id": OPERATIONAL,
    # The offline page is a cache of card ids for one person.
    "feed_page.person_id": IDENTIFIER,
    "feed_page.audience": OPERATIONAL,
    "feed_page.item_ids": HEALTH,
    "feed_page.cursor": OPERATIONAL,
    "feed_page.next_cursor": OPERATIONAL,
    "feed_page.quiet": OPERATIONAL,
    "feed_page.held_by_caps": OPERATIONAL,
    "feed_page.rendered_at": OPERATIONAL,
    # A red flag is a symptom he said and who was told.
    "red_flag.feeling": HEALTH,
    "red_flag.event_id": HEALTH,
    "red_flag.raised_by_person_id": IDENTIFIER,
    "red_flag.raised_at": HEALTH,
    "red_flag.told": IDENTIFIER,
    "red_flag.suppressed_because": HEALTH,
    "red_flag.ambiguous_profile": HEALTH,
    # E05: the columns a flag heard at a visit needs — what it is and what it rests on is
    # health; when a person closed it is operational — and the visit loop's tables. The brief,
    # a question, a memo and a summary are his health said back to him; a person named on one
    # (who added a question, who confirmed a summary) is an identifier; the yes or no on a
    # summary item is his decision on what was heard, like a confirmation.
    "red_flag.kind": HEALTH,
    "red_flag.code": HEALTH,
    "red_flag.subject": HEALTH,
    "red_flag.fact_ids": HEALTH,
    "red_flag.payload": HEALTH,
    "red_flag.artifact_id": HEALTH,
    "red_flag.appointment_id": HEALTH,
    "red_flag.resolved_at": OPERATIONAL,
    "brief.id": HEALTH,
    "brief.state_id": HEALTH,
    "brief.boundary": HEALTH,
    "brief.appointment_id": HEALTH,
    "brief.language": OPERATIONAL,
    "brief.since_state_id": HEALTH,
    "brief.lines": HEALTH,
    "brief.sources": HEALTH,
    "brief.built_at": OPERATIONAL,
    "question.id": HEALTH,
    "question.state_id": HEALTH,
    "question.boundary": HEALTH,
    "question.appointment_id": HEALTH,
    "question.language": OPERATIONAL,
    "question.source": HEALTH,
    "question.source_kind": HEALTH,
    "question.source_ids": HEALTH,
    "question.key": HEALTH,
    "question.slots": HEALTH,
    "question.text": HEALTH,
    "question.priority": OPERATIONAL,
    "question.added_by_person_id": IDENTIFIER,
    "question.removed": OPERATIONAL,
    "question.supersedes_id": HEALTH,
    "question.superseded_at": OPERATIONAL,
    "question.created_at": OPERATIONAL,
    "question.written_scope": CONSENT,
    "memo.id": HEALTH,
    "memo.state_id": HEALTH,
    "memo.boundary": HEALTH,
    "memo.appointment_id": HEALTH,
    "memo.kind": HEALTH,
    "memo.source": HEALTH,
    "memo.source_id": HEALTH,
    "memo.key": HEALTH,
    "memo.slots": HEALTH,
    "memo.text": HEALTH,
    "memo.language": OPERATIONAL,
    "memo.supersedes_id": HEALTH,
    "memo.superseded_at": OPERATIONAL,
    "memo.created_at": OPERATIONAL,
    "visit_summary.id": HEALTH,
    "visit_summary.state_id": HEALTH,
    "visit_summary.boundary": HEALTH,
    "visit_summary.appointment_id": HEALTH,
    "visit_summary.artifact_id": HEALTH,
    "visit_summary.language": OPERATIONAL,
    "visit_summary.red_flag": HEALTH,
    "visit_summary.lines": HEALTH,
    "visit_summary.created_at": OPERATIONAL,
    "visit_summary.confirmed_at": OPERATIONAL,
    "visit_summary.confirmed_by_person_id": IDENTIFIER,
    "summary_item.id": HEALTH,
    "summary_item.summary_id": HEALTH,
    "summary_item.position": OPERATIONAL,
    "summary_item.kind": HEALTH,
    "summary_item.payload": HEALTH,
    "summary_item.span": HEALTH,
    "summary_item.confidence": HEALTH,
    "summary_item.key": HEALTH,
    "summary_item.text": HEALTH,
    "summary_item.state": CONSENT,
    "summary_item.decided_at": OPERATIONAL,
    "summary_item.memo_id": HEALTH,
    "summary_item.appointment_id": HEALTH,
    "summary_item.fact_id": HEALTH,
    "summary_item.flag_id": HEALTH,
    # Where in a consult recording an item was said, and the recording a card was heard from.
    "summary_item.clip_start_s": HEALTH,
    "summary_item.clip_end_s": HEALTH,
    "visit_summary.recording_artifact_id": HEALTH,
    # --- the consult recording (E02-05, E05-04) -------------------------------------------------
    # A recording of a visit and who spoke when in it: health. The consent it rested on is the
    # consent record; whether the doctor was named is part of the notice the pattern owes
    # (docs/trust/recording-consent.md), so it is classified with the consent too. The person
    # who pressed Start is an identifier. No row holds a word of what was said.
    "consult_recording.id": HEALTH,
    "consult_recording.appointment_id": HEALTH,
    "consult_recording.artifact_id": HEALTH,
    "consult_recording.transcript_artifact_id": HEALTH,
    "consult_recording.consent_id": CONSENT,
    "consult_recording.duration_s": HEALTH,
    "consult_recording.started_at": HEALTH,
    "consult_recording.notice_language": OPERATIONAL,
    "consult_recording.doctor_named": CONSENT,
    "consult_recording.heard_confidence": OPERATIONAL,
    "consult_recording.recorded_by_person_id": IDENTIFIER,
    "consult_recording.stored_at": OPERATIONAL,
    "consult_segment.id": HEALTH,
    "consult_segment.recording_id": HEALTH,
    "consult_segment.position": OPERATIONAL,
    "consult_segment.speaker": HEALTH,
    "consult_segment.start_s": HEALTH,
    "consult_segment.end_s": HEALTH,
    "consult_segment.char_start": HEALTH,
    "consult_segment.char_end": HEALTH,
    # A recording on its way in, in chunks (#129): which visit, the consent it was opened on,
    # who opened it, how far it came, the doctor's answer, and what became of it. The chunks
    # are bytes in the region's store; the row holds no words and no audio. The doctor's yes
    # and why an upload was thrown away (a no, the page left) are the room's consent.
    "consult_upload.id": HEALTH,
    "consult_upload.appointment_id": HEALTH,
    "consult_upload.consent_id": CONSENT,
    "consult_upload.started_by_person_id": IDENTIFIER,
    "consult_upload.content_type": OPERATIONAL,
    "consult_upload.started_at": HEALTH,
    "consult_upload.opened_at": HEALTH,
    "consult_upload.chunks": OPERATIONAL,
    "consult_upload.received_bytes": OPERATIONAL,
    "consult_upload.doctor_said_yes_at": CONSENT,
    "consult_upload.discarded_at": CONSENT,
    "consult_upload.discarded_because": CONSENT,
    "consult_upload.finished_at": HEALTH,
    "consult_upload.recording_id": HEALTH,
    # --- the family (E12) ---------------------------------------------------------------------
    # The thread and the tasks are about his care: their words and what they point at are
    # health. The roster says who looks after him and when: an identifier, like the family
    # dimension of State. "Only me" is his choice over who reads a part of his record: consent.
    "thread_message.author_person_id": IDENTIFIER,
    "thread_message.posted_at": OPERATIONAL,
    "thread_message.text": HEALTH,
    "thread_message.state_id": HEALTH,
    "thread_message.card_kind": HEALTH,
    "thread_message.task_id": HEALTH,
    # A photo the family shared: which message, which artefact, who shared it, and their own
    # yes to its being on his story cards — and taking it back — which is a consent.
    "thread_photo.message_id": HEALTH,
    "thread_photo.artifact_id": HEALTH,
    "thread_photo.author_person_id": IDENTIFIER,
    "thread_photo.on_his_feed": CONSENT,
    "thread_photo.posted_at": OPERATIONAL,
    "thread_photo.withdrawn_at": CONSENT,
    "task.what": HEALTH,
    "task.assigned_person_id": IDENTIFIER,
    "task.due_at": OPERATIONAL,
    "task.created_by_person_id": IDENTIFIER,
    "task.created_at": OPERATIONAL,
    "task.done_at": OPERATIONAL,
    "task.done_by_person_id": IDENTIFIER,
    # A drive to a visit (E05-03): which visit, and that it is the drive.
    "task.appointment_id": HEALTH,
    "task.errand": HEALTH,
    # An order for more of a medicine (E04-05): which of his medicine lines.
    "task.medication_line_id": HEALTH,
    # An order task's wall-clock day (E04-05; #166 review): timing metadata the once-a-day
    # rule keys on, no different from `created_at`.
    "task.opened_on": OPERATIONAL,
    "roster_slot.person_id": IDENTIFIER,
    "roster_slot.role": IDENTIFIER,
    "roster_slot.weekdays": OPERATIONAL,
    "roster_slot.starts_on": OPERATIONAL,
    "roster_slot.ends_on": OPERATIONAL,
    "roster_slot.from_time": OPERATIONAL,
    "roster_slot.to_time": OPERATIONAL,
    "roster_slot.added_by_person_id": IDENTIFIER,
    "roster_slot.added_at": OPERATIONAL,
    "roster_slot.ended_at": OPERATIONAL,
    "scheduled_call.with_person_id": IDENTIFIER,
    "scheduled_call.scheduled_at": OPERATIONAL,
    "scheduled_call.call_link": OPERATIONAL,
    "scheduled_call.label": OPERATIONAL,
    "scheduled_call.added_by_person_id": IDENTIFIER,
    "scheduled_call.added_at": OPERATIONAL,
    "scheduled_call.cancelled_at": OPERATIONAL,
    # A message a chief composed to him: her words, the State she composed against, and the
    # boundary column every rendered row has (empty here: her words infer nothing).
    "scheduled_push.composed_by_person_id": IDENTIFIER,
    "scheduled_push.composed_at": OPERATIONAL,
    "scheduled_push.language": OPERATIONAL,
    "scheduled_push.template_id": OPERATIONAL,
    "scheduled_push.lines": HEALTH,
    "scheduled_push.send_at": OPERATIONAL,
    "scheduled_push.channel": OPERATIONAL,
    "scheduled_push.expires_at": OPERATIONAL,
    "scheduled_push.state_id": HEALTH,
    "scheduled_push.boundary": HEALTH,
    # E13/E14 (ADR 0002). The notice to the family, the what-to-do card and the emergency
    # card: codes and ids, no prose, about his health. The flag is E21's `red_flag`, above.
    "notice.id": HEALTH,
    "notice.kind": HEALTH,
    "notice.to_person_id": IDENTIFIER,
    "notice.template": HEALTH,
    "notice.slots": HEALTH,
    "notice.language": OPERATIONAL,
    "notice.flag_id": HEALTH,
    "notice.event_id": HEALTH,
    "notice.created_at": OPERATIONAL,
    "notice.deliver_after": OPERATIONAL,
    "notice.delivered_at": OPERATIONAL,
    "what_to_do_card.id": HEALTH,
    "what_to_do_card.kind": HEALTH,
    "what_to_do_card.language": OPERATIONAL,
    "what_to_do_card.line_ids": HEALTH,
    "what_to_do_card.flag_id": HEALTH,
    "what_to_do_card.event_id": HEALTH,
    "what_to_do_card.check_in_at": HEALTH,
    "what_to_do_card.rendered_at": OPERATIONAL,
    "what_to_do_card.rendered_for_person_id": IDENTIFIER,
    "what_to_do_card.state_id": HEALTH,
    "what_to_do_card.boundary": HEALTH,
    # His insurer on the emergency card (E13-01), typed on a yes: the insurer's name and the
    # policy reference point at him at the insurer, so both are identifiers, and so is who
    # typed it; the yes is the consent record; when, operational.
    "insurer.id": IDENTIFIER,
    "insurer.name": IDENTIFIER,
    "insurer.policy_reference": IDENTIFIER,
    "insurer.set_by_person_id": IDENTIFIER,
    "insurer.confirmation_id": CONSENT,
    "insurer.set_at": OPERATIONAL,
    "emergency_card.id": HEALTH,
    "emergency_card.format": OPERATIONAL,
    "emergency_card.language": OPERATIONAL,
    "emergency_card.fact_ids": HEALTH,
    "emergency_card.line_ids": HEALTH,
    "emergency_card.rendered_at": OPERATIONAL,
    "emergency_card.rendered_for_person_id": IDENTIFIER,
    "emergency_card.state_id": HEALTH,
    "emergency_card.boundary": HEALTH,
    "document.artifact_id": HEALTH,
    "document.tag": HEALTH,
    "document.added_by_person_id": IDENTIFIER,
    "document.added_at": OPERATIONAL,
    "privacy.scope": CONSENT,
    "privacy.marked_by_person_id": IDENTIFIER,
    "privacy.marked_at": CONSENT,
    "privacy.lifted_at": CONSENT,
    "privacy.lifted_by_person_id": IDENTIFIER,
    # --- WhatsApp (E19) -----------------------------------------------------------------------
    # The rows are references, never the words: the words are a message artefact. What a row
    # points at — the artefact, the flag, the State, the fact a proposal became — and what kind
    # of message it was are health; who wrote or is on the ladder is an identifier; the
    # 24-hour window, the template and the provider's own message id are operational.
    "whatsapp_thread.person_id": IDENTIFIER,
    "whatsapp_thread.is_patient": IDENTIFIER,
    "whatsapp_thread.opened_at": OPERATIONAL,
    "whatsapp_thread.last_inbound_at": OPERATIONAL,
    "whatsapp_thread.last_outbound_at": OPERATIONAL,
    "whatsapp_message.thread_id": HEALTH,
    "whatsapp_message.direction": OPERATIONAL,
    "whatsapp_message.kind": HEALTH,
    "whatsapp_message.person_id": IDENTIFIER,
    "whatsapp_message.at": OPERATIONAL,
    "whatsapp_message.provider_message_id": OPERATIONAL,
    "whatsapp_message.artifact_id": HEALTH,
    "whatsapp_message.flag_id": HEALTH,
    "whatsapp_message.template_name": OPERATIONAL,
    "whatsapp_message.catalogue_key": HEALTH,
    "whatsapp_message.state_id": HEALTH,
    "whatsapp_message.asks_feeling": OPERATIONAL,
    # The family's WhatsApp group: the provider's handle names a group of people around him.
    "whatsapp_group.provider_group_id": IDENTIFIER,
    "whatsapp_group.opened_by_person_id": IDENTIFIER,
    "whatsapp_group.opened_at": OPERATIONAL,
    "whatsapp_group.members_digest": IDENTIFIER,
    # The webhook's receipt of one inbound message (#158): the provider's id and whether it was
    # handled, never the words and never whose it was — operational through and through.
    "whatsapp_receipt.id": OPERATIONAL,
    "whatsapp_receipt.provider_message_id": OPERATIONAL,
    "whatsapp_receipt.first_seen_at": OPERATIONAL,
    "whatsapp_receipt.handled_at": OPERATIONAL,
    "whatsapp_receipt.failures": OPERATIONAL,
    "whatsapp_receipt.last_failed_at": OPERATIONAL,
    "whatsapp_receipt.last_failure": OPERATIONAL,
    # "Which tablet?" (#162): the tablets it read out to him are his medicines — health.
    "whatsapp_dose_question.id": HEALTH,
    "whatsapp_dose_question.thread_id": HEALTH,
    "whatsapp_dose_question.asked_at": OPERATIONAL,
    "whatsapp_dose_question.expires_at": OPERATIONAL,
    "whatsapp_dose_question.doses": HEALTH,
    "whatsapp_dose_question.answered_at": OPERATIONAL,
    # A proposal is what was heard, waiting for the poster's yes: a reading, not yet a fact.
    "whatsapp_proposal.thread_id": HEALTH,
    "whatsapp_proposal.message_id": HEALTH,
    "whatsapp_proposal.poster_person_id": IDENTIFIER,
    "whatsapp_proposal.subject": HEALTH,
    "whatsapp_proposal.attribute": HEALTH,
    "whatsapp_proposal.value": HEALTH,
    "whatsapp_proposal.unit": HEALTH,
    "whatsapp_proposal.event_kind": HEALTH,
    "whatsapp_proposal.occurred_at": HEALTH,
    "whatsapp_proposal.said": HEALTH,
    "whatsapp_proposal.created_at": OPERATIONAL,
    "whatsapp_proposal.expires_at": OPERATIONAL,
    "whatsapp_proposal.status": OPERATIONAL,
    "whatsapp_proposal.answered_at": OPERATIONAL,
    "whatsapp_proposal.fact_id": HEALTH,
    "whatsapp_proposal.event_id": HEALTH,
    # The ladder beside a red flag: person ids in calling order, like the flag's `told`.
    "safety_escalation.flag_id": HEALTH,
    "safety_escalation.roster": IDENTIFIER,
    "safety_escalation.told": IDENTIFIER,
    "safety_escalation.created_at": HEALTH,
    # --- onboarding (E01) -----------------------------------------------------------------------
    # The settings screen says what helps him read, hear and remember — his abilities, folded
    # into State's functional and cognitive dimensions — and his conditions and his doctor:
    # health, like those dimensions. His breakfast time is folded into the preference
    # dimension and is health with it. The name he goes by and whoever set, added, answered
    # or skipped something point at a person. The language is operational, as on the person.
    # The biography's papers, lines and prompts point at his record, and a prompt's gap says
    # what is missing from it: health.
    "profile_settings.id": HEALTH,
    "profile_settings.conditions": HEALTH,
    "profile_settings.answers": HEALTH,
    "profile_settings.language": OPERATIONAL,
    "profile_settings.density": HEALTH,
    "profile_settings.large_text": HEALTH,
    "profile_settings.high_contrast": HEALTH,
    "profile_settings.voice_on": HEALTH,
    "profile_settings.big_targets": HEALTH,
    "profile_settings.one_thing_per_screen": HEALTH,
    "profile_settings.read_back": HEALTH,
    "profile_settings.repeat_prompts": HEALTH,
    "profile_settings.preferred_name": IDENTIFIER,
    "profile_settings.doctor_name": HEALTH,
    "profile_settings.breakfast_time": HEALTH,
    "profile_settings.checkin_time": HEALTH,
    # The decade he was born in: part of a date of birth, so it points at a person.
    "profile_settings.birth_decade": IDENTIFIER,
    "profile_settings.event_id": HEALTH,
    "profile_settings.set_by_person_id": IDENTIFIER,
    "profile_settings.set_at": OPERATIONAL,
    "profile_settings.supersedes_id": HEALTH,
    "profile_settings.superseded_at": OPERATIONAL,
    "biography_session.id": HEALTH,
    "biography_session.opened_by_person_id": IDENTIFIER,
    "biography_session.opened_at": OPERATIONAL,
    "biography_session.read_back_at": OPERATIONAL,
    "biography_session.read_back_by_person_id": IDENTIFIER,
    "biography_session.closed_at": OPERATIONAL,
    "biography_session.closed_by_person_id": IDENTIFIER,
    "biography_paper.id": HEALTH,
    "biography_paper.session_id": HEALTH,
    "biography_paper.position": OPERATIONAL,
    "biography_paper.artifact_id": HEALTH,
    "biography_paper.card_id": HEALTH,
    "biography_paper.paper": HEALTH,
    "biography_paper.added_by_person_id": IDENTIFIER,
    "biography_paper.added_at": OPERATIONAL,
    "biography_line.id": HEALTH,
    "biography_line.session_id": HEALTH,
    "biography_line.position": OPERATIONAL,
    "biography_line.fact_id": HEALTH,
    "biography_line.answer": HEALTH,
    "biography_line.dispute_fact_id": HEALTH,
    "biography_line.answered_by_person_id": IDENTIFIER,
    "biography_line.answered_at": OPERATIONAL,
    "activation_plan.id": HEALTH,
    "activation_plan.session_id": HEALTH,
    "activation_plan.breakfast_time": HEALTH,
    "activation_plan.first_day": OPERATIONAL,
    "activation_plan.created_by_person_id": IDENTIFIER,
    "activation_plan.created_at": OPERATIONAL,
    "plan_prompt.id": HEALTH,
    "plan_prompt.plan_id": HEALTH,
    "plan_prompt.day": OPERATIONAL,
    "plan_prompt.gap": HEALTH,
    "plan_prompt.due_at": OPERATIONAL,
    "plan_prompt.status": OPERATIONAL,
    "plan_prompt.done_at": OPERATIONAL,
    "plan_prompt.done_by_fact_id": HEALTH,
    "plan_prompt.skipped_at": OPERATIONAL,
    "plan_prompt.skipped_by_person_id": IDENTIFIER,
    "plan_prompt.deferred": OPERATIONAL,
    "biography_question.id": HEALTH,
    "biography_question.session_id": HEALTH,
    "biography_question.gap": HEALTH,
    "biography_question.kept": HEALTH,
    "biography_question.decided_by_person_id": IDENTIFIER,
    "biography_question.decided_at": OPERATIONAL,
    "biography_question.question_id": HEALTH,
    "biography_question.handed_over_at": OPERATIONAL,
    # --- trends, the routine, the calendar (E09-01, E10-01, E18-02) ---------------------------
    # A trend card is what was shown to him about his results: the analyte, the facts, the
    # direction, the lines and the boundary line are health, like a feed card's.
    "trend_card.analyte": HEALTH,
    "trend_card.language": OPERATIONAL,
    "trend_card.fact_ids": HEALTH,
    "trend_card.direction": HEALTH,
    "trend_card.lines": HEALTH,
    "trend_card.rendered_for_person_id": IDENTIFIER,
    "trend_card.rendered_at": OPERATIONAL,
    "trend_card.state_id": HEALTH,
    "trend_card.boundary": HEALTH,
    # His day: when he wakes, eats and sleeps, and what he is prompted to check, is about his
    # care; who set it points at a person.
    "routine.anchors": HEALTH,
    "routine.reading_prompts": HEALTH,
    "routine.walks": HEALTH,
    "routine.morning_card_at": OPERATIONAL,
    "routine.supersedes_id": HEALTH,
    "routine.superseded_at": OPERATIONAL,
    "routine.set_by_person_id": IDENTIFIER,
    "routine.set_at": OPERATIONAL,
    # A connector is a standing permission to read, resting on a consent: consent. A proposal
    # is a candidate visit — with whom, when, where — which is health; the digest is of the
    # event's UID, not its content.
    "connector.kind": CONSENT,
    "connector.source": OPERATIONAL,
    "connector.consent_id": CONSENT,
    "connector.connected_by_person_id": IDENTIFIER,
    "connector.connected_at": CONSENT,
    "appointment_proposal.connector_id": CONSENT,
    "appointment_proposal.event_digest": OPERATIONAL,
    "appointment_proposal.title": HEALTH,
    "appointment_proposal.location": HEALTH,
    "appointment_proposal.starts_at": HEALTH,
    "appointment_proposal.all_day": HEALTH,
    "appointment_proposal.matched_by": OPERATIONAL,
    "appointment_proposal.keyword": HEALTH,
    "appointment_proposal.provider_id": HEALTH,
    "appointment_proposal.provider_name": HEALTH,
    "appointment_proposal.provider_kind": HEALTH,
    "appointment_proposal.status": HEALTH,
    "appointment_proposal.found_at": OPERATIONAL,
    "appointment_proposal.decided_at": OPERATIONAL,
    "appointment_proposal.decided_by_person_id": IDENTIFIER,
    "appointment_proposal.appointment_id": HEALTH,
    # Capture extras (E02-02, E02-03, E02-06, E02-08): the kind a page was offered as and
    # where an imported PDF came from; who typed a field Nura could not read; and a note on
    # an event, whose recording or image is an artefact and whose heard words are in the
    # object store under `transcript_key` — the row holds a reference, never the words.
    "review_card.asked_as": HEALTH,
    "review_card.source": OPERATIONAL,
    "review_field.corrected_by_person_id": IDENTIFIER,
    "event_note.id": HEALTH,
    "event_note.event_id": HEALTH,
    "event_note.artifact_id": HEALTH,
    "event_note.kind": HEALTH,
    "event_note.private": CONSENT,
    "event_note.label": HEALTH,
    "event_note.transcript_key": HEALTH,
    "event_note.transcript_sha256": HEALTH,
    "event_note.transcript_confidence": OPERATIONAL,
    "event_note.transcript_language": OPERATIONAL,
    "event_note.written_by_person_id": IDENTIFIER,
    "event_note.written_at": HEALTH,
    # --- the feeling cloud and smart nudges (E17) ---------------------------------------------
    # A tap is how he said he feels: his word (a code), its answer, why the word was on the
    # cloud and the State it was read from are health; who tapped is an identifier. A note is
    # what the tap was read into, rendered for him: its lines, reasons and the visit it is kept
    # for are health, like a card's. A nudge's lines and why are health (a visit, a medicine,
    # his own words); its cap class, timing and ordering are operational, as on a feed card.
    # A response is what he did with a nudge: which nudge and the event are health, the kind
    # and the moment operational, like a card's engagement.
    "feeling_tap.id": HEALTH,
    "feeling_tap.event_id": HEALTH,
    "feeling_tap.word": HEALTH,
    "feeling_tap.red": HEALTH,
    "feeling_tap.flag_id": HEALTH,
    "feeling_tap.follow_up": HEALTH,
    "feeling_tap.answer": HEALTH,
    "feeling_tap.answered_at": HEALTH,
    "feeling_tap.emphasised": HEALTH,
    "feeling_tap.reasons": HEALTH,
    "feeling_tap.cloud_state_id": HEALTH,
    "feeling_tap.by_person_id": IDENTIFIER,
    "feeling_tap.tapped_at": HEALTH,
    "feeling_note.id": HEALTH,
    "feeling_note.state_id": HEALTH,
    "feeling_note.boundary": HEALTH,
    "feeling_note.tap_id": HEALTH,
    "feeling_note.word": HEALTH,
    "feeling_note.answer": HEALTH,
    "feeling_note.language": OPERATIONAL,
    "feeling_note.headline": HEALTH,
    "feeling_note.said": HEALTH,
    "feeling_note.lines": HEALTH,
    "feeling_note.then": HEALTH,
    "feeling_note.voice": HEALTH,
    "feeling_note.reasons": HEALTH,
    "feeling_note.outcome": HEALTH,
    "feeling_note.appointment_id": HEALTH,
    "feeling_note.created_at": OPERATIONAL,
    "nudge.id": HEALTH,
    "nudge.state_id": HEALTH,
    "nudge.boundary": HEALTH,
    "nudge.kind": HEALTH,
    "nudge.scope": OPERATIONAL,
    "nudge.day": OPERATIONAL,
    "nudge.language": OPERATIONAL,
    "nudge.lines": HEALTH,
    "nudge.voice": HEALTH,
    "nudge.why": HEALTH,
    "nudge.reason": HEALTH,
    "nudge.cap_class": OPERATIONAL,
    "nudge.priority": OPERATIONAL,
    "nudge.send_after": OPERATIONAL,
    "nudge.expires_at": OPERATIONAL,
    "nudge.dedupe_key": HEALTH,
    "nudge.memo_id": HEALTH,
    "nudge.handed_over_at": OPERATIONAL,
    "nudge.handed_over_by_person_id": IDENTIFIER,
    "nudge_response.id": HEALTH,
    "nudge_response.nudge_id": HEALTH,
    "nudge_response.person_id": IDENTIFIER,
    "nudge_response.kind": OPERATIONAL,
    "nudge_response.event_id": HEALTH,
    "nudge_response.at": OPERATIONAL,
    # The pharmacist's review queue (E22-04, docs/adr/0007-the-pharmacist-review-queue.md):
    # operator data, de-identified. No column points at a profile or a person on anyone's
    # record — a card's lines are stored with every name taken out (`{name}`, `{doctor}`) and
    # his record's own words left out, a source is a publisher, and `decided_by` is a staff
    # handle from the deployment's staff list. The words themselves are health, de-identified
    # (the operator's decision, 2026-09-15, on the clinical-safety review): a sample keeps his
    # readings, days and plain names for medicines, a rewrite proposes such lines, and a
    # reason is free text a pharmacist may quote a line into. The rest is operational.
    "review_item.id": OPERATIONAL,
    "review_item.kind": OPERATIONAL,
    "review_item.card_type": OPERATIONAL,
    "review_item.sample_number": OPERATIONAL,
    "review_item.source_id": OPERATIONAL,
    "review_item.language": OPERATIONAL,
    "review_item.lines": HEALTH,
    "review_item.catalogue_ids": OPERATIONAL,
    "review_item.digest": OPERATIONAL,
    "review_item.verdict": OPERATIONAL,
    "review_item.reason": HEALTH,
    "review_item.proposed": HEALTH,
    "review_item.decided_by": OPERATIONAL,
    "review_item.created_at": OPERATIONAL,
    "review_item.decided_at": OPERATIONAL,
    # The fuller insurance record (E13-03), beside the one field `insurer` already keeps for
    # the emergency card: a policy's insurer, reference and who and what it covers all point
    # at him or say something about his cover, so all are identifiers; the type, the dates
    # and the status describe the policy, not a person directly, but sit beside an identifier
    # closely enough to be read the same way; who typed it is an identifier, the yes a
    # consent record, when operational.
    "policy.id": IDENTIFIER,
    "policy.insurer_name": IDENTIFIER,
    "policy.policy_reference": IDENTIFIER,
    "policy.policy_type": IDENTIFIER,
    "policy.covered": IDENTIFIER,
    "policy.covers": IDENTIFIER,
    "policy.start_date": IDENTIFIER,
    "policy.renewal_date": IDENTIFIER,
    "policy.premium_due_date": IDENTIFIER,
    "policy.status": IDENTIFIER,
    "policy.guarantee_letter": IDENTIFIER,
    "policy.supersedes_id": IDENTIFIER,
    "policy.superseded_at": OPERATIONAL,
    "policy.set_by_person_id": IDENTIFIER,
    "policy.confirmation_id": CONSENT,
    "policy.set_at": OPERATIONAL,
    # A claim names a policy and a visit, both identifiers by the same rule, and carries the
    # insurer's own claim number on the same terms as a policy reference.
    "insurance_claim.id": IDENTIFIER,
    "insurance_claim.policy_id": IDENTIFIER,
    "insurance_claim.appointment_id": IDENTIFIER,
    "insurance_claim.claim_reference": IDENTIFIER,
    "insurance_claim.status": IDENTIFIER,
    # The three amounts the ledger sums (0047, T2 `app.insurance.ledger`): what money moved
    # for his care, the same standing as a medicine's dose or a reading's number — health,
    # not an identifier and not merely operational.
    "insurance_claim.claimed_amount_cents": HEALTH,
    "insurance_claim.paid_by_insurer_cents": HEALTH,
    "insurance_claim.paid_by_patient_cents": HEALTH,
    "insurance_claim.filed_by_person_id": IDENTIFIER,
    "insurance_claim.confirmation_id": CONSENT,
    "insurance_claim.filed_at": OPERATIONAL,
    "insurance_claim.status_changed_by_person_id": IDENTIFIER,
    "insurance_claim.status_changed_confirmation_id": CONSENT,
    "insurance_claim.status_changed_at": OPERATIONAL,
    # --- the Health Analyst's weekly report (`app.reasoning.analyst`) -----------------------
    "insight_report.id": HEALTH,
    "insight_report.generated_at": OPERATIONAL,
    "insight_report.week_of": OPERATIONAL,
    "insight_report.language": OPERATIONAL,
    # Which analyst wrote it, "rule" or "claude" (`app.reasoning.analyst.provider`):
    # provenance of the row, not itself a fact about his health.
    "insight_report.source": OPERATIONAL,
    # The boundary line the report carried (`Surface.INSIGHT`), the same standing as
    # `feed_item.boundary` above.
    "insight_report.boundary": HEALTH,
    # Every section and insight the report holds: composed, already-verified text about his
    # week — health, the same standing as `trend_card.lines`.
    "insight_report.sections": HEALTH,
}


class Unclassified(RuntimeError):
    """A column reached the data map without a classification. Add it to CLASSES."""


def classification_of(table: str, column: str) -> str:
    for key in (f"{table}.{column}", f"*.{column}"):
        if key in CLASSES:
            return CLASSES[key]
    raise Unclassified(f"{table}.{column} has no classification in scripts/data_map.py")


def tables() -> list[Table]:
    """Every table of the app, in the order the metadata sorts them (dependencies first)."""
    return [t for t in Base.metadata.sorted_tables if not t.name.startswith("test_")]


def _type_name(kind: TypeEngine[object]) -> str:
    """A column type's name; a decorated type (`UTCDateTime`) by the type it stores as."""
    return type(kind.impl if isinstance(kind, TypeDecorator) else kind).__name__


def rows() -> Iterator[tuple[str, str, str, str, str]]:
    """(table, column, type, nullable, classification) for every column. The type is the
    SQLAlchemy type's name (`Uuid`, `String`, `JSON`), the same on SQLite and Postgres."""
    for table in tables():
        for column in table.columns:
            yield (
                table.name,
                column.name,
                _type_name(column.type),
                "yes" if column.nullable else "no",
                classification_of(table.name, column.name),
            )


def render() -> str:
    """The Markdown block: the counts, then the table."""
    listed = list(rows())
    counts = {c: sum(1 for r in listed if r[4] == c) for c in CLASSIFICATIONS}
    lines = [
        BEGIN,
        f"{len(tables())} tables, {len(listed)} columns: "
        + ", ".join(f"{counts[c]} {c}" for c in CLASSIFICATIONS)
        + ". Generated by `python3 -m scripts.data_map`; do not edit by hand.",
        "",
        "| Table | Column | Type | Nullable | Classification |",
        "|---|---|---|---|---|",
    ]
    lines.extend(f"| `{t}` | `{c}` | {ty} | {n} | {cl} |" for t, c, ty, n, cl in listed)
    lines.append(END)
    return "\n".join(lines)


def block_in(document: str) -> str | None:
    match = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), document, re.DOTALL)
    return match.group(0) if match else None


def check(document_path: Path = DOCUMENT) -> list[str]:
    """What is wrong with the document's block, if anything: a list of problems, empty if none."""
    if not document_path.is_file():
        return [f"{document_path} does not exist"]
    found = block_in(document_path.read_text(encoding="utf-8"))
    if found is None:
        return [f"{document_path} has no {BEGIN} … {END} block"]
    if found != render():
        return [f"{document_path}: the data-map block is out of date; run python3 -m scripts.data_map"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="data_map", description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare with the document")
    parser.add_argument("--document", type=Path, default=DOCUMENT)
    args = parser.parse_args(argv)
    if args.check:
        problems = check(args.document)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    print(render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
