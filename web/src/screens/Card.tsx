import type { JSX } from "preact";
import type { FeedItemOut } from "../api/types";
import { go } from "../flow";
import { Header, Hear } from "../ui/components";
import { PaperTile } from "../ui/kit";
import { Shell } from "./Shell";

/** One card a push opened (#143): the backend's own lines, its boundary under it, and a tap to
 *  hear it. Nothing plays by itself; Today is one tap away — the back arrow, or the tab bar. */
export function CardScreen({ item }: { item: FeedItemOut }): JSX.Element {
  return (
    <Shell tab="home" testId="card-screen">
      <Header title={item.headline} onBack={() => go({ name: "today" })} />
      <PaperTile testId="opened-card">
        <div class="lines">
          {item.body.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
        {item.boundary && <p class="boundary">{item.boundary}</p>}
        <Hear lines={item.voice.length > 0 ? item.voice : item.body} />
      </PaperTile>
    </Shell>
  );
}
