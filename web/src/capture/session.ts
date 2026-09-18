import * as nura from "../api/nura";
import type { ReviewCardOut } from "../api/types";
import { base64Of } from "../onboarding/actions";
import { readable } from "../onboarding/review";
import { profile, token } from "../store/session";
import { isPdf, PaperBatch } from "./batch";

function who(): { bearer: string; profileId: string } {
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) throw new Error("no session");
  return { bearer, profileId: papers.profile_id };
}

/** The backend's own caps (`app.ingestion.photos.MAX_PHOTO_BYTES`,
 *  `app.ingestion.documents.MAX_PDF_BYTES`): a file at or past one of these is refused
 *  outright, so it goes through the plain route rather than the streamed one — the layer in
 *  front of the app answers a body this large before a single real step could ever run
 *  (papers.spec.ts "a photo too large for Nura"), and the plain route's refusal is the one
 *  already proven right for it. */
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;
const MAX_PDF_BYTES = 20 * 1024 * 1024;

/** A photo or PDF sent through the streamed capture routes (docs/design-direction.md
 *  'Conversation, waiting and thinking'): `onStep` fires with the backend's own words the
 *  instant each real stage finishes, and the promise settles with the same review card the
 *  plain routes give. A file past the backend's own size cap goes through the plain route
 *  instead, with no step: there is no real trace to show for a page that is refused outright. */
async function sendPaperStream(file: File, onStep: (key: string, label: string) => void): Promise<ReviewCardOut> {
  const { bearer, profileId } = who();
  const data = await base64Of(file);
  const taken = new Date(file.lastModified || Date.now()).toISOString();
  if (isPdf(file)) {
    if (file.size >= MAX_PDF_BYTES) return nura.addImport(bearer, profileId, data, "application/pdf", taken, "share");
    return nura.addImportStream(bearer, profileId, data, "application/pdf", taken, "share", onStep);
  }
  if (file.size >= MAX_PHOTO_BYTES) return nura.addPhoto(bearer, profileId, data, file.type || "application/octet-stream", taken);
  return nura.addPhotoStream(bearer, profileId, data, file.type || "application/octet-stream", taken, onStep);
}

/** The one batch of papers from his photos, for as long as the page is open: kept in memory
 *  while he checks each card and comes back, and let go when he leaves (`PaperBatch.forget`). */
export const batch = new PaperBatch({
  thumb: (file) => URL.createObjectURL(file),
  revoke: (url) => URL.revokeObjectURL(url),
  send: sendPaperStream,
  readable,
});
