import { http } from './httpClient';
import { apiConfig } from './config';
import type {
  ReviewCard,
  ReviewField,
  ReviewClarify,
  ConfirmCardIn,
  DocumentKind,
  DocumentSource,
} from '../../domain/reviewCard';

export interface ReviewFieldWire {
  field_id: string;
  position: number;
  subject: string;
  attribute: string;
  value: unknown;
  unit: string | null;
  confidence: number;
  needs_confirm: boolean;
  unreadable: boolean;
  prompt: string[] | null;
  page: number | null;
}

export interface ReviewClarifyWire {
  kind: string;
  mismatched: string[];
  existing_card_id: string | null;
  existing_added_on: string | null;
}

export interface ReviewCardWire {
  card_id: string;
  profile_id: string;
  artifact_id: string;
  document_kind: DocumentKind;
  document_date: string | null;
  asked_as: DocumentKind | null;
  source: DocumentSource | null;
  notice: string[] | null;
  high_risk_class: string | null;
  created_at: string;
  confirmed_at: string | null;
  confirmed_by_person_id: string | null;
  fields: ReviewFieldWire[];
  clarify: ReviewClarifyWire | null;
  discarded: boolean;
  duplicate_of_added_on: string | null;
}

function fieldFromWire(w: ReviewFieldWire): ReviewField {
  return {
    fieldId: w.field_id,
    position: w.position,
    subject: w.subject,
    attribute: w.attribute,
    value: w.value,
    unit: w.unit,
    confidence: w.confidence,
    needsConfirm: w.needs_confirm,
    unreadable: w.unreadable,
    prompt: w.prompt,
    page: w.page,
  };
}

function clarifyFromWire(w: ReviewClarifyWire | null): ReviewClarify | null {
  if (!w) return null;
  return {
    kind: w.kind,
    mismatched: w.mismatched,
    existingCardId: w.existing_card_id,
    existingAddedOn: w.existing_added_on,
  };
}

export function reviewCardFromWire(w: ReviewCardWire): ReviewCard {
  return {
    cardId: w.card_id,
    profileId: w.profile_id,
    artifactId: w.artifact_id,
    documentKind: w.document_kind,
    documentDate: w.document_date,
    askedAs: w.asked_as,
    source: w.source,
    notice: w.notice,
    highRiskClass: w.high_risk_class,
    createdAt: w.created_at,
    confirmedAt: w.confirmed_at,
    confirmedByPersonId: w.confirmed_by_person_id,
    fields: w.fields.map(fieldFromWire),
    clarify: clarifyFromWire(w.clarify),
    discarded: w.discarded,
    duplicateOfAddedOn: w.duplicate_of_added_on,
  };
}

/** `GET /profiles/{id}/review-cards` — the report table's source (C3). */
export async function listReviewCards(profileId: string): Promise<ReviewCard[]> {
  if (apiConfig.mode === 'demo') return [];
  const wire = await http.get<ReviewCardWire[]>(`/profiles/${profileId}/review-cards`);
  return wire.map(reviewCardFromWire);
}

/** `GET /profiles/{id}/review-cards/{cardId}`. */
export async function getReviewCard(profileId: string, cardId: string): Promise<ReviewCard> {
  return reviewCardFromWire(
    await http.get<ReviewCardWire>(`/profiles/${profileId}/review-cards/${cardId}`),
  );
}

/**
 * `POST /profiles/{id}/review-cards/{cardId}/answer` — the card's one
 * pending question (whose-paper / duplicate), a chip's opaque `value`
 * only, never free text (`ReviewAnswerIn`'s own doc).
 */
export async function answerReviewCard(profileId: string, cardId: string, value: string): Promise<ReviewCard> {
  return reviewCardFromWire(
    await http.post<ReviewCardWire>(`/profiles/${profileId}/review-cards/${cardId}/answer`, { value }),
  );
}

/**
 * `POST /profiles/{id}/review-cards/{cardId}/confirm` — the uncertain-field
 * review's own submit (C3). `confirmationId` is a client-generated
 * idempotency key: the same confirm retried after a dropped connection
 * must not double-confirm.
 */
export async function confirmReviewCard(
  profileId: string,
  cardId: string,
  body: ConfirmCardIn,
): Promise<ReviewCard> {
  const wire = await http.post<{ card: ReviewCardWire }>(
    `/profiles/${profileId}/review-cards/${cardId}/confirm`,
    {
      decisions: body.decisions.map((d) => ({
        field_id: d.fieldId,
        decision: d.decision,
        corrected_value: d.correctedValue ?? null,
      })),
      confirmation_id: body.confirmationId,
      episode_id: body.episodeId ?? null,
    },
  );
  return reviewCardFromWire(wire.card);
}
