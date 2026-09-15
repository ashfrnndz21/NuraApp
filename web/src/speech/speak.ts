import { signal } from "@preact/signals";
import type { SpeechLike } from "../player/player";
import { LOCALE, type Language } from "../strings";

/** The spoken twin of a card: its lines, read one after another with a pause between.
 *
 *  One function, `speak(card)`, is the whole seam. Today it is the Web Speech API with a
 *  voice that runs on the phone (`localService`) and no other: a network voice would send
 *  the words — medicine names, dose sentences — to a vendor's servers, outside the region
 *  and outside the consent. With no local voice for the language, nothing is spoken. The
 *  backend's pre-rendered voice is a later adapter set with `setSpeaker`. Audio starts
 *  only from a tap — nothing here is called on load, on a new card, or after another. */

export interface SpokenCard {
  lines: readonly string[];
  language: Language;
}

export type Speaker = (card: SpokenCard) => void;

export const speaking = signal(false);

type VoiceLike = Pick<SpeechSynthesisVoice, "lang" | "localService">;

/** A voice that runs on the device, for this language: exact locale first, then the
 *  language, then none. */
export function pickLocalVoice<V extends VoiceLike>(voices: readonly V[], language: Language): V | null {
  const local = voices.filter((voice) => voice.localService);
  const wanted = LOCALE[language].toLowerCase();
  const code = language.toLowerCase();
  return (
    local.find((voice) => voice.lang.toLowerCase().replace("_", "-") === wanted) ??
    local.find((voice) => voice.lang.toLowerCase().slice(0, 2) === code) ??
    null
  );
}

function webSpeech(card: SpokenCard): void {
  const synth = typeof speechSynthesis === "undefined" ? null : speechSynthesis;
  if (!synth) return;
  const voice = pickLocalVoice(synth.getVoices(), card.language);
  if (!voice) return; // no local voice: stay silent rather than leave the region
  synth.cancel();
  const lines = card.lines.filter((line) => line.trim().length > 0);
  if (lines.length === 0) return;
  speaking.value = true;
  lines.forEach((line, index) => {
    const utterance = new SpeechSynthesisUtterance(line);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.9;
    if (index === lines.length - 1) {
      utterance.onend = () => (speaking.value = false);
      utterance.onerror = () => (speaking.value = false);
    }
    synth.speak(utterance);
  });
}

let speaker: Speaker = webSpeech;

export function setSpeaker(next: Speaker): void {
  speaker = next;
}

/** Read this card out. Call it from a tap handler and nowhere else. */
export function speak(card: SpokenCard): void {
  speaker(card);
}

export function stopSpeaking(): void {
  if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  speaking.value = false;
}

/** The phone's own voice for the one player (`player/player.ts`): the lines one after another
 *  at his speed, each reported as it starts, so the transcript under the controls follows. The
 *  same rule as `speak`: only a voice that runs on the phone; with none for the language it
 *  answers false and nothing is said. */
export const browserSpeech: SpeechLike = {
  say(lines, language, rate, events) {
    const synth = typeof speechSynthesis === "undefined" ? null : speechSynthesis;
    if (!synth) return false;
    const voice = pickLocalVoice(synth.getVoices(), language);
    if (!voice) return false;
    synth.cancel();
    if (lines.length === 0) return false;
    speaking.value = true;
    lines.forEach((line, index) => {
      const utterance = new SpeechSynthesisUtterance(line);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = 0.9 * rate;
      utterance.onstart = () => events.onLine(index);
      if (index === lines.length - 1) {
        utterance.onend = () => {
          speaking.value = false;
          events.onEnd();
        };
        utterance.onerror = () => (speaking.value = false);
      }
      synth.speak(utterance);
    });
    return true;
  },
  pause() {
    if (typeof speechSynthesis !== "undefined") speechSynthesis.pause();
  },
  resume() {
    if (typeof speechSynthesis !== "undefined") speechSynthesis.resume();
  },
  cancel: () => stopSpeaking(),
};
