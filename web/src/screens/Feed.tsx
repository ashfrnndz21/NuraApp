import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { CardClipOut, FeedItemOut, LineOut, OrderPreviewOut } from "../api/types";
import { ClipButton } from "../day/components";
import { clipsOf } from "../day/model";
import { go, openTab } from "../flow";
import { cardView, speechLanguage, statusLine, variantOf, type CardView, type SideAction } from "../feed/model";
import { lineForCard, reorderActions } from "../record/model";
import type { Playback } from "../feed/playback";
import { feedFor } from "../feed/session";
import type { Entry, FeedStore, Note } from "../feed/store";
import { density, profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { dateLine, timeLine } from "../today/model";
import { Card, Notice, Tile } from "../ui/components";
import { PillButton } from "../ui/kit";
import { PlayerControls } from "../ui/Player";
import { voice } from "../player/voice";
import { Shell } from "./Shell";
import "../ui/feed.css";

/** The vertical feed (E21-01): one card fills the screen; up for the next. The backend's
 *  order, its lines, its why and its boundary; four buttons on every card; nothing plays or
 *  moves by itself. See `feed/store.ts` for the pages and `feed/playback.ts` for the voice. */
export function FeedScreen(): JSX.Element | null {
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) return null;
  const open = feedFor(bearer, papers);
  return <FeedPager store={open.store} playback={open.playback} name={papers.display_name} />;
}

