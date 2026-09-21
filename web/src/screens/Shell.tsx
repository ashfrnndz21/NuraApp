import { useRef, useState } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import { go, openMe, openTab } from "../flow";
import { tabsFor, type Tab } from "../nav";
import { speak } from "../speech/speak";
import { emergencyOnly } from "../offline/emergencyCache";
import { density, profile } from "../store/session";
import { fill, language, t } from "../strings";
import { AskBar, Icon, PaperTile, Sheet, TabBar, Wordmark, type IconName } from "../ui/kit";
import { ProfileSwitcher } from "./Switcher";

/** Ask or search (docs/ui-mockup-v2.html), wired: Enter or Ask opens the answer, E03's recall
 *  over his own papers. The voice button speaks two lines — "Press the microphone on your
 *  keyboard", then "Then say your question." — through the existing speech module (a voice on the
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
        speak({ lines: [s.shell.voiceSaid1, s.shell.voiceSaid2], language: language.value });
        input.current?.focus();
      }}
      voiceLabel={s.shell.voice}
      submitLabel={s.feed.ask}
      inputRef={input}
      testId={testId}
    />
  );
}

/** The bell (docs/design/nura-concept-board.html): what is new for him — the vertical feed's
 *  own cards, and the weekly report's own row, added here so a fresh report is never only one
 *  tap he has to already know to make on Health. A sheet, not a second screen: it opens
 *  nothing itself, only names where to go next. */
export function BellButton(): JSX.Element {
  const s = t();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" class="head-button" aria-label={s.shell.bell} aria-haspopup="dialog" onClick={() => setOpen(true)} data-testid="bell">
        <Icon name="bell" />
      </button>
      <Sheet title={s.shell.bell} open={open} onClose={() => setOpen(false)} closeLabel={s.shell.close} testId="bell-sheet">
        <PaperTile testId="bell-rows">
          <nav class="place-rows" aria-label={s.shell.bell}>
            <button
              type="button"
              class="place-row"
              onClick={() => {
                setOpen(false);
                go({ name: "feed" });
              }}
              data-testid="bell-feed"
            >
              <Icon name="today" />
              <span class="place-word">{s.shell.bellFeed}</span>
              <Icon name="chevron" />
            </button>
            <button
              type="button"
              class="place-row"
              onClick={() => {
                setOpen(false);
                go({ name: "insights" });
              }}
              data-testid="bell-insights"
            >
              <Icon name="trends" />
              <span class="place-word">{s.shell.bellInsights}</span>
              <Icon name="chevron" />
            </button>
          </nav>
        </PaperTile>
      </Sheet>
    </>
  );
}

/** The header on every screen with the tab bar (docs/design-direction.md, Reference B's top
 *  bar): the menu, which opens Me; the serif wordmark; then the switcher, which names whose
 *  papers are open and opens every other set this person can; and the bell, which opens what is
 *  new for him — the cards made for him, the same place "See more for you" opens.
 *
 *  The switcher is on every screen in both densities, not only the caregiver's: one app and one
 *  account (docs/product-reset.md §6), so whose record the app is in is always on screen and
 *  never inferred from how the screen looks. */
export function ShellHeader(): JSX.Element {
  const s = t();
  const papers = profile.value;
  // A key to the emergency card alone opens nothing else, so it has no bell to ring.
  const bell = papers !== null && !emergencyOnly(papers);
  return (
    <header class="shell-head">
      <span class="head-start">
        <button type="button" class="head-button" aria-label={s.tabs.me} aria-haspopup="dialog" onClick={openMe} data-testid="open-me">
          <Icon name="menu" />
        </button>
      </span>
      <span class="head-mark">
        <Wordmark name={s.appName} mark={false} />
      </span>
      <span class="head-end">{bell && <BellButton />}</span>
      {/* Whose papers are open, on every screen, just under the bar. */}
      {papers && (
        <span class="head-whose">
          <ProfileSwitcher />
        </span>
      )}
    </header>
  );
}

/** The board's own per-screen top bars (`docs/design/nura-concept-board.html`), owner's
 *  decision 2026-09-17: these replace the global menu+wordmark+switcher+bell header on a
 *  tab's own root screen — the five screens the board actually draws. "board": back · centred
 *  title · one action icon (Health, Connect, Services — the board's screens 3–5); "home": the
 *  board's own screen 2, menu (still opening Me, the one entry point until every caller of the
 *  sheet moves) · wordmark · bell (notifications, per the board), with no switcher — whose
 *  papers are open lives on the Profile tab's own row (`ProfileNav`'s `switch-profile`) now,
 *  not in every screen's header. "plain": Profile's own screen 6 — a bare title, no back, no
 *  icon. Nested screens under a tab (Family, the Record, Emergency, Feed, …) are not on the
 *  board at all, so they are untouched: they keep the old global `ShellHeader`, switcher
 *  included, because only the five tab-root screens themselves pass `topBar`. */
