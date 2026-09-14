import { signal } from "@preact/signals";
import { LOCALE, type Language } from "../strings";

/** The spoken twin of a card: its lines, read one after another with a pause between.
 *
 *  One function, `speak(card)`, is the whole seam. Today it is the Web Speech API; the
 *  backend's pre-rendered voice is a later adapter set with `setSpeaker`, and nothing
 *  else changes. Audio starts only from a tap — nothing here is called on load, on a new
 *  card, or after another card finishes. */

export interface SpokenCard {
  lines: readonly string[];
  language: Language;
}

export type Speaker = (card: SpokenCard) => void;

export const speaking = signal(false);

function webSpeech(card: SpokenCard): void {
  const synth = typeof speechSynthesis === "undefined" ? null : speechSynthesis;
  if (!synth) return;
  synth.cancel();
  const lines = card.lines.filter((line) => line.trim().length > 0);
  if (lines.length === 0) return;
  speaking.value = true;
  lines.forEach((line, index) => {
    const utterance = new SpeechSynthesisUtterance(line);
    utterance.lang = LOCALE[card.language];
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
