import type { JSX } from "preact";
import type { FeedItemOut } from "../api/types";
import { go } from "../flow";
import { Header, Hear, TabBar, Tile } from "../ui/components";

/** One card a push opened (#143): the backend's own lines, its boundary under it, and a tap to
 *  hear it. Nothing plays by itself; Today is one tap away. */
export function CardScreen({ item }: { item: FeedItemOut }): JSX.Element {
  return (
    <main class="screen">
      <Header title={item.headline} onBack={() => go({ name: "today" })} />
      <Tile paper testId="opened-card">
        <div class="lines">
          {item.body.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
        {item.boundary && <p class="boundary">{item.boundary}</p>}
        <Hear lines={item.voice.length > 0 ? item.voice : item.body} />
      </Tile>
      <TabBar current="today" onSelect={(tab) => go(tab === "today" ? { name: "today" } : { name: "me" })} />
    </main>
  );
}
