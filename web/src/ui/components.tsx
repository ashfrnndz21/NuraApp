import type { ComponentChildren, JSX } from "preact";
import { speak, type SpokenCard } from "../speech/speak";
import { language, refusalLines, t } from "../strings";
import { Refused, Unreachable } from "../api/client";
import { go } from "../flow";

/** The few pieces every screen is made of. Decisions sit on paper; the rest may be glass. */

export function Brand(): JSX.Element {
  return (
    <div class="brand" aria-hidden="true">
      <svg viewBox="0 0 200 200">
        <defs>
          <linearGradient id="nuraAura" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#B9A6E0" />
            <stop offset="1" stop-color="#F0C9DA" />
          </linearGradient>
        </defs>
        <path d="M86 166C44 138 22 102 36 74c12-24 48-22 64 4" fill="none" stroke="#4E3A78" stroke-width="20" stroke-linecap="round" />
        <path d="M114 166c42-28 64-64 50-92-12-24-48-22-64 4" fill="none" stroke="url(#nuraAura)" stroke-width="20" stroke-linecap="round" />
        <circle cx="100" cy="112" r="12" fill="#4E3A78" />
      </svg>
      {t().appName}
    </div>
  );
}

interface TileProps {
  paper?: boolean;
  glass?: boolean;
  sheet?: boolean;
  settled?: boolean;
  children: ComponentChildren;
  role?: "alert" | "status";
  testId?: string;
}

export function Tile({ paper, glass, sheet, settled, children, role, testId }: TileProps): JSX.Element {
  const classes = ["tile", paper && "paper", glass && "glass", sheet && "sheet", settled && "settled"]
    .filter(Boolean)
    .join(" ");
  return (
    <section class={classes} role={role} data-testid={testId}>
      {children}
    </section>
  );
}

interface PillProps {
  onClick: () => void;
  children: ComponentChildren;
  plum?: boolean;
  coral?: boolean;
  done?: boolean;
  quiet?: boolean;
  disabled?: boolean;
  label?: string;
  testId?: string;
  /** The answer already given, among several choices: a plum outline, not a fill. */
  chosen?: boolean;
  /** A toggle's state, for the screen reader and the answered colours. */
  pressed?: boolean;
  extraClass?: string;
}

export function Pill({ onClick, children, plum, coral, done, quiet, disabled, label, testId, chosen, pressed, extraClass }: PillProps): JSX.Element {
  const classes = ["pill", plum && "plum", coral && "coral", done && "done", quiet && "quiet", chosen && "chosen", extraClass]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      type="button"
      class={classes}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={pressed ?? (chosen === undefined ? undefined : chosen)}
      data-testid={testId}
    >
      {children}
    </button>
  );
}

/** The spoken twin of a card. Audio starts here and nowhere else. */
export function Hear({ lines }: { lines: readonly string[] }): JSX.Element {
  const card: SpokenCard = { lines, language: language.value };
  return (
    <Pill quiet onClick={() => speak(card)} label={`${t().today.hear}: ${lines[0] ?? ""}`} testId="hear">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 10v4h3l4 4V6L7 10H4z" />
        <path d="M15 9a4 4 0 0 1 0 6" />
        <path d="M17.5 6.5a8 8 0 0 1 0 11" />
      </svg>
      {t().today.hear}
    </Pill>
  );
}

interface CardProps {
  title?: string;
  lines: readonly string[];
  provenance?: string;
  paper?: boolean;
  action?: ComponentChildren;
  hear?: boolean;
  /** The backend's boundary lines, shown under the card's own lines (E16-01). */
  boundary?: readonly string[];
  /** The spoken twin when the backend wrote one (a feed card's `voice`); else every line shown. */
  spoken?: readonly string[];
  settled?: boolean;
  testId?: string;
}

/** Card grammar: one title, a few whole lines, its source, one action, and its spoken twin. */
export function Card({ title, lines, provenance, paper = true, action, hear = true, boundary = [], spoken: voice, settled, testId }: CardProps): JSX.Element {
  const spoken = voice ?? [title, ...lines, ...boundary].filter((line): line is string => Boolean(line));
  return (
    <Tile paper={paper} glass={!paper} settled={settled} testId={testId}>
      {title && <h2 class="title">{title}</h2>}
      <div class="lines">
        {lines.map((line, index) => (
          <p key={index}>{line}</p>
        ))}
      </div>
      {boundary.length > 0 && (
        <div class="lines boundary" data-testid="boundary">
          {boundary.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      )}
      {provenance && <p class="provenance">{provenance}</p>}
      {action}
      {hear && <Hear lines={spoken} />}
    </Tile>
  );
}

/** A refusal said on a screen other than the one that met it, by its class name. */
export function RefusalNotice({ refusal }: { refusal: string | undefined }): JSX.Element | null {
  if (!refusal) return null;
  return (
    <Tile paper role="alert" testId="notice">
      {refusalLines(refusal).map((line, index) => (
        <p key={index}>{line}</p>
      ))}
    </Tile>
  );
}

/** What happened and what to do, in one plain sentence — never the class, never an id. */
export function Notice({ error }: { error: unknown }): JSX.Element | null {
  if (!error) return null;
  const lines =
    error instanceof Unreachable
      ? [t().errors.network]
      : error instanceof Refused
        ? refusalLines(error.refusal)
        : refusalLines(undefined);
  return (
    <Tile paper role="alert" testId="notice">
      {lines.map((line, index) => (
        <p key={index}>{line}</p>
      ))}
    </Tile>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onInput: (value: string) => void;
  type?: string;
  inputMode?: JSX.HTMLAttributes<HTMLInputElement>["inputMode"];
  autoComplete?: string;
  big?: boolean;
  name: string;
  maxLength?: number;
}

export function Field({ label, value, onInput, type = "text", inputMode, autoComplete, big, name, maxLength }: FieldProps): JSX.Element {
  return (
    <label style="display:flex;flex-direction:column;gap:6px">
      <span class="label">{label}</span>
      <input
        class={big ? "field big" : "field"}
        name={name}
        type={type}
        value={value}
        inputMode={inputMode}
        autoComplete={autoComplete}
        maxLength={maxLength}
        onInput={(event) => onInput((event.target as HTMLInputElement).value)}
      />
    </label>
  );
}

export function Header({ title, onBack }: { title: string; onBack?: () => void }): JSX.Element {
  return (
    <header style="display:flex;flex-direction:column;gap:12px">
      <Brand />
      <h1 class="title">{title}</h1>
      {onBack && (
        <Pill quiet onClick={onBack}>
          {t().signIn.back}
        </Pill>
      )}
    </header>
  );
}

/** The nav entries, in the order Today · Feed · Record · Family · Me; each one screen away.
 *  (The Feed opens from Today's "See more for you", and the Family entry is W6's.) */
export type Tab = "today" | "record" | "me";
const TABS: readonly Tab[] = ["today", "record", "me"];

export function TabBar({ current }: { current: Tab }): JSX.Element {
  const s = t();
  const open = (tab: Tab) => go(tab === "record" ? { name: "record", at: { name: "hub" } } : { name: tab });
  return (
    <nav class="tabbar" aria-label={s.appName}>
      {TABS.map((tab) => (
        <button key={tab} type="button" aria-current={current === tab ? "page" : undefined} onClick={() => open(tab)} data-testid={`tab-${tab}`}>
          {s.tabs[tab]}
        </button>
      ))}
    </nav>
  );
}
