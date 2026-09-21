import { useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut } from "../../api/types";
import { continueAfterPaper } from "./Records";
import { profile } from "../../store/session";
import { fill, t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { PaperInsightView } from "../Insight";
import { StepTitle } from "./parts";

/** Checkpoint 3, "What it means for you" (package 7), inside the sitting (`onboarding/state.ts`
 *  `Stage`'s `"insight"`): the same content the Record's Papers flow shows
 *  (`screens/Insight.tsx`'s `PaperInsightView`), in onboarding's own bare chrome — no Shell, no
 *  tab bar, until the sitting itself is done. "Not now" (the blueprint's own words, the same
 *  ones `PaperInsightView` always shows) runs what "Looks right" used to run at once
 *  (`continueAfterPaper`) and returns to the step that would have come next: never a dead end,
 *  and never a step skipped or reordered. A failure on the way out (the sitting's own read,
 *  offline) is said here, with the onboarding step's own "Next" to try again — never a silent
 *  stall on a screen with nothing left to tap. */
export function InsightStep({ card }: { card: ReviewCardOut }): JSX.Element {
  const s = t();
  const papers = profile.value;
  const self = papers?.standing === "owner";
  const patientName = papers?.display_name ?? "";
  const title = self ? s.paperInsight.screenTitle : fill(s.paperInsight.screenTitleOther, { patient: patientName });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const next = async () => {
    setBusy(true);
    setError(null);
    try {
      await continueAfterPaper(card);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen onboarding" data-stage="insight" data-card-id={card.card_id}>
      <StepTitle title={title} />
      <PaperInsightView card={card} onLeave={() => void next()} testId="insight-body" />
      <Notice error={error} />
      {error && (
        <Pill onClick={() => void next()} disabled={busy} testId="insight-next-retry">
          {s.onboarding.next}
        </Pill>
      )}
    </main>
  );
}
