import * as nura from "../api/nura";
import { browserSpeech } from "../speech/speak";
import { kvGet, kvSet } from "../store/kv";
import { profile, token } from "../store/session";
import { isSpeed, Player, type MediaLike } from "./player";

/** The one player the whole app plays through (E15-07): the browser's audio element, the
 *  phone's own voice, the API's clip route, and his speed kept on this phone. */

export const SPEED_KEY = "device.speed";

export const voice = new Player({
  media: () => new Audio() as unknown as MediaLike,
  objectUrl: (blob) => URL.createObjectURL(blob),
  revoke: (url) => URL.revokeObjectURL(url),
  fetchClip: (artifactId, start, end) => nura.clip(token.value ?? "", profile.value?.profile_id ?? "", artifactId, start, end),
  speech: browserSpeech,
  saveRate: (rate) => kvSet(SPEED_KEY, rate),
});

/** His speed, as this phone remembers it. Like the language and the look, it stays after
 *  sign-out: it is how the phone sounds, not anything about his papers. */
export async function restoreSpeed(): Promise<void> {
  const saved = await kvGet<number>(SPEED_KEY);
  if (isSpeed(saved)) voice.rate.value = saved;
}