export type TopBarSpec =
  | { variant: "board"; title: string; back?: boolean; action?: { icon: IconName; label: string; onClick: () => void } }
  | { variant: "home" }
  | { variant: "plain"; title: string };

function BoardTopBar({ spec }: { spec: TopBarSpec }): JSX.Element {
  const s = t();
  const papers = profile.value;
  if (spec.variant === "home") {
    const bell = papers !== null && !emergencyOnly(papers);
    return (
      <header class="shell-head" data-testid="board-top-bar">
        <span class="head-start">
          <button type="button" class="head-button" aria-label={s.tabs.me} aria-haspopup="dialog" onClick={openMe} data-testid="open-me">
            <Icon name="menu" />
          </button>
        </span>
        <span class="head-mark">
          <Wordmark name={s.appName} mark={false} />
        </span>
        <span class="head-end">{bell && <BellButton />}</span>
        {/* Whose papers are open (product-reset.md §6): a real, load-bearing control the
            board's own single-profile mock never had to draw — kept here, as it was in the
            old global header, even though the board's Home topbar itself has no room for it.
            "Switch profile" on the Profile tab (`ProfileNav`) is the fuller, second way in. */}
        {papers && (
          <span class="head-whose">
            <ProfileSwitcher />
          </span>
        )}
      </header>
    );
  }
  return (
    <header class="shell-head board-top-bar" data-testid="board-top-bar">
      <span class="head-start">
        {spec.variant === "board" && spec.back && (
          <button type="button" class="head-button" aria-label={s.shell.back} onClick={() => openTab("home")} data-testid="top-bar-back">
            <Icon name="back" />
          </button>
        )}
      </span>
      <span class="head-mid">
        <h1 class="title top-bar-title">{spec.title}</h1>
      </span>
      <span class="head-end">
        {spec.variant === "board" && spec.action && (
          <button type="button" class="head-button" aria-label={spec.action.label} onClick={spec.action.onClick} data-testid="top-bar-action">
            <Icon name={spec.action.icon} />
          </button>
        )}
      </span>
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
  /** Only for the five tab-root screens (see `TopBarSpec` above): the board's own topbar in
   *  place of the global header. Left off, the screen keeps the global `ShellHeader`. */
  topBar?: TopBarSpec;
  /** A screen's own header, replacing both `topBar` and the global `ShellHeader` entirely
   *  (cp3-home's merged Home header: the switcher doubles as the avatar beside the greeting,
   *  one row, not the old menu+wordmark+bell row over a second switcher row). Takes priority
   *  over `topBar` when both are given, which should not happen. */
  header?: ComponentChildren;
  /** A bar of the screen's own, docked above the tab bar and never under the fold it scrolls
   *  behind (docs/design/experience-blueprint.html's `dock()`): Home's own ask bar, with the
   *  living orb, in both densities — replacing the header's caregiver-only `AskField` for this
   *  screen, not stacking under it. */
  bottomBar?: ComponentChildren;
}

/** Every screen with the tab bar (D1): the header, in the chief's density the ask bar — "Ask
 *  about Pa", on every one of her screens — then the page, which scrolls in its own region, and
 *  the tab bar under it in the flow. The bar reserves its own space: nothing scrolls under it
 *  and it never covers a line. */
export function Shell({ tab, children, fill: fills, testId, attrs, extraClass, bar = true, ask = true, topBar, header, bottomBar }: ShellProps): JSX.Element {
  const s = t();
  const d = density();
  const papers = profile.value;
  return (
    <main class={["shell", fills && "fill", extraClass].filter(Boolean).join(" ")} data-density={d} data-testid={testId} {...attrs}>
      {header ?? (topBar ? <BoardTopBar spec={topBar} /> : <ShellHeader />)}
      {!bottomBar && ask && d === "caregiver" && papers && (
        <div class="shell-ask">
          <AskField placeholder={fill(s.shell.askAbout, { name: papers.display_name })} />
        </div>
      )}
      <div class="screen shell-scroll" data-testid="shell-scroll">
        {children}
      </div>
      {bottomBar && <div class="shell-bottom-bar">{bottomBar}</div>}
      {bar && <TabBar tabs={tabsFor(d, s, papers?.scopes ?? [], papers?.standing === "owner")} current={tab} onSelect={(id) => openTab(id as Tab)} label={s.appName} />}
    </main>
  );
}
