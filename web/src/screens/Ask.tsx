import type { JSX } from "preact";
import type { FeedItemOut } from "../api/types";
import { go } from "../flow";
import { t } from "../strings";
import { Header, Pill, TabBar, Tile } from "../ui/components";

/** Ask about a card (E21-04). The place E03's `POST /ask` answers when it is on main: until
 *  then it names the card he asked about, in the backend's own headline, says plainly that
 *  asking comes here soon, and takes him back to the same card. */
export function AskScreen({ item }: { item: FeedItemOut }): JSX.Element {
  const s = t();
  return (
    <main class="screen" data-testid="ask-screen">
      <Header title={s.feed.askTitle} />
      <Tile paper>
        <h2 class="title">{item.headline}</h2>
        <p>{s.feed.askSoon}</p>
      </Tile>
      <Pill onClick={() => go({ name: "feed" })} testId="back-to-cards">
        {s.feed.back}
      </Pill>
      <TabBar current="today" onSelect={(tab) => go(tab === "me" ? { name: "me" } : { name: "today" })} />
    </main>
  );
}
