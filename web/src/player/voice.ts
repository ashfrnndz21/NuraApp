import { effect } from "@preact/signals";
import * as nura from "../api/nura";
import { browserSpeech } from "../speech/speak";
import { kvSet } from "../store/kv";
import { profile, savedSpeed, SPEED_KEY, token } from "../store/session";
import { isSpeed, Player, type MediaLike } from "./player";

/** The one player the whole app plays through (E15-07): the browser's audio element, the
 *  phone's own voice, the API's clip route, and his speed kept on this phone (`device.speed`).
 *  Like the language and the look, his speed stays after sign-out: it is how the phone sounds,
 *  not anything about his papers. */

export const voice = new Player({
  media: () => new Audio() as unknown as MediaLike,
  objectUrl: (blob) => URL.createObjectURL(blob),
  revoke: (url) => URL.revokeObjectURL(url),
  fetchClip: (artifactId, start, end) => nura.clip(token.value ?? "", profile.value?.profile_id ?? "", artifactId, start, end),
  speech: browserSpeech,
  saveRate: (rate) => kvSet(SPEED_KEY, rate),
});

// His speed as the session restored it, before any screen shows.
effect(() => {
  const saved = savedSpeed.value;
  if (isSpeed(saved)) voice.rate.value = saved;
});