function FeedPager({ store, playback, name }: { store: FeedStore; playback: Playback; name: string }): JSX.Element {
  const s = t();
  const pager = useRef<HTMLDivElement>(null);
  const entries = store.entries.value;
  const notes = store.notes.value;
  const audience = store.audience.value;
  const patient = density() === "patient";
  // The reorder card's two buttons (E04-05) are the medicine line's, in the backend's words:
  // the list is read once, when a reorder card is on the page, and matched by the fact the
  // card cites.
  const [lines, setLines] = useState<LineOut[] | null>(null);
  const [asked, setAsked] = useState<Record<string, string[]>>({});
  // What he reads before his yes, by card: who Nura will ask, for which medicine.
  const [previews, setPreviews] = useState<Record<string, OrderPreviewOut>>({});
  const [reorderError, setReorderError] = useState<unknown>(null);
  const hasReorder = entries.some((entry) => variantOf(entry.item) === "reorder");
  useEffect(() => {
    const bearer = token.value;
    const papers = profile.value;
    if (!hasReorder || lines !== null || !bearer || !papers) return;
    nura.medicines(bearer, papers.profile_id, language.value).then(setLines, () => setLines([]));
  }, [hasReorder]);
  const reorderFor = (item: FeedItemOut): Reorder | null => {
    if (variantOf(item) !== "reorder" || !lines) return null;
    const line = lineForCard(item, lines);
    const actions = line ? reorderActions(line) : null;
    return line && actions ? { lineId: line.line_id, ...actions } : null;
  };
  /** "Ask the family to order.": first the preview — who Nura will ask, and for what. If the
   *  family was already asked today, the backend's line says so and there is nothing to add. */
  const askToOrder = async (item: FeedItemOut, lineId: string) => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    setReorderError(null);
    try {
      const shown = await nura.orderPreview(bearer, papers.profile_id, lineId, language.value);
      store.record(item, "tapped");
      if (shown.already_asked) setAsked({ ...asked, [item.item_id]: shown.lines });
      else setPreviews({ ...previews, [item.item_id]: shown });
    } catch (failure) {
      setReorderError(failure);
    }
  };
  /** His yes, for exactly the person and the line the preview named. */
  const orderYes = async (item: FeedItemOut, shown: OrderPreviewOut) => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    setReorderError(null);
    try {
      const minted = await nura.mintOrder(bearer, papers.profile_id, shown.line_id, shown.asked_person_id);
      const done = await nura.askToOrder(bearer, papers.profile_id, shown.line_id, minted.confirmation_id, language.value);
      setAsked({ ...asked, [item.item_id]: done.lines });
      const { [item.item_id]: _, ...rest } = previews;
      setPreviews(rest);
    } catch (failure) {
      setReorderError(failure);
    }
  };
  const orderNo = (item: FeedItemOut) => {
    const { [item.item_id]: _, ...rest } = previews;
    setPreviews(rest);
  };
  // "Hear what Dr Tan said" under a line said at a recorded visit (E21-03): on a tap only.

  const cards = (): HTMLElement[] => [...(pager.current?.querySelectorAll<HTMLElement>("article.feed-card") ?? [])];

  /** Which card is on screen: the one across the pager's middle line. Tells the store (the
   *  next page within two of the end), warms the voices of that card and the two after it,
   *  and stops a voice whose card has left the screen. Nothing is played from here. */
  const settle = () => {
    const root = pager.current;
    if (!root) return;
    const middle = root.scrollTop + root.clientHeight / 2;
    let index = 0;
    for (const [at, card] of cards().entries()) if (card.offsetTop <= middle) index = at;
    const playingKey = playback.playing.peek();
    if (playingKey) {
      const card = root.querySelector<HTMLElement>(`article.feed-card[data-key="${playingKey}"]`);
      // Offsets are whole pixels and the pager's height need not be (it flexes in the shell):
      // a card within a pixel of the edge has left.
      const gone = !card || card.offsetTop + card.offsetHeight <= root.scrollTop + 1 || card.offsetTop >= root.scrollTop + root.clientHeight - 1;
      if (gone) playback.leave(playingKey);
    }
    const list = store.entries.peek();
    playback.warm(list.slice(index, index + 3).map((entry) => ({ itemId: entry.item.item_id, language: entry.item.language })));
    if (index !== store.current || index >= list.length - 1 - 2) void store.visible(index);
  };

  useEffect(() => {
    void store.open();
    // Leaving the feed: its voice stops, and every recording a clip fetched is let go.
    return () => {
      playback.stop();
      voice.forget();
    };
  }, [store, playback]);

  // Back from Ask: the pager opens on the card he left.
  useLayoutEffect(() => {
    const card = cards()[store.current];
    if (card && pager.current) pager.current.scrollTo({ top: card.offsetTop, behavior: "instant" });
  }, []);

  useEffect(() => {
    const root = pager.current;
    if (!root) return;
    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        settle();
      });
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    settle();
    return () => {
      root.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [entries.length]);

  /** Move to a card: focus it and bring it to the top. The pager's own scroll-behavior —
   *  smooth, or instant under Reduce Motion — decides how it moves. */
  const goTo = (index: number) => {
    const list = cards();
    const card = list[Math.max(0, Math.min(index, list.length - 1))];
    if (!card) return;
    card.focus({ preventScroll: true });
    card.scrollIntoView({ block: "start", behavior: "auto" });
  };

  /** The keyboard, and a screen reader's page keys (the ARIA feed pattern): Page Down and
   *  Page Up move a whole card; on a focused card, the arrows and Home / End do too. */
  const onKey = (event: KeyboardEvent) => {
    const list = cards();
    const active = document.activeElement;
    const at = list.findIndex((card) => card === active || card.contains(active));
    const onCard = at >= 0 && list[at] === active;
    const from = at >= 0 ? at : store.current;
    let to: number | null = null;
    if (event.key === "PageDown" || (onCard && event.key === "ArrowDown")) to = from + 1;
    else if (event.key === "PageUp" || (onCard && event.key === "ArrowUp")) to = from - 1;
    else if (onCard && event.key === "Home") to = 0;
    else if (onCard && event.key === "End") to = list.length - 1;
    if (to === null) return;
    event.preventDefault();
    goTo(to);
  };

  const now = new Date();
  const locale = LOCALE[language.value];
  const keptUntil = store.keptUntil.value;
  // A kept page past its midnight is never shown, even if the app stayed open.
  const expired = store.origin.value === "kept" && keptUntil !== null && now.getTime() >= Date.parse(keptUntil);
  const shown = expired ? [] : entries;
  const blank = store.offline.value && shown.length === 0 && !store.error.value;
  const keptAt = store.keptAt.value;

  return (
    <Shell tab="today" fill>
      <div class="feed-screen" data-density={density()} data-testid="feed-screen">
      {/* The screen's name for a screen reader, and where focus starts when the feed opens. */}
      <h1 class="sr-only">{s.feed.title}</h1>
      <div class="feed-strip">
        {store.offline.value && keptAt && shown.length > 0 && (
          <Tile glass testId="offline">
            <p>{s.today.offline}</p>
            <p>{s.feed.offlineSub}</p>
            <p class="caption">{fill(s.today.asOf, { date: dateLine(new Date(keptAt), locale), time: timeLine(new Date(keptAt), locale) })}</p>
          </Tile>
        )}
        <Notice error={store.error.value} />
        <Notice error={store.said.value} />
        <Notice error={reorderError} />
        {blank && (
          <>
            <Card lines={[s.today.cannotReach]} testId="cannot-reach" />
            <Card title={s.today.emergencyTitle} lines={[s.today.emergencySoon]} testId="emergency-placeholder" />
          </>
        )}
        {!blank && store.origin.value !== "none" && !store.busy.value && !store.error.value && shown.length === 0 && (
          <Card
            lines={[s.feed.empty]}
            hear={false}
            testId="feed-empty"
            action={
              <PillButton onClick={() => go({ name: "today" })} testId="feed-empty-back">
                {s.feed.emptyAction}
              </PillButton>
            }
          />
        )}
      </div>

      {!blank && (
        <div
          class="feed-pager"
          ref={pager}
          role="feed"
          aria-label={s.feed.title}
          aria-busy={store.busy.value}
          tabIndex={-1}
          onKeyDown={onKey}
          data-testid="pager"
        >
          {shown.map((entry, index) => (
            <FeedCard
              key={entry.key}
              entry={entry}
              index={index}
              view={cardView(entry.item)}
              clips={clipsOf(entry.item)}
              note={notes.get(entry.item.item_id) ?? null}
              status={statusLine(entry.item, audience)}
              patient={patient}
              owner={profile.value?.standing === "owner"}
              name={name}
              s={s}
              playing={playback.playing.value === entry.key}
              onHear={(view) => {
                playback.hear({ key: entry.key, itemId: view.itemId, lines: view.spoken, language: speechLanguage(view.language, language.value) });
                store.record(entry.item, "heard");
              }}
              onAsk={() => {
                playback.stop();
                store.record(entry.item, "tapped");
                go({ name: "ask", item: entry.item });
              }}
              onFamily={() => void store.share(entry.item)}
              onNotForMe={() => void store.notForMe(entry.item)}
              onKeepGoing={() => goTo(index + 1)}
              reorder={reorderFor(entry.item)}
              said={asked[entry.item.item_id] ?? null}
              preview={previews[entry.item.item_id] ?? null}
              onAskToOrder={(lineId) => void askToOrder(entry.item, lineId)}
              onOrderYes={(shown) => void orderYes(entry.item, shown)}
              onOrderNo={() => orderNo(entry.item)}
            />
          ))}
          {store.quiet.value && store.ended.value && (
            <section class="feed-end" data-testid="feed-quiet">
              <div class="tile paper">
                <p>{s.feed.quiet}</p>
                <p>{s.feed.quietSub}</p>
              </div>
            </section>
          )}
          {!store.quiet.value && store.ended.value && store.origin.value !== "none" && (
            <section class="feed-end" data-testid="feed-end">
              <div class="tile paper">
                <p>{s.feed.nothingMore}</p>
              </div>
            </section>
          )}
        </div>
      )}

      </div>
    </Shell>
  );
}

