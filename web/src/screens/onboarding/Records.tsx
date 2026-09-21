import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { batch, sendPaperStream } from "../../capture/session";
import { PaperBatchView } from "../PaperBatch";
import { Refused } from "../../api/client";
import * as nura from "../../api/nura";
import type { ReviewCardOut } from "../../api/types";
import { closeSitting, refreshBiography, refreshPlan, who } from "../../onboarding/actions";
import { paperDate } from "../../onboarding/dates";
import { decisionsFor, kindLine, readable, startingEdits, type FieldEdit } from "../../onboarding/review";
import { biography, lastPaper, returnTo, say, to, whose } from "../../onboarding/state";
import { language, LOCALE, t } from "../../strings";
import { density } from "../../store/session";
import { Notice, Pill } from "../../ui/components";
import { ThreeStateButton } from "../../ui/kit";
import { PaperBubble, ReadingProgress, ReadingResult } from "./PaperReading";
import { usePaperTrace } from "./paperTrace";
import { ReportTable } from "./ReportTable";
import { Capture, Sheet, Status, StepTitle } from "./parts";

/** A file picked for the reading screen: its name for the bubble, and a thumbnail only for a
 *  photo — revoked the moment it is no longer shown (papers.spec.ts: nothing of a photo stays
 *  on the phone). */
function useFileBubble(): { file: { name: string; thumb: string | null } | null; show: (file: File) => void; clear: () => void } {
  const [file, setFile] = useState<{ name: string; thumb: string | null } | null>(null);
  useEffect(() => () => {
    if (file?.thumb) URL.revokeObjectURL(file.thumb);
  }, [file]);
  return {
    file,
    show: (picked: File) => setFile({ name: picked.name, thumb: picked.type.startsWith("image/") ? URL.createObjectURL(picked) : null }),
    clear: () => setFile(null),
  };
}

/** The assistant-led records step (E01-02): the backend's next prompt, shown with its
 *  spoken twin; a photo or a file; the review card; one yes; what Nura learned; the next
 *  prompt; and "That is all for today", which closes the session. */

