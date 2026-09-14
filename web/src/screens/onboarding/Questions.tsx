import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { QuestionOut } from "../../api/types";
import { who } from "../../onboarding/actions";
import { biography, say, to } from "../../onboarding/state";
import { density } from "../../store/session";
import { fill, t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

/** Questions from the records: the backend's list, each whole, spoken on Hear, with Keep or
 *  Not this one. The patient sees one per screen; the caregiver, the list. */
export function QuestionsStep(): JSX.Element {
  const s = t();
  const q = s.onboarding.questions;
  const patient = density() === "patient";
  const questions = biography.value?.questions ?? [];
  const [ack, setAck] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const decide = async (question: QuestionOut, keep: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const { bearer, profileId } = who();
      const updated = await nura.answerQuestion(bearer, profileId, question.question_id, keep);
      biography.value = updated;
      setAck(keep ? q.kept : q.dropped);
      if (patient && !updated.questions.some((each) => each.kept === null)) to({ name: "plan" });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const next = (
    <Pill plum onClick={() => to({ name: "plan" })} disabled={busy} testId="questions-next">
      {s.onboarding.next}
    </Pill>
  );
  const title = say(q.titleSelf, q.titleOther);

  if (questions.length === 0) {
    return (
      <main class="screen onboarding" data-stage="questions">
        <StepTitle title={title} />
        <Sheet lines={[q.none]} testId="questions-none" />
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
          lines={question.lines}
          source={question.source}
          stateId={question.state_id}
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
      <Notice error={error} />
      {(!patient || !current) && next}
    </main>
  );
}
