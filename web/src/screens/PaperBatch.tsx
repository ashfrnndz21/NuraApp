import type { JSX } from "preact";
import type { ReviewCardOut } from "../api/types";
import type { Picked } from "../capture/batch";
import { batch } from "../capture/session";
import { kindLine } from "../onboarding/review";
import { fill, refusalLines, t } from "../strings";
import { Pill } from "../ui/components";
import { StepTrace } from "../ui/kit";
import { Sheet, Status } from "./onboarding/parts";

/** Papers from his photos (E18-01's web substitute): pick many at once with the phone's own
 *  picker, see them as a grid, tap any to leave it out, and send them on one yes — nothing goes
 *  before it. Then each paper says what became of it: a review card to check, the backend's
 *  words that a page is not a health paper, a refusal in its sentence, or that it could not be
 *  sent. Used by the Papers screen and by the sitting's papers step. */
export function PaperBatchView({ onReview }: { onReview: (card: ReviewCardOut) => void }): JSX.Element {
  const s = t();
  const p = s.papers;
  const items = batch.items.value;
  const stage = batch.stage.value;
  const chosen = items.filter((item) => item.chosen).length;
  const sending = batch.sending.value;
  const picked = (event: Event) => {
    const input = event.currentTarget as HTMLInputElement;
    const files = [...(input.files ?? [])];
    input.value = "";
    batch.pick(files);
  };
  const choosing = stage === "empty" || stage === "choosing";
  return (
    <>
      {choosing && <Sheet lines={[p.lead, p.lead2]} testId="papers-lead" />}
      {choosing && (
        <label class={stage === "empty" ? "pill plum" : "pill"} data-testid="choose-photos">
          {p.pick}
          <input type="file" multiple accept="image/*,application/pdf" onChange={picked} data-testid="photos-input" />
        </label>
      )}
      {stage === "choosing" && (
        <>
          <p class="lead">{p.gridLead}</p>
          <ul class="paper-grid" data-testid="paper-grid">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  class={item.chosen ? "paper-tile chosen" : "paper-tile"}
                  aria-pressed={item.chosen}
                  onClick={() => batch.toggle(item.id)}
                  data-testid="paper-tile"
                >
                  {item.thumb ? (
                    <img src={item.thumb} alt="" loading="lazy" decoding="async" />
                  ) : (
                    <span class="paper-doc" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path d="M6 3h8l4 4v14H6z" />
                        <path d="M14 3v4h4M9 12h6M9 16h6" />
                      </svg>
                    </span>
                  )}
                  <span class="paper-name">{fill(p.picture, { count: item.place })}</span>
                  <span class="paper-state">{item.chosen ? p.tileIn : p.tileOut}</span>
                </button>
              </li>
            ))}
          </ul>
          <Pill plum onClick={() => void batch.send()} disabled={chosen === 0} testId="send-papers">
            {chosen === 1 ? p.sendOne : fill(p.send, { count: chosen })}
          </Pill>
        </>
      )}
      <Status text={sending ? fill(p.sending, { n: sending.n, total: sending.total }) : null} testId="papers-sending" />
      {sending && <StepTrace steps={batch.trace.value} working={p.working} testId="papers-trace" />}
      {(stage === "sending" || stage === "done") && (
        <>
          <h2 class="title">{p.found}</h2>
          {items.map((item) => (
            <PaperResult key={item.id} item={item} onReview={onReview} />
          ))}
        </>
      )}
      {stage === "done" && items.some((item) => item.outcome.kind === "notSent") && (
        <Pill onClick={() => void batch.send()} testId="send-rest">
          {p.sendRest}
        </Pill>
      )}
      {stage === "done" && !batch.holdsPhotos() && (
        <p class="caption" data-testid="nothing-kept">
          {p.nothingKept}
        </p>
      )}
    </>
  );
}

function PaperResult({ item, onReview }: { item: Picked; onReview: (card: ReviewCardOut) => void }): JSX.Element {
  const s = t();
  const p = s.papers;
  const outcome = item.outcome;
  return (
    <section class="tile paper" data-testid="paper-result" data-outcome={outcome.kind}>
      <p class="label">{fill(p.picture, { count: item.place })}</p>
      {outcome.kind === "card" && (
        <>
          <p>{kindLine(outcome.card.document_kind, s)}</p>
          {outcome.checked ? (
            <p data-testid="paper-checked">{s.onboarding.records.saved}</p>
          ) : (
            <>
              <p>{p.read}</p>
              <Pill onClick={() => onReview(outcome.card)} testId="check-paper">
                {p.check}
              </Pill>
            </>
          )}
        </>
      )}
      {outcome.kind === "notHealth" && (
        <div class="lines" data-testid="paper-not-health">
          {(outcome.card.notice?.length ? outcome.card.notice : [p.notHealth]).map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
      )}
      {outcome.kind === "refused" && (
        <div class="lines" role="alert">
          {refusalLines(outcome.failure.refusal).map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
      )}
      {outcome.kind === "notSent" && <p role="alert">{p.notSent}</p>}
    </section>
  );
}
