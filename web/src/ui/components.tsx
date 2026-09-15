import type { ComponentChildren, JSX } from "preact";
import { useEffect, useId, useRef } from "preact/hooks";
import { voice } from "../player/voice";
import { language, refusalLines, t } from "../strings";
import { Refused, Unreachable } from "../api/client";
import { demo } from "../store/deployment";
import { PlayerControls } from "./Player";

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

/** The spoken twin of a card. Audio starts here and nowhere else: the tap opens the one
 *  player (E15-07) under the button — Play / Pause, his speed, the line being said — and
 *  leaving the screen stops it. */
export function Hear({ lines }: { lines: readonly string[] }): JSX.Element {
  const key = `hear:${useId()}`;
  const open = voice.key.value === key;
  useEffect(() => () => voice.leave(key), [key]);
  return (
    <>
      <Pill
        quiet
        onClick={() => void voice.play({ kind: "speech", key, lines, language: language.value }).catch(() => undefined)}
        label={`${t().today.hear}: ${lines[0] ?? ""}`}
        testId="hear"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 10v4h3l4 4V6L7 10H4z" />
          <path d="M15 9a4 4 0 0 1 0 6" />
          <path d="M17.5 6.5a8 8 0 0 1 0 11" />
        </svg>
        {t().today.hear}
      </Pill>
      {open && <PlayerControls />}
    </>
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
        ? refusalLines(error.refusal, language.value)
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

export function TabBar({ current, onSelect }: { current: "today" | "family" | "me"; onSelect: (tab: "today" | "family" | "me") => void }): JSX.Element {
  const s = t();
  const tabs = [
    ["today", s.tabs.today],
    ["family", s.tabs.family],
    ["me", s.tabs.me],
  ] as const;
  // The screen keeps room under its last line for the bar as tall as it is: at a large text
  // size a label can take two lines, and a fixed allowance would leave a line under the bar.
  const bar = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = bar.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const measure = () => document.documentElement.style.setProperty("--tabbar-h", `${Math.ceil(element.getBoundingClientRect().height)}px`);
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(element);
    return () => watch.disconnect();
  }, []);
  return (
    <nav class="tabbar" aria-label={s.appName} ref={bar}>
      {tabs.map(([tab, label]) => (
        <button key={tab} type="button" aria-current={current === tab ? "page" : undefined} onClick={() => onSelect(tab)} data-testid={`tab-${tab}`}>
          {label}
        </button>
      ))}
    </nav>
  );
}

/** On a demo deployment (ADR 0008), first on every screen: what this is, in the person's
 *  language, and that real health information does not belong in it. */
/** The demo banner (ADR 0008). Its headline is pinned to the top of every screen; the lines
 *  under it sit above the screen and scroll away with it, so that at a large text size the part
 *  that never moves stays one headline tall and is never drawn over his lines (E15-04). */
export function DemoBanner(): JSX.Element | null {
  if (!demo.value) return null;
  const s = t().demo;
  return (
    <>
      <aside class="demo-banner" role="note" data-testid="demo-banner">
        <strong>{s.banner}</strong>
      </aside>
      <div class="demo-lines" data-testid="demo-lines">
        {s.lines.map((line, index) => (
          <span key={index}>{line}</span>
        ))}
      </div>
    </>
  );
}
