import { useState } from "preact/hooks";
import type { JSX } from "preact";
import { tell } from "../../onboarding/actions";
import { asksFor } from "../../onboarding/cloud";
import { answers, conditions, picked } from "../../onboarding/state";
import { density } from "../../store/session";
import { t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Sheet, StepTitle } from "./parts";

/** The follow-up questions some words carry ("How long have you taken them?"), the backend's
 *  words and options, one per screen for the patient, all on one page for the caregiver.
 *  An answer is a tap; "Not now" leaves it unanswered. */
export function AsksStep(): JSX.Element {
  const s = t();
  const patient = density() === "patient";
  const list = asksFor(conditions.value?.words ?? [], picked.value);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await tell();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const choose = (wordId: string, optionId: string | null) => {
    const next = { ...answers.value };
    if (optionId === null) delete next[wordId];
    else next[wordId] = optionId;
    answers.value = next;
    if (!patient) return;
    if (index + 1 < list.length) setIndex(index + 1);
    else void send();
  };

  const shown = patient ? list.slice(index, index + 1) : list;
  return (
    <main class="screen onboarding" data-stage="asks">
      <StepTitle title={s.onboarding.asks.lead} />
      {shown.map((word) => (
        <Sheet key={word.id} caption={word.word} title={word.ask!.question} testId={`ask-${word.id}`}>
          <div class="choices" role="group">
            {word.ask!.options.map((option) => (
              <Pill key={option.id} onClick={() => choose(word.id, option.id)} chosen={answers.value[word.id] === option.id} disabled={busy} testId={`option-${option.id}`}>
                {option.text}
              </Pill>
            ))}
          </div>
          {patient && (
            <Pill quiet onClick={() => choose(word.id, null)} testId="ask-not-now">
              {s.onboarding.notNow}
            </Pill>
          )}
        </Sheet>
      ))}
      <Notice error={error} />
      {!patient && (
        <Pill plum onClick={() => void send()} disabled={busy} testId="asks-next">
          {s.onboarding.next}
        </Pill>
      )}
    </main>
  );
}
