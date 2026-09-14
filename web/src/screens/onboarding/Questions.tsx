import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { QuestionOut } from "../../api/types";
import { closeSitting, who } from "../../onboarding/actions";
import { biography, say } from "../../onboarding/state";
import { density } from "../../store/session";
import { fill, t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

/** Questions from the papers (#117): the backend's list, each one whole line, spoken on Hear,
 *  with Keep or Not this one, and the backend's own line for how many more wait for later.
 *  Keep is his yes: the sitting puts the line on the next visit's list (E05) when one is
 *  booked, and with none it waits there and moves when one is (`handed_over_to`).
 *  Then the sitting closes. The patient sees one per screen; the caregiver, the list. */
export function QuestionsStep(): JSX.Element {
  const s = t();
  const q = s.onboarding.questions;
  const patient = density() === "patient";
  const bio = biography.value;
  const questions = bio?.questions ?? [];
  const [ack, setAck] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const act = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const decide = (question: QuestionOut, keep: boolean) =>
    act(async () => {
      const { bearer, profileId } = who();
      // His keep is the one call: the sitting puts a kept question on the next visit's list
      // itself (E05), and with no visit booked it waits and moves when one is.
      const updated = await nura.answerQuestion(bearer, profileId, question.question_id, keep);
      biography.value = updated;
      setAck(keep ? q.kept : q.dropped);
      if (patient && !updated.questions.some((each) => each.kept === null)) await closeSitting();
    });

  const title = bio?.step === "questions" ? bio.prompt.headline : say(q.titleSelf, q.titleOther);
  const next = (
    <Pill plum onClick={() => void act(closeSitting)} disabled={busy} testId="questions-next">
      {s.onboarding.next}
    </Pill>
  );

  if (questions.length === 0) {
    return (
      <main class="screen onboarding" data-stage="questions">
        <StepTitle title={title} />
        <Sheet lines={[q.none]} testId="questions-none" />
        <Notice error={error} />
        {next}
      </main>
    );
  }

  const current = questions.find((each) => each.kept === null);
  const shown = patient ? (current ? [current] : []) : questions;
  return (
    <main class="screen onboarding" data-stage="questions">
      <StepTitle title={title} />
      <p class="lead">{q.lead}</p>
      <Status text={ack} testId="question-ack" />
      {shown.map((question) => (
        <Sheet
          key={question.question_id}
          caption={patient ? fill(s.onboarding.readBack.lineOf, { n: questions.indexOf(question) + 1, total: questions.length }) : undefined}
          lines={[question.line]}
          source={question.source ?? undefined}
          stateId={question.state_id ?? undefined}
          testId="question"
        >
          <div class="choices" role="group">
            <Pill plum={patient} onClick={() => void decide(question, true)} disabled={busy} extraClass="yes" pressed={question.kept === true} testId="keep">
              {q.keep}
            </Pill>
            <Pill onClick={() => void decide(question, false)} disabled={busy} extraClass="no" pressed={question.kept === false} testId="not-this">
              {q.notThis}
            </Pill>
          </div>
        </Sheet>
      ))}
      {bio?.more && (
        <p class="lead" data-testid="questions-more">
          {bio.more}
        </p>
      )}
      <Notice error={error} />
      {(!patient || !current) && next}
    </main>
  );
}
