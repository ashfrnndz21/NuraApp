import { useEffect, useState } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import type { ProfileOut } from "../../api/types";
import { go, openTab, type FamilyPart } from "../../flow";
import { density, profile, token } from "../../store/session";
import { fill, LOCALE, language, t } from "../../strings";
import { Header, Notice, TabBar } from "../../ui/components";

/** What every Family part needs: whose papers, as whom, how dense, in which language. */
export interface Here {
  bearer: string;
  papers: ProfileOut;
  /** The owner reads "your"; anyone else reads his name. */
  owner: boolean;
  /** The patient density: one thing per screen, 56px targets. */
  patient: boolean;
  lang: string;
  locale: string;
}

export function useHere(): Here | null {
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) return null;
  return {
    bearer,
    papers,
    owner: papers.standing === "owner",
    patient: density() === "patient",
    lang: language.value,
    locale: LOCALE[language.value],
  };
}

/** A title said to the owner as "your", to anyone else with his name. */
export function whose(here: Here, self: string, other: string): string {
  return here.owner ? self : fill(other, { name: here.papers.display_name });
}

/** One Family part: the header with its way back, the part, the tab bar. */
export function FamilyPage({ title, part, children }: { title: string; part: FamilyPart; children: ComponentChildren }): JSX.Element {
  return (
    <main class="screen family" data-density={density()} data-testid={`family-${part}`}>
      <Header title={title} onBack={part === "home" ? undefined : () => go({ name: "family", part: "home" })} />
      {children}
      <TabBar current="family" onSelect={openTab} />
    </main>
  );
}

/** Lines the backend wrote, shown as they are, one paragraph each. */
export function Lines({ lines, testId }: { lines: readonly string[]; testId?: string }): JSX.Element {
  return (
    <div class="lines" data-testid={testId}>
      {lines.map((line, at) => (
        <p key={at}>{line}</p>
      ))}
    </div>
  );
}

/** A read from the backend: its answer, or the refusal it gave, said in its words. */
export function useRead<T>(read: (() => Promise<T>) | null, deps: readonly unknown[]): { value: T | null; error: unknown; reload: () => Promise<void> } {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reload = async () => {
    if (!read) return;
    try {
      setValue(await read());
      setError(null);
    } catch (failure) {
      setValue(null);
      setError(failure);
    }
  };
  useEffect(() => {
    void reload();
  }, deps);
  return { value, error, reload };
}

/** One action at a time: busy while it runs, its refusal kept to be said where it happened. */
export function useAct(): { busy: boolean; error: unknown; at: string | null; act: (where: string, work: () => Promise<void>) => Promise<void>; clear: () => void } {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [at, setAt] = useState<string | null>(null);
  const act = async (where: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setAt(where);
    try {
      await work();
      setAt(null);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, at, act, clear: () => (setError(null), setAt(null)) };
}

/** The refusal an action met, said beside the thing that was tapped. */
export function NoticeAt({ act, where }: { act: { error: unknown; at: string | null }; where: string }): JSX.Element | null {
  return act.at === where ? <Notice error={act.error} /> : null;
}

export function s() {
  return t().family;
}