export function RecordsStep(): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const bio = biography.value;
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState<ReviewCardOut | null>(null);
  const paper = usePaperTrace();
  const bubble = useFileBubble();

  const upload = async (file: File) => {
    bubble.show(file);
    setBusy(true);
    setError(null);
    try {
      returnTo.value = "records";
      paper.start();
      const card = await sendPaperStream(file, paper.onStep);
      // A refusal that already happened — a page that is not a health paper, or one Nura could
      // not read at all — has nothing to show a reading screen over: no headline, no rows, no
      // thinking animation for a thing that is already done. Straight to the honest word for it.
      if (!readable(card)) {
        bubble.clear();
        to({ name: "review", card });
        return;
      }
      setReading(card);
    } catch (failure) {
      setError(failure);
      bubble.clear();
    } finally {
      setBusy(false);
    }
  };

  /** No more papers: the read-back when there are papers to read back, else the close. */
  const enough = async () => {
    setBusy(true);
    setError(null);
    try {
      await refreshBiography();
      const now = biography.value;
      if (now && now.open_cards > 0) setError(new Refused("CardsStillOpen", 409));
      else if (now && now.papers.length === 0) await closeSitting();
      else to({ name: "readBack" });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  if (bubble.file && (busy || reading)) {
    return (
      <main class="screen onboarding" data-stage="reading">
        <PaperBubble name={bubble.file.name} thumb={bubble.file.thumb} testId="paper-bubble" />
        {!reading && <ReadingProgress status={paper.trace.length > 0 ? paper.trace[paper.trace.length - 1]!.text : r.looking} testId="looking" />}
        {reading && <ReadingResult card={reading} onContinue={() => to({ name: "review", card: reading })} testId="reading-result" />}
      </main>
    );
  }

  // The sitting's own words for the step address him; a chief reads the app's.
  const inPapers = whose().self && bio?.step === "papers";
  return (
    <main class="screen onboarding" data-stage="records">
      <StepTitle title={inPapers ? bio.prompt.headline : say(r.titleSelf, r.titleOther)} />
      <Status text={lastPaper.value ? r.saved : null} testId="saved" />
      {inPapers && bio.prompt.lines.length > 0 && <Sheet lines={bio.prompt.lines} testId="prompt" />}
      <Notice error={error} />
      <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={r.photo} />
      <Pill onClick={() => to({ name: "batch" })} disabled={busy} testId="choose-many">
        {s.papers.chooseMany}
      </Pill>
      <Pill onClick={() => void enough()} disabled={busy} testId="all-done">
        {r.allPapers}
      </Pill>
    </main>
  );
}

/** Many photos at once, in the sitting (E18-01): the grid he confirms, then a review card for
 *  each paper; each one he checks joins the sitting like a single photo does. */
export function BatchStep(): JSX.Element {
  const s = t();
  return (
    <main class="screen onboarding" data-stage="batch">
      <StepTitle title={s.papers.title} />
      <PaperBatchView
        onReview={(card) => {
          returnTo.value = "batch";
          to({ name: "review", card });
        }}
      />
      <Pill
        onClick={() => {
          batch.forget();
          to({ name: "records" });
        }}
        testId="batch-done"
      >
        {s.onboarding.back}
      </Pill>
    </main>
  );
}

/** The capture review card (E02-07): each line of the paper as it was read, how sure Nura
 *  is in words (solid underline, or dotted and "Please check this one."), a box to correct
 *  it, "Leave this one out", and one "Looks right" that mints the yes for exactly these
 *  decisions and spends it. Then the biography takes the paper in and says what it learned. */
interface ReviewStepProps {
  card: ReviewCardOut;
  /** Outside onboarding (the Record's waiting papers, a machine's screen, papers from his
   *  photos, E18-01): what happens once the card is confirmed, instead of the sitting taking
   *  the paper in — the card's facts are written, and nothing joins a sitting. */
  onDone?: (card: ReviewCardOut) => void;
  /** Outside the sitting: back to the list the card was opened from. */
  onBack?: () => void;
  /** Another photo, when the page could not be read: the caller sends it and shows its card. */
  onPaper?: (file: File) => Promise<void>;
}

export function ReviewStep({ card, onDone, onBack, onPaper }: ReviewStepProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const locale = LOCALE[language.value];
  const [edits, setEdits] = useState<Record<string, FieldEdit>>(() => startingEdits(card));
  const [waiting, setWaiting] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [fixHint, setFixHint] = useState(false);
  const paper = usePaperTrace();
  const back = onBack ?? (() => to({ name: returnTo.value }));

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      if (onPaper) await onPaper(file);
      else {
        paper.start();
        to({ name: "review", card: await sendPaperStream(file, paper.onStep) });
      }
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  if (!readable(card)) {
    return (
      <main class="screen onboarding" data-stage="review">
        <StepTitle title={r.reviewTitle} />
        <Sheet lines={card.notice?.length ? card.notice : [kindLine(card.document_kind, s), r.unknownHint]} testId="review-unreadable" />
        {busy && <ReadingProgress status={paper.trace.length > 0 ? paper.trace[paper.trace.length - 1]!.text : r.looking} testId="looking-again" />}
        <Notice error={error} />
        <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={r.photo} />
        <Pill quiet onClick={back}>
          {s.onboarding.back}
        </Pill>
      </main>
    );
  }

  const edit = (fieldId: string, patch: Partial<FieldEdit>) => {
    setEdits({ ...edits, [fieldId]: { ...edits[fieldId]!, ...patch } });
    setWaiting(waiting.filter((each) => each !== fieldId));
  };

  const looksRight = async () => {
    const { decisions, waiting: still } = decisionsFor(card, edits);
    setWaiting(still);
    // Waits for him rather than resolving: a `ThreeStateButton` that "finished" while a line is
    // still open for correction would say "Saved" over a decision that never went anywhere.
    if (still.length > 0) throw new Error("waiting on a decision");
    setBusy(true);
    setError(null);
    try {
      const { bearer, profileId } = who();
      if (!confirmed) {
        const yes = await nura.mintReviewYes(bearer, profileId, card.card_id, decisions);
        await nura.confirmReviewCard(bearer, profileId, card.card_id, decisions, yes.confirmation_id);
        setConfirmed(true);
      }
      if (onDone) {
        onDone(card);
        return;
      }
      if (returnTo.value === "records" || returnTo.value === "batch") {
        // The sitting takes the paper in; its read-back will read the card's facts back to him.
        await nura.attachPaper(bearer, profileId, card.card_id);
        await refreshBiography();
      } else {
        // From the Ready screen the sitting is closed: the gap closes as the fact arrives.
        await refreshPlan();
      }
      if (returnTo.value === "batch") batch.checked(card.card_id);
      lastPaper.value = card.card_id;
      to({ name: returnTo.value });
    } catch (failure) {
      setError(failure);
      throw failure;
    } finally {
      setBusy(false);
    }
  };

  const patient = density() === "patient";
  return (
    <main class="screen onboarding" data-stage="review" data-card-id={card.card_id}>
      <StepTitle title={r.reviewTitle} />
      {card.notice && card.notice.length > 0 && <Sheet glass lines={card.notice} testId="review-notice" />}
      <ReportTable
        card={card}
        edits={edits}
        onEdit={edit}
        waiting={waiting}
        documentDateText={card.document_date ? paperDate(card.document_date, locale) : null}
        dateText={paperDate(card.created_at, locale)}
        patient={patient}
        testId="review-card"
      />
      {waiting.length > 0 && (
        <p role="alert" data-testid="not-a-number">
          {card.fields.find((field) => field.field_id === waiting[0])?.unreadable ? r.typeIt : r.notANumber}
        </p>
      )}
      {fixHint && (
        <p class="caption" role="status" data-testid="fix-hint">
          {r.fixHint}
        </p>
      )}
      {busy && <Status text={s.onboarding.saving} />}
      <Notice error={error} />
      <div class="acts">
        <ThreeStateButton label={r.looksRight} busyLabel={s.onboarding.saving} doneLabel={r.saved} onAct={looksRight} testId="looks-right" />
        <Pill quiet onClick={() => setFixHint(true)} testId="fix-number">
          {r.fixNumber}
        </Pill>
      </div>
    </main>
  );
}
