import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut } from "../api/types";
import { batch } from "../capture/session";
import { go } from "../flow";
import { readable } from "../onboarding/review";
import { t } from "../strings";
import { Header, Pill } from "../ui/components";
import { focusHeading } from "../ui/focus";
import { PillButton } from "../ui/kit";
import { PaperBubble, ReadingProgress, ReadingResult } from "./onboarding/PaperReading";
import { ReviewStep } from "./onboarding/Records";
import { PaperBatchView } from "./PaperBatch";
import { Shell } from "./Shell";

/** Papers from his photos (E18-01), from Me: the grid, one yes, then a review card for each
 *  paper — checked one at a time, each written only on its own *Looks right*. Leaving lets go of
 *  every photo still in memory. */
export function PapersScreen({ report = false }: { report?: boolean }): JSX.Element {
  const s = t();
  const [reviewing, setReviewing] = useState<ReviewCardOut | null>(null);
  // The reading screen (E02, checkpoint 2): what Nura found the moment a single report reads,
  // before he ever sees the full table — the same component the sitting's own papers step
  // shows. Only for a card there is something to read at all: a refusal already happened has
  // nothing to show a reading screen over (`Records.tsx`'s own `RecordsStep`).
  const [reading, setReading] = useState<ReviewCardOut | null>(null);
  useEffect(() => () => batch.forget(), []);
  // One report from Home's "Add a health report" (docs/design-direction.md): choosing the file
  // there only picked it — it does not go until he says so here, on its own confirm card naming
  // the file and giving him "Send it" (reviewer #237 item 6: a chosen file is never sent on its
  // own). A paper that was read then opens on its review card — the same card as every other
  // paper. One that could not be read stays on the list, saying so in the backend's own words;
  // nothing claims it was read.
  const [opened, setOpened] = useState(false);
  const items = batch.items.value;
  const reportPicked = report && batch.stage.value === "choosing" && items.length === 1 ? items[0]! : null;
  // While the one real upload is in flight: the same paper bubble the sitting's own reading
  // screen shows, so a screen capture (and a person) can see it genuinely mid-read rather than
  // jumping straight from "Send it" to the finished card.
  const sendingSingle = report && batch.stage.value === "sending" && items.length === 1 ? items[0]! : null;
  const done = batch.stage.value === "done";
  useEffect(() => {
    if (!report || opened || !done) return;
    const only = items.length === 1 ? items[0]!.outcome : null;
    if (only?.kind === "card" && !only.checked) {
      setOpened(true);
      if (readable(only.card)) setReading(only.card);
      else setReviewing(only.card);
    }
  }, [report, opened, done]);
  useEffect(() => focusHeading(), [reviewing?.card_id ?? reading?.card_id ?? ""]);
  if (reading) {
    const picked = items[0]!;
    return (
      <Shell tab={null} testId="papers-screen" attrs={{ "data-stage": "reading" }}>
        {/* The reading screen has just the back control and the paper bubble (blueprint
            `reading`): no screen title sitting over a single paper's own bubble. */}
        <header class="screen-head reading-head">
          <PillButton variant="quiet" compact icon="back" onClick={() => go({ name: "today" })} testId="reading-back">
            {s.onboarding.back}
          </PillButton>
        </header>
        <PaperBubble name={picked.name} thumb={picked.thumb} testId="paper-bubble" />
        <ReadingResult
          card={reading}
          onContinue={() => {
            setReviewing(reading);
            setReading(null);
          }}
          testId="reading-result"
        />
      </Shell>
    );
  }
  if (sendingSingle) {
    const latest = batch.trace.value;
    return (
      <Shell tab={null} testId="papers-screen" attrs={{ "data-stage": "reading" }}>
        <header class="screen-head reading-head">
          <PillButton variant="quiet" compact icon="back" onClick={() => go({ name: "today" })} testId="reading-back">
            {s.onboarding.back}
          </PillButton>
        </header>
        <PaperBubble name={sendingSingle.name} thumb={sendingSingle.thumb} testId="paper-bubble" />
        <ReadingProgress status={latest.length > 0 ? latest[latest.length - 1]!.text : s.papers.working} testId="papers-trace" />
      </Shell>
    );
  }
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
  if (reportPicked) {
    // His one yes for this file: its name, plain, and one button — nothing goes before he taps
    // it (reviewer #237 item 6). Leaving the screen (the back arrow, the tab bar) lets it go
    // unsent, the same as leaving the many-photo grid before its own Send.
    return (
      <Shell tab={null} testId="papers-screen" attrs={{ "data-stage": "confirm" }}>
        <Header title={s.papers.title} onBack={() => go({ name: "today" })} />
        <p class="lead" data-testid="report-confirm-name">
          {reportPicked.name}
        </p>
        <p class="lead">{s.hub.reportReady}</p>
        <Pill plum onClick={() => void batch.send()} testId="report-send">
          {s.hub.reportSend}
        </Pill>
      </Shell>
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
