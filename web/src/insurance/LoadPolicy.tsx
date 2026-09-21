import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { sendPaperStream } from "../capture/session";
import type { ReviewCardOut } from "../api/types";
import { readable } from "../onboarding/review";
import { ReviewStep } from "../screens/onboarding/Records";
import { PaperBubble, ReadingProgress, ReadingResult } from "../screens/onboarding/PaperReading";
import { usePaperTrace } from "../screens/onboarding/paperTrace";
import { Capture } from "../screens/onboarding/parts";
import { t } from "../strings";
import { focusHeading } from "../ui/focus";
import { Header, Notice } from "../ui/components";

/** "Add a policy" (package 12a, item 1): the SAME live-reading flow as any paper — a real
 *  thumbnail bubble, one in-place status line with the backend's own stages
 *  (`web/src/screens/onboarding/PaperReading.tsx`, reused unchanged), then the report table's
 *  confirm step (`web/src/screens/onboarding/Records.tsx` `ReviewStep`, reused unchanged) —
 *  wired into the Insurance screen's own local state rather than the onboarding sitting's
 *  navigation, so this package touches no onboarding screen file.
 *
 *  Deliberately visually consistent with every other paper-reading screen in the app (the
 *  `Capture`/`ReviewStep` pipeline has not itself been restyled into the dusk-glass blueprint
 *  language yet — that is the separate, larger "conversation protocol" migration
 *  `docs/design/build-spec.md` §1 tracks) — the passport screen around it is. */
export function LoadPolicyFlow({ onDone, onCancel }: { onDone: (card: ReviewCardOut) => void; onCancel: () => void }): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const [bubble, setBubble] = useState<{ name: string; thumb: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState<ReviewCardOut | null>(null);
  const [reviewing, setReviewing] = useState<ReviewCardOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const paper = usePaperTrace();

  useEffect(() => focusHeading(), [reviewing]);
  useEffect(
    () => () => {
      if (bubble?.thumb) URL.revokeObjectURL(bubble.thumb);
    },
    [bubble],
  );

  const upload = async (file: File): Promise<void> => {
    setBubble({ name: file.name, thumb: file.type.startsWith("image/") ? URL.createObjectURL(file) : null });
    setBusy(true);
    setError(null);
    try {
      paper.start();
      const card = await sendPaperStream(file, paper.onStep);
      // Not a health paper at all, or nothing Nura could read: straight to the honest word for
      // it (`ReviewStep` shows this itself) — no headline, no rows, over a thing that is
      // already done, exactly as the onboarding records step already does for any paper.
      if (!readable(card)) {
        setReviewing(card);
        return;
      }
      setReading(card);
    } catch (failure) {
      setError(failure);
      setBubble(null);
    } finally {
      setBusy(false);
    }
  };

  if (reviewing) {
    return (
      <ReviewStep
        key={reviewing.card_id}
        card={reviewing}
        onBack={() => {
          setReviewing(null);
          setBubble(null);
          setReading(null);
        }}
        onDone={(confirmed) => onDone(confirmed)}
      />
    );
  }

  if (bubble && (busy || reading)) {
    return (
      <main class="screen insurance-load" data-testid="policy-load-reading">
        <PaperBubble name={bubble.name} thumb={bubble.thumb} testId="policy-paper-bubble" />
        {!reading && <ReadingProgress status={paper.trace.length > 0 ? paper.trace[paper.trace.length - 1]!.text : r.looking} testId="policy-reading-status" />}
        {reading && <ReadingResult card={reading} onContinue={() => setReviewing(reading)} testId="policy-reading-result" />}
      </main>
    );
  }

  return (
    <main class="screen insurance-load" data-testid="policy-load">
      <Header title={s.insurance.passport.loadTitle} onBack={onCancel} />
      <Notice error={error} />
      <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={r.photo} />
    </main>
  );
}
