import { signal } from "@preact/signals";
import { Refused } from "../api/client";
import type { Language } from "../strings";

/** The one player (E15-07): everything Nura says out loud goes through here — a card's spoken
 *  twin on the phone's own voice, a card's pre-rendered voice (E11), and a stretch of a visit's
 *  recording (E03-05, a clip).
 *
 *  It starts only from a tap (`play`), never when a card arrives and never when another voice
 *  ends. One thing sounds at a time: a new tap stops the last. It pauses and goes on from where
 *  it was (`toggle`), and plays at the speed he chose (`setRate`), which the phone remembers.
 *  `line` is the transcript: the line being said, shown under the controls.
 *
 *  A clip is the whole recording played as a media fragment (`#t=start,end`) — a webm or an mp4
 *  cannot be cut at a byte offset without a demuxer — started at its start by hand when the
 *  fragment is ignored and paused at its end. The recording is fetched once per artefact. A
 *  recording this key may not hear (a 403: `OnlyTheFamilyHears`) is remembered in `refused`, so
 *  the line shows the refusal's sentence and no player. */

export const SPEEDS = [0.75, 1, 1.25] as const;
export type Speed = (typeof SPEEDS)[number];
export const USUAL_SPEED: Speed = 1;

export function isSpeed(value: unknown): value is Speed {
  return typeof value === "number" && (SPEEDS as readonly number[]).includes(value);
}

/** The stretch of a consult recording a line cites. */
export interface ClipRef {
  artifact_id: string;
  start_s: number;
  end_s: number;
}

function seconds(value: number): string {
  return String(Number(value.toFixed(1)));
}

/** The media fragment for a stretch: `#t=19.8,28.9`. */
export function fragment(start: number, end: number): string {
  return `#t=${seconds(start)},${seconds(end)}`;
}

export type Source =
  /** A card's spoken twin, read by a voice that runs on the phone. */
  | { kind: "speech"; key: string; lines: readonly string[]; language: Language }
  /** A card's pre-rendered voice: bytes the backend made (E11). */
  | { kind: "audio"; key: string; blob: Blob; lines: readonly string[] }
  /** A stretch of a visit's recording, with the line it is the words of. */
  | { kind: "clip"; key: string; clip: ClipRef; lines: readonly string[] };

export type Status = "idle" | "loading" | "playing" | "paused";

/** One part of a story said in parts (the medication story, E04-06): its own voice note when
 *  the backend has one (`audio`), else its lines on the phone's own voice. */
export interface Part {
  lines: readonly string[];
  language: Language;
  audio: Blob | null;
}

/** As much of an audio element as the player uses. */
export interface MediaLike {
  src: string;
  currentTime: number;
  playbackRate: number;
  play(): Promise<void>;
  pause(): void;
  addEventListener(type: "loadedmetadata" | "timeupdate" | "ended", listener: () => void): void;
}

export interface SpeechEvents {
  /** The line at this index (of the lines handed to `say`) has started. */
  onLine(index: number): void;
  /** The last line has been said. */
  onEnd(): void;
}

/** The phone's own voice. `say` answers false when the phone has no voice of its own for the
 *  language: then nothing is said (a network voice would send the words out of the region). */
export interface SpeechLike {
  say(lines: readonly string[], language: Language, rate: number, events: SpeechEvents): boolean;
  pause(): void;
  resume(): void;
  cancel(): void;
}

export interface PlayerDeps {
  media(): MediaLike;
  objectUrl(blob: Blob): string;
  revoke(url: string): void;
  fetchClip(artifactId: string, start: number, end: number): Promise<Blob>;
  speech: SpeechLike;
  /** Remember his speed on this phone. */
  saveRate(rate: Speed): unknown;
}

export class Player {
  /** Which source the controls belong to, or null: nothing is open. */
  readonly key = signal<string | null>(null);
  readonly status = signal<Status>("idle");
  /** The transcript line: the line being said now. */
  readonly line = signal<string | null>(null);
  readonly rate = signal<Speed>(USUAL_SPEED);
  /** Recordings this key may not hear, by artefact id: the refusal's class name. */
  readonly refused = signal<ReadonlyMap<string, string>>(new Map());
  /** A story said in parts has another part after the one heard: *Next part* plays it. */
  readonly more = signal(false);

