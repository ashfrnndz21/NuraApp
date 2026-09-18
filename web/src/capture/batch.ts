import { signal } from "@preact/signals";
import { Refused, Unreachable } from "../api/client";
import type { ReviewCardOut } from "../api/types";
import type { TraceStep } from "../ui/kit";

/** Papers from his photos (E18-01, the web's substitute for the iOS photo-library scan): many
 *  photos or PDFs picked at once, shown as a grid he confirms, then — on his one yes, and not
 *  before — each sent through the capture route (E02), one at a time, in the order picked.
 *
 *  Every paper ends with something said about it: a review card to check, the backend's own
 *  words that a page is not a health paper, a refusal in its sentence, or that it could not be
 *  sent (the network went; *Send the ones that did not go* tries again). None is dropped in silence.
 *
 *  Nothing of a photo stays on the phone: the file is only ever in memory, its picture is an
 *  object URL let go as soon as it is sent, and nothing here writes to the phone's storage. */

export type Outcome =
  | { kind: "waiting" }
  | { kind: "sending" }
  /** Read: a review card with lines to check; `checked` once he has said yes to it. */
  | { kind: "card"; card: ReviewCardOut; checked: boolean }
  /** Not a health paper: the card has no lines, and says so in its notice. */
  | { kind: "notHealth"; card: ReviewCardOut }
  | { kind: "refused"; failure: Refused }
  /** The network went before it could be sent. */
  | { kind: "notSent" };

export interface Picked {
  id: number;
  /** Its place in the grid, from 1: "Picture 3". */
  place: number;
  /** The file's own name, exactly as his phone gave it — shown so he can see what he is about
   *  to send before he says so (the report confirm step, `PapersScreen`). */
  name: string;
  pdf: boolean;
  /** The picture in the grid, while it is not sent: an object URL, or null for a PDF. */
  thumb: string | null;
  chosen: boolean;
  outcome: Outcome;
}

export interface BatchDeps {
  thumb(file: File): string | null;
  revoke(url: string): void;
  /** `onStep` fires the instant each real stage the backend just finished is known — stored,
   *  reading, what it found, and so on (`app.ingestion.review.review_artifact_stream`) —
   *  never a step this file made up (docs/design-direction.md). */
  send(file: File, onStep: (key: string, label: string) => void): Promise<ReviewCardOut>;
  /** Whether a card has lines to check (`onboarding/review.ts`). */
  readable(card: ReviewCardOut): boolean;
}

export type Stage = "empty" | "choosing" | "sending" | "done";

export function isPdf(file: Pick<File, "type" | "name">): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export class PaperBatch {
  readonly items = signal<Picked[]>([]);
  readonly stage = signal<Stage>("empty");
  /** Which of the chosen is being sent now, from 1, and how many are going. */
  readonly sending = signal<{ n: number; total: number } | null>(null);
  /** The item now being sent's own real trace, oldest step first — cleared before each item
   *  starts, so a caregiver watching the grid always sees the paper in front of it working
   *  (docs/design-direction.md 'Conversation, waiting and thinking'). Every step here is one
   *  `onStep` from the backend really gave; nothing here invents a step or a delay. */
  readonly trace = signal<TraceStep[]>([]);
  private readonly files = new Map<number, File>();
  private nextId = 1;

  constructor(private readonly deps: BatchDeps) {}

  /** The photos he picked, added to the grid, every one in to begin with. Nothing is sent. */
  pick(files: readonly File[]): void {
    const added: Picked[] = [];
    const start = this.items.value.length;
    files.forEach((file, index) => {
      const id = this.nextId++;
      this.files.set(id, file);
      added.push({ id, place: start + index + 1, name: file.name, pdf: isPdf(file), thumb: isPdf(file) ? null : this.deps.thumb(file), chosen: true, outcome: { kind: "waiting" } });
    });
    if (added.length === 0) return;
    this.items.value = [...this.items.value, ...added];
    this.stage.value = "choosing";
  }

  /** In, or left out: only while he is choosing. */
  toggle(id: number): void {
    if (this.stage.value !== "choosing") return;
    this.items.value = this.items.value.map((item) => (item.id === id ? { ...item, chosen: !item.chosen } : item));
  }

  chosen(): Picked[] {
    return this.items.value.filter((item) => item.chosen);
  }

  /** His one yes: every chosen paper not yet sent goes, one at a time, in the order picked. A
   *  paper left out is let go at once and never sent. A lost network stops here; what is left
   *  says it could not be sent, and `send` again sends only those. */
  async send(): Promise<void> {
    if (this.stage.value === "sending") return;
    for (const item of this.items.value) if (!item.chosen) this.letGo(item.id);
    this.items.value = this.items.value.filter((item) => item.chosen);
    const going = this.items.value.filter((item) => item.outcome.kind === "waiting" || item.outcome.kind === "notSent");
    if (going.length === 0) return;
    this.stage.value = "sending";
    let offline = false;
    for (const [at, item] of going.entries()) {
      if (offline) {
        this.set(item.id, { kind: "notSent" });
        continue;
      }
      const file = this.files.get(item.id);
      if (!file) continue;
      this.sending.value = { n: at + 1, total: going.length };
      this.trace.value = [];
      this.set(item.id, { kind: "sending" });
      try {
        const card = await this.deps.send(file, (key, text) => {
          // Every step already sent stays done; the new one joins in progress, so the trace
          // reads top to bottom exactly as the backend really finished them.
          this.trace.value = [...this.trace.value.map((step) => ({ ...step, done: true })), { key, text, done: false }];
        });
        this.trace.value = this.trace.value.map((step) => ({ ...step, done: true }));
        this.set(item.id, this.deps.readable(card) ? { kind: "card", card, checked: false } : { kind: "notHealth", card });
        this.letGo(item.id);
      } catch (failure) {
        if (failure instanceof Unreachable) {
          offline = true;
          this.set(item.id, { kind: "notSent" });
        } else {
          this.set(item.id, { kind: "refused", failure: failure instanceof Refused ? failure : new Refused("HttpError", 0) });
          this.letGo(item.id);
        }
      }
    }
    this.sending.value = null;
    this.trace.value = [];
    this.stage.value = "done";
  }

  /** He said yes to this paper's review card. */
  checked(cardId: string): void {
    this.items.value = this.items.value.map((item) =>
      item.outcome.kind === "card" && item.outcome.card.card_id === cardId ? { ...item, outcome: { ...item.outcome, checked: true } } : item,
    );
  }

  /** Let go of everything: every picture and every file. */
  forget(): void {
    for (const id of [...this.files.keys()]) this.letGo(id);
    for (const item of this.items.value) if (item.thumb) this.deps.revoke(item.thumb);
    this.items.value = [];
    this.stage.value = "empty";
    this.sending.value = null;
    this.trace.value = [];
  }

  /** Whether the phone still holds any of his photos: the files, or their pictures. */
  holdsPhotos(): boolean {
    return this.files.size > 0 || this.items.value.some((item) => item.thumb !== null);
  }

  private letGo(id: number): void {
    this.files.delete(id);
    const item = this.items.value.find((each) => each.id === id);
    if (item?.thumb) {
      this.deps.revoke(item.thumb);
      this.items.value = this.items.value.map((each) => (each.id === id ? { ...each, thumb: null } : each));
    }
  }

  private set(id: number, outcome: Outcome): void {
    this.items.value = this.items.value.map((item) => (item.id === id ? { ...item, outcome } : item));
  }
}
