import { Refused } from "../api/client";
import * as nura from "../api/nura";
import type { BiographyOut, PlanOut, ReviewCardOut } from "../api/types";
import { profile, setDensity, token } from "../store/session";
import { language } from "../strings";
import { deviceEffects, startingSettings, tidy } from "./about";
import { biography, closed, draft, picked, plan, settings, to, whose } from "./state";

/** The calls more than one step makes, on #117's routes. Each throws what the API threw; the
 *  screen that called it shows it (`Notice`) — a refusal is never swallowed here. */

function who(): { bearer: string; profileId: string } {
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) throw new Error("no session");
  return { bearer, profileId: papers.profile_id };
}

/** Open the sitting, or read the one already open (`BiographyAlreadyOpen`). */
export async function openSitting(): Promise<void> {
  const { bearer, profileId } = who();
  try {
    biography.value = await nura.openBiography(bearer, profileId);
  } catch (failure) {
    if (!(failure instanceof Refused) || failure.refusal !== "BiographyAlreadyOpen") throw failure;
    biography.value = await nura.biography(bearer, profileId, language.value);
  }
}

export async function refreshBiography(): Promise<void> {
  const { bearer, profileId } = who();
  biography.value = await nura.biography(bearer, profileId, language.value);
}

export async function refreshPlan(): Promise<void> {
  const { bearer, profileId } = who();
  plan.value = await nura.plan(bearer, profileId, language.value);
}

/** The settings screen, whole, with the words he tapped as `conditions`: one PUT. His density
 *  follows at once on his own phone; the sitting moves on to his papers. */
export async function saveSettings(): Promise<void> {
  const { bearer, profileId } = who();
  const base = draft.value ?? startingSettings(settings.value, profile.value, language.value);
  const body = tidy({ ...base, conditions: picked.value });
  settings.value = await nura.putSettings(bearer, profileId, body);
  draft.value = body;
  const effects = deviceEffects(body, profile.value?.standing);
  if (effects.density) await setDensity(effects.density);
  if (biography.value && !biography.value.closed_at) await refreshBiography();
}

/** After the cloud (or its follow-ups): save the words, then on to the papers. */
export async function saveWordsAndGoOn(): Promise<void> {
  await saveSettings();
  to({ name: "records" });
}

/** E01's writes answer in the language on his settings. A chief reads in her own phone's
 *  (`?language=`), so for her the sitting and the week are read again after each write. */
export async function inMyLanguage(view: BiographyOut): Promise<BiographyOut> {
  if (whose().self) return view;
  const { bearer, profileId } = who();
  return nura.biography(bearer, profileId, language.value);
}

export async function planInMyLanguage(view: PlanOut): Promise<PlanOut> {
  if (whose().self) return view;
  const { bearer, profileId } = who();
  return nura.plan(bearer, profileId, language.value);
}

/** Close the sitting: its summary and the first week come back with it. */
export async function closeSitting(): Promise<void> {
  const { bearer, profileId } = who();
  const done = await nura.closeBiography(bearer, profileId);
  closed.value = done;
  biography.value = await inMyLanguage(done.biography);
  plan.value = await planInMyLanguage(done.plan);
  to({ name: "plan" });
}

/** The bytes of a photo or a file, base64, as `PhotoIn` and `ImportIn` take them. */
export function base64Of(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** A PDF is read by `POST /imports` (E02-03); anything else is a photo for `POST /photos`. */
export function isPdf(file: Pick<File, "type" | "name">): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export async function sendPaper(file: File): Promise<ReviewCardOut> {
  const { bearer, profileId } = who();
  const data = await base64Of(file);
  const taken = new Date(file.lastModified || Date.now()).toISOString();
  if (isPdf(file)) return nura.addImport(bearer, profileId, data, "application/pdf", taken, "share");
  return nura.addPhoto(bearer, profileId, data, file.type || "application/octet-stream", taken);
}

export { who };
