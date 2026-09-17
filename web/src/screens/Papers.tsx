import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut } from "../api/types";
import { batch } from "../capture/session";
import { go } from "../flow";
import { t } from "../strings";
import { Header, Pill } from "../ui/components";
import { focusHeading } from "../ui/focus";
import { ReviewStep } from "./onboarding/Records";
import { PaperBatchView } from "./PaperBatch";
import { Shell } from "./Shell";

/** Papers from his photos (E18-01), from Me: the grid, one yes, then a review card for each
 *  paper — checked one at a time, each written only on its own *Looks right*. Leaving lets go of
 *  every photo still in memory. */
export function PapersScreen({ report = false }: { report?: boolean }): JSX.Element {
  const s = t();
  const [reviewing, setReviewing] = useState<ReviewCardOut | null>(null);
  useEffect(() => () => batch.forget(), []);
  // One report from Home's "Add a health report" (docs/design-direction.md): choosing the file
  // there was the yes, so it goes at once, and a paper that was read opens on its review card —
  // the same card as every other paper. One that could not be read stays on the list, saying so
  // in the backend's own words; nothing claims it was read.
  const [opened, setOpened] = useState(false);
  useEffect(() => {
    if (report && batch.stage.value === "choosing") void batch.send();
  }, [report]);
  const done = batch.stage.value === "done";
  useEffect(() => {
    if (!report || opened || !done) return;
    const items = batch.items.value;
    const only = items.length === 1 ? items[0]!.outcome : null;
    if (only?.kind === "card" && !only.checked) {
      setOpened(true);
      setReviewing(only.card);
    }
  }, [report, opened, done]);
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
    <Shell tab={null} testId="papers-screen" attrs={{ "data-stage": batch.stage.value }}>
      <Header title={s.papers.title} />
      <PaperBatchView onReview={setReviewing} />
      <Pill onClick={() => go({ name: "today" })} testId="papers-finish">
        {s.papers.backToday}
      </Pill>
    </Shell>
  );
}
