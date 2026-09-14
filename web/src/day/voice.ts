import type { Said } from "../api/types";
import { browserRecorderDeps, canRecord, ConsultRecorder, type Kept } from "../visit/recorder";

/** His own voice note (E13-02, E14-01): the phone's recorder, started by his tap and stopped by
 *  his tap, sent once. His own words, kept like typed text (ADR 0003): no recording consent is
 *  asked, and nothing is sent until he stops. */

export { canRecord };

export function voiceRecorder(): ConsultRecorder {
  return new ConsultRecorder(browserRecorderDeps());
}

/** A kept note as the safety routes take it: the bytes as base64, the plain content type. */
export async function saidOf(kept: Kept): Promise<Said> {
  const bytes = new Uint8Array(await kept.blob.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const type = (kept.blob.type || "audio/webm").split(";")[0]!.trim();
  return { audio: btoa(binary), content_type: type };
}
