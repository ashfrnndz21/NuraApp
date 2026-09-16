import { sendPaper } from "../onboarding/actions";
import { readable } from "../onboarding/review";
import { PaperBatch } from "./batch";

/** The one batch of papers from his photos, for as long as the page is open: kept in memory
 *  while he checks each card and comes back, and let go when he leaves (`PaperBatch.forget`). */
export const batch = new PaperBatch({
  thumb: (file) => URL.createObjectURL(file),
  revoke: (url) => URL.revokeObjectURL(url),
  send: sendPaper,
  readable,
});
