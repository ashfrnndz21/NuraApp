import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut } from "../api/types";
import { batch } from "../capture/session";
import { go } from "../flow";
import { t } from "../strings";
import { Header, Pill, TabBar } from "../ui/components";
import { focusHeading } from "../ui/focus";
import { ReviewStep } from "./onboarding/Records";
import { PaperBatchView } from "./PaperBatch";

/** Papers from his photos (E18-01), from Me: the grid, one yes, then a review card for each
 *  paper — checked one at a time, each written only on its own *Looks right*. Leaving lets go of
 *  every photo still in memory. */
export function PapersScreen(): JSX.Element {
  const s = t();
  const [reviewing, setReviewing] = useState<ReviewCardOut | null>(null);
  useEffect(() => () => batch.forget(), []);
  useEffect(() => focusHeading(), [reviewing?.card_id ?? ""]);
  if (reviewing) {
    return (
      <ReviewStep
        key={reviewing.card_id}
        card={reviewing}
        onDone={() => {
          batch.checked(reviewing.card_id);
          setReviewing(null);
        }}
        onBack={() => setReviewing(null)}
      />
    );
  }
  return (
    <main class="screen" data-testid="papers-screen" data-stage={batch.stage.value}>
      <Header title={s.papers.title} />
      <PaperBatchView onReview={setReviewing} />
      <Pill onClick={() => go({ name: "today" })} testId="papers-finish">
        {s.papers.backToday}
      </Pill>
      <TabBar current="me" onSelect={(tab) => go(tab === "today" ? { name: "today" } : { name: "me" })} />
    </main>
  );
}
