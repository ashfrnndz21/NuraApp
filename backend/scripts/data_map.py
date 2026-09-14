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

from sqlalchemy import Table

# Every module that declares a table, so the metadata is whole.
import app.audit.models
import app.channels.whatsapp.models
import app.consent.models
import app.delivery.feed.models
import app.family.models
import app.identity.models
import app.ingestion.models
import app.keys.confirm
import app.keys.models
import app.keys.privacy
import app.medicines.models
import app.memory.models
import app.notes.models
import app.onboarding.models
import app.safety.red_flags
import app.state.models  # noqa: F401
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
    "task.id": HEALTH,
    "scheduled_push.id": HEALTH,
    "document.id": HEALTH,
    "roster_slot.id": IDENTIFIER,
    "privacy.id": CONSENT,
    # --- accounts and the graph's ownership -------------------------------------------------
    "person.display_name": IDENTIFIER,
    "person.language": OPERATIONAL,
    "person.phone_e164": IDENTIFIER,
    "person.email": IDENTIFIER,
    "person.created_at": OPERATIONAL,
    "profile.display_name": IDENTIFIER,
    "profile.language": OPERATIONAL,
    "profile.owner_person_id": IDENTIFIER,
    "profile.patient_phone_e164": IDENTIFIER,
    "profile.created_at": OPERATIONAL,
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
    "medication_line.dose": HEALTH,
    "medication_line.prescriber": HEALTH,
    "medication_line.source_kind": HEALTH,
    "medication_line.lead_time_days": OPERATIONAL,
    "medication_line.reorder_threshold_days": OPERATIONAL,
    "medication_line.source_artifact_id": HEALTH,
    "medication_line.source_event_id": HEALTH,
    "medication_line.confidence": OPERATIONAL,
    "medication_line.confidence_state": OPERATIONAL,
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
    "dose_taken.by_person_id": IDENTIFIER,
    "interaction_flag.line_id": HEALTH,
    "interaction_flag.other_line_id": HEALTH,
    "interaction_flag.severity": HEALTH,
    "interaction_flag.text_id": HEALTH,
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
    "feed_engagement.item_id": HEALTH,
    "feed_engagement.person_id": IDENTIFIER,
    "feed_engagement.kind": OPERATIONAL,
    "feed_engagement.channel": OPERATIONAL,
    "feed_engagement.event_id": HEALTH,
    "feed_engagement.at": OPERATIONAL,
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
    "task.what": HEALTH,
    "task.assigned_person_id": IDENTIFIER,
    "task.due_at": OPERATIONAL,
    "task.created_by_person_id": IDENTIFIER,
    "task.created_at": OPERATIONAL,
    "task.done_at": OPERATIONAL,
    "task.done_by_person_id": IDENTIFIER,
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


def rows() -> Iterator[tuple[str, str, str, str, str]]:
    """(table, column, type, nullable, classification) for every column. The type is the
    SQLAlchemy type's name (`Uuid`, `String`, `JSON`), the same on SQLite and Postgres."""
    for table in tables():
        for column in table.columns:
            yield (
                table.name,
                column.name,
                type(column.type).__name__,
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
