import { signal } from "@preact/signals";

/** "Hear what Dr Tan said" (E03-05): the stretch of a consult recording a line cites, on a tap.
 *
 *  The backend answers a clip with the whole recording and the stretch to play — a webm or an
 *  mp4 cannot be cut at a byte offset without a demuxer — so the phone plays it as a media
 *  fragment (`#t=start,end`), sets the start itself when the fragment is ignored, and pauses
 *  at the end. The recording is fetched once per artefact (`warm`) so a tap plays at once,
 *  inside the tap; nothing plays when a card arrives or when a clip ends. */

export interface ClipRef {
  artifact_id: string;
  start_s: number;
  end_s: number;
}

export interface ClipAudio {
  src: string;
  currentTime: number;
  play(): Promise<void>;
  pause(): void;
  addEventListener(type: "loadedmetadata" | "timeupdate" | "ended", listener: () => void): void;
}

export interface ClipDeps {
  fetchClip(artifactId: string, start: number, end: number): Promise<Blob>;
  objectUrl(blob: Blob): string;
  revoke(url: string): void;
  audio(): ClipAudio;
}

function seconds(value: number): string {
  return String(Number(value.toFixed(1)));
}

/** The media fragment for a stretch: `#t=19.8,28.9`. */
export function fragment(start: number, end: number): string {
  return `#t=${seconds(start)},${seconds(end)}`;
}

export class ClipPlayer {
  /** The key of the line whose clip is playing, or null. */
  readonly playing = signal<string | null>(null);
  private readonly urls = new Map<string, Promise<string>>();
  private current: ClipAudio | null = null;

  constructor(private readonly deps: ClipDeps) {}

  /** Fetch, never play, the recording a clip is in. */
  warm(clip: ClipRef): void {
    this.url(clip).catch(() => undefined);
  }

  /** Play exactly this stretch. Call from a tap and from nowhere else. */
  async play(key: string, clip: ClipRef): Promise<void> {
    this.stop();
    this.playing.value = key;
    const audio = this.deps.audio();
    this.current = audio;
    const url = await this.url(clip);
    if (this.current !== audio) return; // another tap came first
    audio.addEventListener("loadedmetadata", () => {
      if (Math.abs(audio.currentTime - clip.start_s) > 0.25) audio.currentTime = clip.start_s;
    });
    audio.addEventListener("timeupdate", () => {
      if (audio.currentTime >= clip.end_s) this.finish(audio);
    });
    audio.addEventListener("ended", () => this.finish(audio));
    audio.src = url + fragment(clip.start_s, clip.end_s);
    try {
      await audio.play();
    } catch (failure) {
      this.finish(audio);
      throw failure;
    }
  }

  stop(): void {
    this.current?.pause();
    this.current = null;
    this.playing.value = null;
  }

  /** Leave: stop, and let go of every recording fetched. */
  forget(): void {
    this.stop();
    for (const url of this.urls.values()) void url.then((each) => this.deps.revoke(each)).catch(() => undefined);
    this.urls.clear();
  }

  private url(clip: ClipRef): Promise<string> {
    let found = this.urls.get(clip.artifact_id);
    if (!found) {
      found = this.deps.fetchClip(clip.artifact_id, clip.start_s, clip.end_s).then((blob) => this.deps.objectUrl(blob));
      this.urls.set(clip.artifact_id, found);
      found.catch(() => this.urls.delete(clip.artifact_id));
    }
    return found;
  }

  private finish(audio: ClipAudio): void {
    if (this.current !== audio) return;
    audio.pause();
    this.current = null;
    this.playing.value = null;
  }
}

/** The browser's audio element and object URLs, around the API's clip route. */
export function browserClipDeps(fetchClip: ClipDeps["fetchClip"]): ClipDeps {
  return {
    fetchClip,
    objectUrl: (blob) => URL.createObjectURL(blob),
    revoke: (url) => URL.revokeObjectURL(url),
    audio: () => new Audio() as unknown as ClipAudio,
  };
}
