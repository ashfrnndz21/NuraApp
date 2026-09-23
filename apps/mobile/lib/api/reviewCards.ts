import { http } from './httpClient';
import { apiConfig } from './config';
import type {
  ReviewCard,
  ReviewField,
  ReviewClarify,
  ConfirmCardIn,
  DocumentKind,
  DocumentSource,
  FieldRange,
  FieldState,
} from '../../domain/reviewCard';

export interface ReviewFieldRangeWire {
  low: number | null;
  high: number | null;
  text: string | null;
}

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
  span: Record<string, number> | null;
  range: ReviewFieldRangeWire | null;
  label_on_paper: string | null;
  state: FieldState;
  corrected_value: unknown;
  corrected_by_person_id: string | null;
  fact_id: string | null;
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

function rangeFromWire(w: ReviewFieldRangeWire | null): FieldRange | null {
  if (!w) return null;
  return { low: w.low, high: w.high, text: w.text };
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
    span: w.span,
    range: rangeFromWire(w.range),
    labelOnPaper: w.label_on_paper,
    state: w.state,
    correctedValue: w.corrected_value,
    correctedByPersonId: w.corrected_by_person_id,
    factId: w.fact_id,
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
 * `POST /profiles/{id}/confirmations` (`subject: 'review_card'`) — mints
 * the one-time "yes" `POST …/confirm` requires. A real bug found live
 * (second independent review of PR #332, while capturing screenshots):
 * `confirmationId` was previously a client-generated string
 * (`${cardId}:${Date.now()}`), which the backend correctly refused —
 * first with a 422 (not a UUID at all), then, once that was fixed to a
 * real UUID, with `NotAConfirmerHere` (400): `confirmation_id` is not a
 * client idempotency key, it references a *minted* confirmation, bound
 * server-side to exactly this card and exactly these decisions
 * (`ReviewCardConfirmIn`'s own doc: "the yes binds to every field as
 * shown and every decision as made"), so a stale or invented one can
 * never be replayed against different data.
 */
async function mintReviewCardConfirmation(
  profileId: string,
  cardId: string,
  decisions: { field_id: string; decision: string; corrected_value: unknown }[],
  episodeId?: string | null,
): Promise<string> {
  const res = await http.post<{ confirmation_id: string }>(`/profiles/${profileId}/confirmations`, {
    subject: 'review_card',
    card_id: cardId,
    decisions,
    episode_id: episodeId ?? null,
  });
  return res.confirmation_id;
}

/**
 * `POST /profiles/{id}/review-cards/{cardId}/confirm` — the uncertain-field
 * review's own submit (C3). Mints the confirmation first, over the exact
 * same decisions, then spends it — two calls, not a client-invented id.
 */
export async function confirmReviewCard(
  profileId: string,
  cardId: string,
  body: ConfirmCardIn,
): Promise<ReviewCard> {
  const decisions = body.decisions.map((d) => ({
    field_id: d.fieldId,
    decision: d.decision,
    corrected_value: d.correctedValue ?? null,
  }));
  const confirmationId = await mintReviewCardConfirmation(profileId, cardId, decisions, body.episodeId);
  const wire = await http.post<{ card: ReviewCardWire }>(
    `/profiles/${profileId}/review-cards/${cardId}/confirm`,
    {
      decisions,
      confirmation_id: confirmationId,
      episode_id: body.episodeId ?? null,
    },
  );
  return reviewCardFromWire(wire.card);
}
