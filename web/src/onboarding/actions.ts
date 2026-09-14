import * as nura from "../api/nura";
import type { ReviewCardOut } from "../api/types";
import { profile, token } from "../store/session";
import { language } from "../strings";
import { answers, biography, picked, to } from "./state";

/** The calls more than one step makes. Each throws what the API threw; the screen that
 *  called it shows it (`Notice`) — a refusal is never swallowed here. */

function who(): { bearer: string; profileId: string } {
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) throw new Error("no session");
  return { bearer, profileId: papers.profile_id };
}

/** Open (or update) the biography with the words he tapped and his answers; the backend
 *  answers with the read-back lines, whole. */
export async function tell(): Promise<void> {
  const { bearer, profileId } = who();
  biography.value = await nura.tellBiography(bearer, profileId, {
    language: language.value,
    words: picked.value,
    answers: answers.value,
  });
  to({ name: "readBack" });
}

/** The bytes of a photo or a file, base64, as `PhotoIn` takes them. */
export function base64Of(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** A photo (or a PDF, which the backend refuses in its own words until it takes them) up to
 *  `POST /photos`; the answer is the review card. */
export async function sendPaper(file: File): Promise<ReviewCardOut> {
  const { bearer, profileId } = who();
  const data = await base64Of(file);
  const taken = new Date(file.lastModified || Date.now()).toISOString();
  return nura.addPhoto(bearer, profileId, data, file.type || "application/octet-stream", taken);
}

export { who };
