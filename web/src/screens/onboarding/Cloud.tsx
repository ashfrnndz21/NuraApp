import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import { tell } from "../../onboarding/actions";
import { asksFor, cloudView, toggle, type CloudWord } from "../../onboarding/cloud";
import { answers, conditions, picked, say, to } from "../../onboarding/state";
import { speak } from "../../speech/speak";
import { token } from "../../store/session";
import { fill, language, t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

/** The word cloud (E01-02): the backend's condition graph as plain words, the most common
 *  biggest and first, so they are on the screen without scrolling. A tap picks a word,
 *  shows the clinic's term in brackets, says the word aloud (its spoken twin — audio only
 *  ever on a tap), and brings in the words that often go with it, which grow with every
 *  pick that points at them. Nothing here is a diagnosis; the lines say so. */
export function CloudStep(): JSX.Element {
  const s = t();
  const c = s.onboarding.cloud;
  const bearer = token.value;
  const [showAll, setShowAll] = useState(false);
  const [lastPicked, setLastPicked] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!bearer || conditions.value?.language === language.value) return;
    nura.conditions(bearer, language.value).then((found) => (conditions.value = found), setError);
  }, [bearer, language.value]);

  const words = conditions.value?.words ?? [];
  const view = cloudView(words, picked.value, { showAll, lastPicked });

  const tap = (word: CloudWord) => {
    const next = toggle(words, picked.value, word.id);
    const nowPicked = next.includes(word.id);
    picked.value = next;
    answers.value = Object.fromEntries(Object.entries(answers.value).filter(([id]) => next.includes(id)));
    setLastPicked(nowPicked ? word.id : null);
    setStatus(nowPicked ? c.noted : c.removed);
    if (nowPicked) {
      speak({ lines: word.term ? [word.word, fill(c.term, { term: word.term })] : [word.word], language: language.value });
    }
  };

  const done = async () => {
    if (asksFor(words, picked.value).length > 0) return to({ name: "asks" });
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

  const title = say(c.titleSelf, c.titleOther);
  return (
    <main class="screen onboarding" data-stage="cloud">
      <StepTitle title={title} />
      <p class="lead">{c.lead}</p>
      <div class="cloud" role="group" aria-label={title} data-testid="cloud">
        {view.map((word) => (
          <button
            key={word.id}
            type="button"
            class={`word s${word.size}${word.picked ? " picked" : ""}${word.fresh ? " fresh" : ""}`}
            aria-pressed={word.picked}
            data-testid={`word-${word.id}`}
            data-size={word.size}
            onClick={() => tap(word)}
          >
            {word.word}
            {word.picked && word.term && <span class="term" data-testid="term">{` (${word.term})`}</span>}
          </button>
        ))}
      </div>
      <Status text={status} testId="cloud-status" />
      <Pill quiet onClick={() => setShowAll(!showAll)} testId="more-words">
        {showAll ? c.fewer : c.more}
      </Pill>
      <Sheet glass lines={[c.lead, c.lead2, c.lead3]} testId="cloud-lead" />
      <Notice error={error} />
      <Pill plum onClick={() => void done()} disabled={busy || !conditions.value} testId="cloud-done">
        {picked.value.length > 0 ? c.done : s.onboarding.next}
      </Pill>
    </main>
  );
}