  private source: Source | null = null;
  private media: MediaLike | null = null;
  private mediaUrl: string | null = null;
  /** The line of a spoken twin being said, and whether a pause needs it said again (a new
   *  speed is taken by the phone's voice only when a line starts). */
  private spoken = 0;
  private restart = false;
  /** Guards: a tap that came later wins over one still loading, and a voice cancelled does
   *  not report its end. */
  private turn = 0;
  private said = 0;
  private readonly recordings = new Map<string, Promise<string>>();
  /** The story being said part by part, and the part it is on. */
  private sequence: { key: string; parts: readonly Part[]; at: number } | null = null;

  constructor(private readonly deps: PlayerDeps) {}

  /** A story in parts, from its first part: each part plays on its own tap and stops at its
   *  end; nothing starts the next part but *Next part*. Call from a tap and from nowhere else. */
  playParts(key: string, parts: readonly Part[]): Promise<void> {
    this.sequence = { key, parts, at: 0 };
    return this.playPart();
  }

  /** *Next part*: the part after the one heard, on this tap. */
  nextPart(): Promise<void> {
    const sequence = this.sequence;
    if (!sequence || sequence.at >= sequence.parts.length - 1) return Promise.resolve();
    sequence.at += 1;
    return this.playPart();
  }

  private playPart(): Promise<void> {
    const sequence = this.sequence;
    const part = sequence?.parts[sequence.at];
    if (!sequence || !part) return Promise.resolve();
    const source: Source = part.audio
      ? { kind: "audio", key: sequence.key, blob: part.audio, lines: part.lines }
      : { kind: "speech", key: sequence.key, lines: part.lines, language: part.language };
    const playing = this.play(source, true);
    this.more.value = sequence.at < sequence.parts.length - 1;
    return playing;
  }

  /** Play this, from its start. Call from a tap and from nowhere else. A clip this key may
   *  not hear is not played: its artefact goes into `refused`. Anything else that goes wrong
   *  is thrown for the screen to say. */
  async play(source: Source, inSequence = false): Promise<void> {
    if (!inSequence) {
      this.sequence = null;
      this.more.value = false;
    }
    this.halt();
    const turn = ++this.turn;
    const lines = source.lines.filter((line) => line.trim().length > 0);
    this.source = { ...source, lines };
    this.key.value = source.key;
    this.spoken = 0;
    this.restart = false;
    this.line.value = lines[0] ?? null;
    if (source.kind === "speech") {
      this.speakFrom(0);
      return;
    }
    if (source.kind === "audio") {
      const url = this.deps.objectUrl(source.blob);
      this.mediaUrl = url;
      this.line.value = lines.join(" ") || null;
      return this.startMedia(url, null);
    }
    if (this.refused.value.has(source.clip.artifact_id)) {
      this.clear();
      return;
    }
    this.status.value = "loading";
    let url: string;
    try {
      url = await this.recording(source.clip);
    } catch (failure) {
      if (turn !== this.turn) return;
      this.clear();
      if (failure instanceof Refused && failure.status === 403) {
        this.refuse(source.clip.artifact_id, failure.refusal);
        return;
      }
      throw failure;
    }
    if (turn !== this.turn) return; // another tap came first
    return this.startMedia(url + fragment(source.clip.start_s, source.clip.end_s), source.clip);
  }

  /** Pause, or go on from where it was; after the end, play it again from the start. */
  toggle(): void {
    const source = this.source;
    if (!source) return;
    const status = this.status.value;
    if (status === "playing") {
      if (source.kind === "speech") this.deps.speech.pause();
      else this.media?.pause();
      this.status.value = "paused";
      return;
    }
    if (status === "paused") {
      if (source.kind === "speech") {
        if (this.restart) this.speakFrom(this.spoken);
        else {
          this.deps.speech.resume();
          this.status.value = "playing";
        }
        return;
      }
      const media = this.media;
      if (!media) return;
      this.status.value = "playing";
      media.play().catch(() => {
        if (this.media === media) this.status.value = "paused";
      });
      return;
    }
    // Play after the end: this again from its start — within a story, this part, never the next.
    if (status === "idle") void this.play(source, this.sequence !== null).catch(() => undefined);
  }

