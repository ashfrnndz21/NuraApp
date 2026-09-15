import { useRef, useState } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import { go, openMe, openTab } from "../flow";
import { tabsFor, type Tab } from "../nav";
import { speak } from "../speech/speak";
import { density, me, profile } from "../store/session";
import { fill, language, t } from "../strings";
import { AskBar, Avatar, BrandMark, TabBar } from "../ui/kit";

/** Ask or search (docs/ui-mockup-v2.html), wired: Enter or Ask opens the answer, E03's recall
 *  over his own papers. The voice button speaks one line — "tap the microphone on your
 *  keyboard, then say your question" — through the existing speech module (a voice on the
 *  phone only), and puts the cursor in the field, so the keyboard's own microphone takes his
 *  words. The page never listens itself: no recording of his voice leaves the phone, and
 *  typing is always there. */
export function AskField({ placeholder, testId }: { placeholder: string; testId?: string }): JSX.Element {
  const s = t();
  const [value, setValue] = useState("");
  const input = useRef<HTMLInputElement>(null);
  return (
    <AskBar
      value={value}
      placeholder={placeholder}
      label={s.feed.askLabel}
      onInput={setValue}
      onSubmit={() => go({ name: "ask", question: value.trim() })}
      onVoice={() => {
        speak({ lines: [s.shell.voiceSaid], language: language.value });
        input.current?.focus();
      }}
      voiceLabel={s.shell.voice}
      submitLabel={s.feed.ask}
      inputRef={input}
      testId={testId}
    />
  );
}

/** The header on every screen with the tab bar: the mark; in the caregiver's density, whose
 *  papers these are; and the signed-in person's avatar, which opens Me. */
export function ShellHeader(): JSX.Element {
  const s = t();
  const papers = profile.value;
  const caregiver = density() === "caregiver";
  return (
    <header class="shell-head">
      <BrandMark />
      {caregiver && papers && (
        <span class="whose" data-testid="whose">
          <Avatar name={papers.display_name} soft />
          <span class="whose-name">{papers.display_name}</span>
        </span>
      )}
      <button type="button" class="me-button" aria-label={s.tabs.me} aria-haspopup="dialog" onClick={openMe} data-testid="open-me">
        <Avatar name={me.value?.display_name || papers?.display_name || ""} />
        <span class="me-word" aria-hidden="true">
          {s.tabs.me}
        </span>
      </button>
    </header>
  );
}

interface ShellProps {
  /** Which tab this screen is under; null for a screen under none. */
  tab: Tab | null;
  children: ComponentChildren;
  /** The page fills the space and scrolls itself (the vertical feed's pager). */
  fill?: boolean;
  testId?: string;
  attrs?: Record<string, string | undefined>;
  /** More classes on the screen (`family` for Family's own rules). */
  extraClass?: string;
  /** False while the screen must not be left (a visit being recorded): no tab bar. */
  bar?: boolean;
  /** False on a screen that is itself the question (Ask): no second ask bar over it. */
  ask?: boolean;
}

/** Every screen with the tab bar (D1): the header, in the chief's density the ask bar — "Ask
 *  about Pa", on every one of her screens — then the page, which scrolls in its own region, and
 *  the tab bar under it in the flow. The bar reserves its own space: nothing scrolls under it
 *  and it never covers a line. */
export function Shell({ tab, children, fill: fills, testId, attrs, extraClass, bar = true, ask = true }: ShellProps): JSX.Element {
  const s = t();
  const d = density();
  const papers = profile.value;
  return (
    <main class={["shell", fills && "fill", extraClass].filter(Boolean).join(" ")} data-density={d} data-testid={testId} {...attrs}>
      <ShellHeader />
      {ask && d === "caregiver" && papers && (
        <div class="shell-ask">
          <AskField placeholder={fill(s.shell.askAbout, { name: papers.display_name })} />
        </div>
      )}
      <div class="screen shell-scroll" data-testid="shell-scroll">
        {children}
      </div>
      {bar && <TabBar tabs={tabsFor(d, s)} current={tab} onSelect={(id) => openTab(id as Tab)} label={s.appName} />}
    </main>
  );
}
