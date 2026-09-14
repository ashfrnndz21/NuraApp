import { useState } from "preact/hooks";
import type { JSX } from "preact";
import { batch } from "../../capture/session";
import { PaperBatchView } from "../PaperBatch";
import { Refused } from "../../api/client";
import * as nura from "../../api/nura";
import type { ReviewCardOut } from "../../api/types";
import { closeSitting, refreshBiography, refreshPlan, sendPaper, who } from "../../onboarding/actions";
import { paperDate } from "../../onboarding/dates";
import { canCorrect, confidenceLine, decisionsFor, fieldLabel, kindLine, readable, spokenLine, startingEdits, valueText, type FieldEdit } from "../../onboarding/review";
import { biography, lastPaper, returnTo, say, to, whose } from "../../onboarding/state";
import { fill, language, LOCALE, t } from "../../strings";
import { density } from "../../store/session";
import { Hear, Notice, Pill } from "../../ui/components";
import { Capture, Sheet, Status, StepTitle } from "./parts";

/** The assistant-led records step (E01-02): the backend's next prompt, shown with its
 *  spoken twin; a photo or a file; the review card; one yes; what Nura learned; the next
 *  prompt; and "That is all for today", which closes the session. */
export function RecordsStep(): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const bio = biography.value;
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      returnTo.value = "records";
      const card = await sendPaper(file);
      to({ name: "review", card });
    } catch (failure) {
      setError(failure);
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

  // The sitting's own words for the step address him; a chief reads the app's.
  const inPapers = whose().self && bio?.step === "papers";
  return (
    <main class="screen onboarding" data-stage="records">
      <StepTitle title={inPapers ? bio.prompt.headline : say(r.titleSelf, r.titleOther)} />
      <Status text={lastPaper.value ? r.saved : null} testId="saved" />
      {inPapers && bio.prompt.lines.length > 0 && <Sheet lines={bio.prompt.lines} testId="prompt" />}
      {busy && <Status text={r.looking} testId="looking" />}
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
 *  decisions and spends it. Then the biography takes the paper in and says what it learned.
 *
 *  Outside the sitting (papers from his photos, E18-01) `onDone` takes over after the yes and
 *  `onBack` goes back to the list: the card's facts are written, and nothing joins a sitting. */
export function ReviewStep({ card, onDone, onBack }: { card: ReviewCardOut; onDone?: () => void; onBack?: () => void }): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const locale = LOCALE[language.value];
  const [edits, setEdits] = useState<Record<string, FieldEdit>>(() => startingEdits(card));
  const [waiting, setWaiting] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const back = onBack ?? (() => to({ name: returnTo.value }));

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      to({ name: "review", card: await sendPaper(file) });
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
        {busy && <Status text={r.looking} />}
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
    if (still.length > 0) return;
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
        onDone();
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
    } finally {
      setBusy(false);
    }
  };

  const head = [
    kindLine(card.document_kind, s),
    ...(card.document_date ? [fill(r.dated, { date: paperDate(card.document_date, locale) })] : []),
    ...(card.high_risk_class ? [r.highRisk] : []),
  ];
  const fields = [...card.fields].sort((a, b) => a.position - b.position);
  const patient = density() === "patient";
  return (
    <main class="screen onboarding" data-stage="review" data-card-id={card.card_id}>
      <StepTitle title={r.reviewTitle} />
      <Sheet
        lines={[...head, r.reviewLead, r.reviewLead2]}
        source={fill(r.fromPhoto, { date: paperDate(card.created_at, locale) })}
        testId="review-card"
      />
      {card.notice && card.notice.length > 0 && <Sheet glass lines={card.notice} testId="review-notice" />}
      {fields.map((field) => {
        const current = edits[field.field_id]!;
        const label = fieldLabel(field, s);
        const sure = !field.needs_confirm && !field.unreadable;
        return (
          <section
            key={field.field_id}
            class={`tile paper${current.leftOut ? " left-out" : ""}`}
            data-testid={`field-${field.attribute}`}
            data-needs-confirm={field.needs_confirm}
          >
            {current.leftOut ? (
              <>
                <p class="label">{label}</p>
                <p>{r.leftOut}</p>
              </>
            ) : canCorrect(field) ? (
              <label class="read">
                <span class="label">{label}</span>
                {field.unreadable && (
                  <span class="lines" data-testid="prompt">
                    {(field.prompt ?? [r.typeIt]).map((line, index) => (
                      <p key={index}>{line}</p>
                    ))}
                  </span>
                )}
                <span class="value-row">
                  <input
                    class={`field ${sure ? "sure" : "unsure"}`}
                    name={`field-${field.attribute}`}
                    aria-label={`${label}: ${r.changeLabel}`}
                    inputMode={typeof field.value === "number" ? "decimal" : "text"}
                    data-unreadable={field.unreadable || undefined}
                    value={current.text}
                    onInput={(event) => edit(field.field_id, { text: (event.target as HTMLInputElement).value })}
                  />
                  {field.unit && <span class="unit">{field.unit}</span>}
                </span>
              </label>
            ) : (
              <>
                <p class="label">{label}</p>
                <p class={`value ${sure ? "sure" : "unsure"}`}>{valueText(field.value)}</p>
                <p class="caption">{r.cannotChange}</p>
              </>
            )}
            {!current.leftOut && <p class="caption" data-testid="confidence">{confidenceLine(field, s)}</p>}
            {waiting.includes(field.field_id) && (
              <p role="alert" data-testid="not-a-number">
                {field.unreadable ? r.typeIt : r.notANumber}
              </p>
            )}
            <Pill quiet onClick={() => edit(field.field_id, { leftOut: !current.leftOut })} testId="leave-out">
              {current.leftOut ? r.keepIn : r.leaveOut}
            </Pill>
            {patient && <Hear lines={current.leftOut ? [label, r.leftOut] : spokenLine(field, s)} />}
          </section>
        );
      })}
      {busy && <Status text={s.onboarding.saving} />}
      <Notice error={error} />
      <Pill plum onClick={() => void looksRight()} disabled={busy} testId="looks-right">
        {r.looksRight}
      </Pill>
    </main>
  );
}