  /** His speed, kept on the phone; the voice playing now takes it at once. */
  setRate(rate: Speed): void {
    if (this.rate.value === rate) return;
    this.rate.value = rate;
    void this.deps.saveRate(rate);
    if (this.media) this.media.playbackRate = rate;
    if (this.source?.kind === "speech") {
      if (this.status.value === "playing") {
        this.deps.speech.cancel();
        this.speakFrom(this.spoken);
      } else if (this.status.value === "paused") {
        this.deps.speech.cancel();
        this.restart = true;
      }
    }
  }

  /** Stop, and close the controls. */
  stop(): void {
    this.turn++;
    this.sequence = null;
    this.more.value = false;
    this.halt();
    this.clear();
  }

  /** The source at `key` has left the screen: its voice stops. Any other plays on. */
  leave(key: string): void {
    if (this.key.value === key) this.stop();
  }

  /** Fetch, never play, the recording a clip is in. */
  warm(clip: ClipRef): void {
    this.recording(clip).catch((failure: unknown) => {
      if (failure instanceof Refused && failure.status === 403) this.refuse(clip.artifact_id, failure.refusal);
    });
  }

  /** Stop, and let go of every recording fetched and every refusal remembered: a signed-out
   *  phone or another person's papers start from nothing. */
  forget(): void {
    this.stop();
    for (const url of this.recordings.values()) void url.then((each) => this.deps.revoke(each)).catch(() => undefined);
    this.recordings.clear();
    this.refused.value = new Map();
  }

  private speakFrom(from: number): void {
    const source = this.source;
    if (!source || source.kind !== "speech") return;
    const run = ++this.said;
    this.restart = false;
    const spoken = this.deps.speech.say(source.lines.slice(from), source.language, this.rate.value, {
      onLine: (index) => {
        if (run !== this.said) return;
        this.spoken = from + index;
        this.line.value = source.lines[from + index] ?? null;
      },
      onEnd: () => {
        if (run !== this.said) return;
        this.status.value = "idle";
        this.spoken = 0;
        this.line.value = source.lines[0] ?? null;
      },
    });
    if (!spoken) {
      // No voice on this phone for the language: nothing is said, and no player shows.
      this.clear();
      return;
    }
    this.status.value = "playing";
  }

  private async startMedia(src: string, clip: ClipRef | null): Promise<void> {
    const media = this.deps.media();
    this.media = media;
    media.playbackRate = this.rate.value;
    if (clip) {
      media.addEventListener("loadedmetadata", () => {
        if (Math.abs(media.currentTime - clip.start_s) > 0.25) media.currentTime = clip.start_s;
        media.playbackRate = this.rate.value;
      });
      media.addEventListener("timeupdate", () => {
        if (media.currentTime >= clip.end_s) this.ended(media);
      });
    }
    media.addEventListener("ended", () => this.ended(media));
    media.src = src;
    this.status.value = "playing";
    try {
      await media.play();
    } catch (failure) {
      if (this.media !== media) return;
      this.halt();
      this.clear();
      throw failure;
    }
  }

  private ended(media: MediaLike): void {
    if (this.media !== media) return;
    media.pause();
    this.media = null;
    this.status.value = "idle";
    const lines = this.source?.lines ?? [];
    this.line.value = this.source?.kind === "audio" ? lines.join(" ") || null : (lines[0] ?? null);
  }

  private recording(clip: ClipRef): Promise<string> {
    let found = this.recordings.get(clip.artifact_id);
    if (!found) {
      found = this.deps.fetchClip(clip.artifact_id, clip.start_s, clip.end_s).then((blob) => this.deps.objectUrl(blob));
      this.recordings.set(clip.artifact_id, found);
      found.catch(() => this.recordings.delete(clip.artifact_id));
    }
    return found;
  }

  private refuse(artifactId: string, refusal: string): void {
    const next = new Map(this.refused.value);
    next.set(artifactId, refusal);
    this.refused.value = next;
  }

  /** Silence whatever sounds, keeping the controls. */
  private halt(): void {
    this.said++;
    this.deps.speech.cancel();
    if (this.media) {
      this.media.pause();
      this.media = null;
    }
    if (this.mediaUrl) {
      this.deps.revoke(this.mediaUrl);
      this.mediaUrl = null;
    }
  }

  private clear(): void {
    this.source = null;
    this.key.value = null;
    this.status.value = "idle";
    this.line.value = null;
  }
}
