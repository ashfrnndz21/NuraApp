import { http } from './httpClient';
import { apiConfig } from './config';
import type { ReviewCard, DocumentKind } from '../../domain/reviewCard';
import { reviewCardFromWire, type ReviewCardWire } from './reviewCards';

export interface PhotoIn {
  /** Base64 bytes — never a file path or a blob URL held past the request. */
  data: string;
  contentType: string;
  capturedAt: string;
  /** What the person says the page is — a hint to the extractor, never taken as the answer. */
  documentKind?: DocumentKind;
}

/**
 * `POST /profiles/{id}/photos` — the direct (non-streaming) upload path.
 * C2's "Nura reads it" screen uses the streaming path instead
 * (`POST /profiles/{id}/runs` with `intent: 'understand_paper'`,
 * `lib/ai/runClient.ts`) so its stages come from real `TOOL_CALL_START`
 * events, never a fake progress bar; this one is for a caller that only
 * needs the finished card (C3's report table, once a card already exists).
 */
export async function uploadPhoto(profileId: string, photo: PhotoIn): Promise<ReviewCard> {
  if (apiConfig.mode === 'demo') {
    throw new Error('uploadPhoto: demo mode has no fixture yet — use the C2 event stream fixture instead.');
  }
  const wire = await http.post<ReviewCardWire>(`/profiles/${profileId}/photos`, {
    data: photo.data,
    content_type: photo.contentType,
    captured_at: photo.capturedAt,
    document_kind: photo.documentKind ?? null,
  });
  return reviewCardFromWire(wire);
}