/** The reorder card's buttons: its line and the backend's two labels. */
interface Reorder {
  lineId: string;
  askToOrder: string;
  iHaveMore: string;
}

interface FeedCardProps {
  entry: Entry;
  index: number;
  view: CardView;
  /** Where each line was said at a recorded visit, by the line's words (E21-03). */
  clips: Map<string, CardClipOut>;
  note: Note | null;
  status: ReturnType<typeof statusLine>;
  patient: boolean;
  owner: boolean;
  name: string;
  s: Strings;
  onHear: (view: CardView) => void;
  onAsk: () => void;
  onFamily: () => void;
  onNotForMe: () => void;
  onKeepGoing: () => void;
  /** This card's voice is open in the player: its controls show above the side actions. */
  playing: boolean;
  reorder: Reorder | null;
  /** What "Ask the family to order." did, in the backend's lines. */
  said: string[] | null;
  /** Before his yes: who Nura will ask, for which medicine, in the backend's lines. */
  preview: OrderPreviewOut | null;
  onAskToOrder: (lineId: string) => void;
  onOrderYes: (shown: OrderPreviewOut) => void;
  onOrderNo: () => void;
}

/** One card: the section it came from, the backend's headline and lines, its boundary, its
 *  why; for the caregiver, what became of it; one action at most; the four side actions.
 *
 *  The card is a column the height of the pager: the lines take what is left above the
 *  buttons and scroll inside the card when they need more, and the buttons follow in normal
 *  flow. Nothing is drawn over a line — the boundary an inferring card ends on is always
 *  readable, scrolled to if need be. */
