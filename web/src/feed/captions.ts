/** A clip's captions (E09-06): the WebVTT the backend makes from the card's own verified lines,
 *  each shown for as long as it takes to say (`GET …/feed/{item}/clip/captions`). Parsed here
 *  only to show the line being said while the narration plays — the words are the backend's,
 *  never re-cut or re-worded. */

export interface Cue {
  start: number;
  end: number;
  text: string;
}

const STAMP = /^(\d{2,}):(\d{2}):(\d{2})\.(\d{3})$/;

function seconds(stamp: string): number | null {
  const found = STAMP.exec(stamp.trim());
  if (!found) return null;
  const [, h, m, s, ms] = found;
  return Number(h) * 3600 + Number(m) * 60 + Number(s) + Number(ms) / 1000;
}

/** The cues of a WebVTT file, in order. A block that is not a cue (the header, a note) is left out. */
export function parseVtt(text: string): Cue[] {
  const cues: Cue[] = [];
  for (const block of text.replace(/\r\n/g, "\n").split(/\n{2,}/)) {
    const lines = block.split("\n").filter((line) => line.trim() !== "");
    const at = lines.findIndex((line) => line.includes("-->"));
    if (at < 0) continue;
    const [from, to] = lines[at]!.split("-->");
    const start = seconds(from ?? "");
    const end = seconds((to ?? "").trim().split(/\s+/)[0] ?? "");
    const words = lines.slice(at + 1).join("\n").trim();
    if (start === null || end === null || words === "") continue;
    cues.push({ start, end, text: words });
  }
  return cues;
}

/** The line being said `elapsed` seconds into the narration; the last one once it has all been said. */
export function cueAt(cues: readonly Cue[], elapsed: number): Cue | null {
  if (cues.length === 0 || elapsed < 0) return null;
  return cues.find((cue) => elapsed >= cue.start && elapsed < cue.end) ?? (elapsed >= cues[cues.length - 1]!.end ? cues[cues.length - 1]! : null);
}

/** A Nura-made clip's own captions (`feed/model.ts` `ClipView.captions`, milliseconds from the
 *  clip's start — `app.delivery.feed.clipmaker.ClipScript.captions`, never re-timed on the
 *  client) as the same `Cue` shape the publisher clip's parsed VTT already gives `cueAt`: each
 *  line's end is the next line's start, and the last line's is the clip's own duration. */
export function cuesFromCaptions(
  captions: readonly { atMs: number; text: string }[],
  durationMs: number | null
): Cue[] {
  return captions.map((caption, index) => {
    const next = captions[index + 1];
    const endMs = next ? next.atMs : (durationMs ?? caption.atMs);
    return { start: caption.atMs / 1000, end: Math.max(endMs, caption.atMs) / 1000, text: caption.text };
  });
}
