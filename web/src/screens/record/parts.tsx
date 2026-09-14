import { signal } from "@preact/signals";
import { useEffect, useState } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import { go } from "../../flow";
import type { RecordAt } from "../../record/places";
import { density, profile, token } from "../../store/session";
import { fill, language, LOCALE, t } from "../../strings";
import { dateLine } from "../../today/model";
import { Header, Pill, TabBar } from "../../ui/components";

/** What every Record screen is made of. */

export function toRecord(at: RecordAt): void {
  go({ name: "record", at });
  if (typeof window !== "undefined") window.scrollTo(0, 0);
}

/** Whose papers, under which token. A Record screen is only ever shown signed in. */
export function session(): { bearer: string; profileId: string } {
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) throw new Error("no session");
  return { bearer, profileId: papers.profile_id };
}

/** The reads a Record screen is waiting on: while any is, the screen says it is busy
 *  (`aria-busy`), so a screen reader waits for the lines and nothing moves under a finger. A
 *  read counts from the screen's first render — before it starts — so no frame says "ready"
 *  with the lines still to come. `reading` only makes the frame render again when it changes. */
const inFlight = new Set<object>();
const reading = signal(0);

function waiting(read: object, on: boolean): void {
  if (on) inFlight.add(read);
  else inFlight.delete(read);
  reading.value = inFlight.size;
}

/** One read on the way in (and again when `deps` change); a refusal is kept to be said. */
export function useRead<T>(read: () => Promise<T>, deps: readonly unknown[]): { data: T | null; error: unknown; reload: () => Promise<void> } {
  const [id] = useState(() => {
    const mine = {};
    inFlight.add(mine);
    return mine;
  });
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reload = async () => {
    setError(null);
    waiting(id, true);
    try {
      setData(await read());
    } catch (failure) {
      setError(failure);
    } finally {
      waiting(id, false);
    }
  };
  useEffect(() => {
    void reload();
    return () => waiting(id, false);
  }, deps);
  return { data, error, reload };
}

/** One line the next Record screen says once, then forgets ("Nura added it to your list."). */
export const recordNote = signal<string[] | null>(null);

export function takeNote(): string[] | null {
  const note = recordNote.peek();
  recordNote.value = null;
  return note;
}

/** A day in his words, from an instant or a day the backend sent. */
export function useDateOf(): (iso: string) => string {
  const locale = LOCALE[language.value];
  return (iso: string) => dateLine(new Date(iso), locale);
}

export function upperFirst(text: string): string {
  return text.length > 0 ? text[0]!.toUpperCase() + text.slice(1) : text;
}

interface FrameProps {
  title: string;
  /** Where "Back to your papers" goes; none on the Record's own first screen. */
  back?: RecordAt;
  testId: string;
  children: ComponentChildren;
}

/** A Record screen: the title, one thing (or the list, in her density), the way back, the nav. */
export function RecordFrame({ title, back, testId, children }: FrameProps): JSX.Element {
  const s = t();
  return (
    <main class="screen record" data-density={density()} data-testid={testId} aria-busy={reading.value >= 0 && inFlight.size > 0 ? "true" : "false"}>
      <Header title={title} />
      {children}
      {back && (
        <Pill quiet onClick={() => toRecord(back)} testId="record-back">
          {s.record.back}
        </Pill>
      )}
      <TabBar current="record" />
    </main>
  );
}

interface PagedProps<T> {
  items: readonly T[];
  render: (item: T, index: number) => JSX.Element;
  /** More to read past the last one (the timeline's cursor): read, then show the next. */
  more?: (() => Promise<void>) | null;
  start?: number;
}

/** A list, one item a screen in his density ("This is 1 of 3." and Next), whole in hers. */
export function Paged<T>({ items, render, more, start = 0 }: PagedProps<T>): JSX.Element {
  const s = t();
  const [index, setIndex] = useState(start);
  const [busy, setBusy] = useState(false);
  if (density() !== "patient") return <>{items.map((item, at) => render(item, at))}</>;
  if (items.length === 0) return <></>;
  const at = Math.max(0, Math.min(index, items.length - 1));
  const last = at === items.length - 1;
  const next = async () => {
    if (!last) return setIndex(at + 1);
    if (!more) return;
    setBusy(true);
    try {
      await more();
      setIndex(at + 1);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {render(items[at]!, at)}
      <p class="caption" data-testid="line-of">
        {fill(s.onboarding.readBack.lineOf, { n: at + 1, total: items.length })}
      </p>
      {(!last || more) && (
        <Pill onClick={() => void next()} disabled={busy} testId="next">
          {s.onboarding.next}
        </Pill>
      )}
      {at > 0 && (
        <Pill quiet onClick={() => setIndex(at - 1)} testId="previous">
          {s.onboarding.back}
        </Pill>
      )}
    </>
  );
}