function FeedCard({ entry, index, view, clips, note, status, patient, owner, name, s, onHear, onAsk, onFamily, onNotForMe, onKeepGoing, playing, reorder, said, preview, onAskToOrder, onOrderYes, onOrderNo }: FeedCardProps): JSX.Element {
  const item: FeedItemOut = entry.item;
  const declined = note === "declined";
  const section =
    view.section === "now" ? s.today.now : view.section === "today" ? s.today.forYou : view.section === "story" ? s.feed.story : view.section === "learning" ? s.feed.learning : null;
  const paper = patient || view.variant === "flag" || view.action !== null;
  const actions = declined ? (["hear"] as const) : view.actions;
  return (
    <article
      class={declined ? "feed-card declined" : "feed-card"}
      data-testid="feed-card"
      data-key={entry.key}
      data-index={index}
      data-item-id={item.item_id}
      data-type={item.type}
      data-supply={item.supply}
      data-variant={view.variant}
      data-state-id={view.stateId}
      tabIndex={0}
      aria-posinset={index + 1}
      aria-setsize={-1}
      aria-label={view.spoken.join(" ")}
    >
      <div class={paper ? "tile paper" : "tile glass"}>
        {/* Every line of the card, in a region that scrolls inside the card when it is taller
            than the space above the buttons; the buttons sit below it, never over it. */}
        <div class="feed-body" data-testid="card-body" tabIndex={0}>
        {section && <p class="feed-section">{section}</p>}
        <h2 class="title">{view.headline}</h2>
        {!declined && (
          <>
            <div class="lines" data-testid="lines">
              {view.lines.map((line, at) => {
                const clip = clips.get(line);
                if (!clip) return <p key={at}>{line}</p>;
                return (
                  <div key={at} class="clip-line" data-testid="card-line">
                    <p>{line}</p>
                    <ClipButton clip={clip} playKey={`${entry.key}:${at}`} />
                  </div>
                );
              })}
            </div>
            {view.boundary.length > 0 && (
              <div class="lines boundary" data-testid="boundary">
                {view.boundary.map((line, at) => (
                  <p key={at}>{line}</p>
                ))}
              </div>
            )}
            {status && (
              <p class="feed-status" data-testid="status">
                {fill(s.feed[status], { name })}
              </p>
            )}
            {view.source && (
              <p class="provenance source" data-testid="source">
                <a href={view.source.url} target="_blank" rel="noopener noreferrer">
                  {fill(s.feed.fromPublisher, { publisher: view.source.publisher })}
                </a>
              </p>
            )}
            {view.why && (
              <p class="provenance" data-testid="why">
                {view.why}
              </p>
            )}
          </>
        )}
        {said && (
          <div class="feed-note" role="status" data-testid="asked">
            {said.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
        )}
        {preview && (
          <div class="feed-note" role="group" data-testid="order-preview">
            {preview.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
        )}
        {note && (
          <div class="feed-note" role="status" data-testid="note">
            {note === "declined" && (
              <>
                <p>{s.feed.declined}</p>
                {owner && <p>{s.feed.declinedToday}</p>}
              </>
            )}
            {note === "shared" && <p>{s.feed.shared}</p>}
            {note === "cannotShare" && <p>{s.feed.cannotShare}</p>}
          </div>
        )}
        </div>
        <div class="feed-controls">
        {!declined && view.action === "keepGoing" && (
          <button type="button" class="pill plum" onClick={onKeepGoing} data-testid="keep-going">
            {s.feed.keepGoing}
          </button>
        )}
        {!declined && preview && (
          <>
            <button type="button" class="pill plum" onClick={() => onOrderYes(preview)} data-testid="order-yes">
              {s.record.orderYes}
            </button>
            <button type="button" class="pill" onClick={onOrderNo} data-testid="order-no">
              {s.record.orderNo}
            </button>
          </>
        )}
        {!declined && reorder && !preview && (
          <>
            <button type="button" class="pill plum" onClick={() => onAskToOrder(reorder.lineId)} disabled={said !== null} data-testid="ask-to-order">
              {reorder.askToOrder}
            </button>
            <button type="button" class="pill" onClick={() => go({ name: "record", at: { name: "more", lineId: reorder.lineId } })} data-testid="i-have-more">
              {reorder.iHaveMore}
            </button>
          </>
        )}
        {!declined && view.action === "toTablets" && (
          <button type="button" class="pill" onClick={() => go({ name: "today" })} data-testid="to-tablets">
            {s.feed.toTablets}
          </button>
        )}
        {playing && <PlayerControls />}
        <div class={actions.length === 1 ? "feed-actions one" : "feed-actions"} role="group" aria-label={view.headline}>
          {actions.map((action) => (
            <SideButton key={action} action={action} s={s} onClick={{ hear: () => onHear(view), ask: onAsk, family: onFamily, notForMe: onNotForMe }[action]} />
          ))}
        </div>
        </div>
      </div>
    </article>
  );
}

const ICONS: Record<SideAction, JSX.Element> = {
  hear: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 10v4h3l4 4V6L7 10H4z" />
      <path d="M15 9a4 4 0 0 1 0 6" />
      <path d="M17.5 6.5a8 8 0 0 1 0 11" />
    </svg>
  ),
  ask: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M6 11a6 6 0 0 0 12 0M12 17v4" />
    </svg>
  ),
  family: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 20l2-5a8 8 0 1 1 3 3z" />
    </svg>
  ),
  notForMe: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    </svg>
  ),
};

function SideButton({ action, s, onClick }: { action: SideAction; s: Strings; onClick: () => void }): JSX.Element {
  const word = { hear: s.today.hear, ask: s.feed.ask, family: s.feed.family, notForMe: s.feed.notForMe }[action];
  return (
    <button type="button" onClick={onClick} data-testid={`action-${action}`}>
      {ICONS[action]}
      {word}
    </button>
  );
}
