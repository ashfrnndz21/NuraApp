import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { PlanCardOut } from "../../api/types";
import { sendPaper, who } from "../../onboarding/actions";
import { dayLine } from "../../onboarding/dates";
import { asksWord, cardsToShow, invites, opensCamera } from "../../onboarding/plan";
import { biography, finish, plan, planNote, returnTo, to } from "../../onboarding/state";
import { density, profile } from "../../store/session";
import { fill, language, LOCALE, t } from "../../strings";
import { Hear, Notice, Pill } from "../../ui/components";
import { Capture, Sheet, Status, StepTitle } from "./parts";

/** Gaps and unlocks on the Ready screen (E01-04, docs/gaps-and-unlocks.md): the backend's
 *  gap cards — what is missing, what having it lets Nura do, the one action — one for the
 *  patient (the first thing Nura will ask for, and how many follow), the whole list for the
 *  caregiver. "Do it now" on a photo gap opens the camera and comes back here; "Later"
 *  defers it. Then Today. */
export function PlanStep(): JSX.Element {
  const s = t();
  const p = s.onboarding.plan;
  const patient = density() === "patient";
  const [status, setStatus] = useState<string | null>(planNote.value);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      const { bearer, profileId } = who();
      nura.plan(bearer, profileId, language.value).then((found) => (plan.value = found), setError);
    } catch (failure) {
      setError(failure);
    }
  }, [language.value]);

  const later = async (card: PlanCardOut) => {
    setBusy(true);
    setError(null);
    try {
      const { bearer, profileId } = who();
      plan.value = await nura.laterOnPlan(bearer, profileId, card.gap_id, language.value);
      setStatus(p.laterSaid);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const doItNow = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      returnTo.value = "plan";
      to({ name: "review", card: await sendPaper(file) });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const { shown, after } = cardsToShow(plan.value, density());
  const done = biography.value?.next_prompt?.kind === "done" ? biography.value.next_prompt : null;
  const locale = LOCALE[language.value];
  return (
    <main class="screen onboarding" data-stage="plan">
      <StepTitle title={p.title} />
      {done && <Sheet lines={done.lines} source={done.source} stateId={done.state_id} testId="done-prompt" />}
      <Sheet glass lines={[p.lead, p.cadence1, p.cadence2]} testId="cadence" />
      {shown.map((card) => {
        const when = fill(p.onDay, { date: dayLine(card.day, locale) });
        return (
          <section key={card.gap_id} class="tile paper gap" data-testid="gap-card" data-gap={card.gap_id} data-state-id={card.state_id}>
            <p class="caption">{p.missing}</p>
            <h2 class="title">{card.missing}</h2>
            <p>{card.unlock}</p>
            <p class="caption">{when}</p>
            {opensCamera(card) && <Capture onFile={(file) => void doItNow(file)} busy={busy} photoLabel={card.action} plum={patient} withFile={false} />}
            {asksWord(card) && (
              <Pill plum={patient} onClick={() => to({ name: "asks", only: asksWord(card)! })} disabled={busy} testId="do-it-now">
                {card.action}
              </Pill>
            )}
            {invites(card, profile.value?.standing) && (
              <Pill plum={patient} onClick={() => to({ name: "invite" })} disabled={busy} testId="do-it-now">
                {card.action}
              </Pill>
            )}
            <Pill quiet onClick={() => void later(card)} disabled={busy} testId="later">
              {p.later}
            </Pill>
            <p class="provenance" data-testid="source">
              {card.source}
            </p>
            <Hear lines={[card.missing, card.unlock, when]} />
          </section>
        );
      })}
      {after > 0 && (
        <p class="lead" data-testid="more-after">
          {after === 1 ? p.moreOne : fill(p.more, { count: after })}
        </p>
      )}
      {plan.value && shown.length === 0 && <Sheet lines={[p.nothing]} testId="plan-nothing" />}
      <Status text={status} testId="plan-status" />
      <Notice error={error} />
      <Pill plum={!patient} onClick={finish} disabled={busy} testId="open-nura">
        {p.open}
      </Pill>
    </main>
  );
}
