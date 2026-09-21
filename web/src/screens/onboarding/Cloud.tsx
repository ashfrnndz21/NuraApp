import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import { saveWordsAndGoOn } from "../../onboarding/actions";
import { acknowledgementLine, asksFor, cloudView, foldTold, toggle, type CloudWord } from "../../onboarding/cloud";
import { answers, conditions, picked, say, to, whose } from "../../onboarding/state";
import { speak } from "../../speech/speak";
import { token } from "../../store/session";
import { fill, language, t } from "../../strings";
import { Field, Notice, Pill } from "../../ui/components";
import { Icon, Orb, SoftText } from "../../ui/kit";
import { Sheet, Status, StepTitle } from "./parts";

/** The word cloud (#117's graph): plain words, the most common biggest and first, so they are
 *  on the screen without scrolling. A tap picks a word, says it aloud (its spoken twin — audio
 *  only ever on a tap), and brings in the words that often go with it, which grow with every
 *  pick that points at them. The clinic's word shows in brackets when the backend sends one.
 *  "That is everything" saves the words with About you's answers, in one PUT. */
export function CloudStep(): JSX.Element {
  const s = t();
  const c = s.onboarding.cloud;
  const bearer = token.value;
  const [showAll, setShowAll] = useState(false);
  const [lastPicked, setLastPicked] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [tellOpen, setTellOpen] = useState(false);
  const [tellText, setTellText] = useState("");
  const [tellBusy, setTellBusy] = useState(false);
  const [tellSafety, setTellSafety] = useState(false);

  useEffect(() => {
    if (!bearer || conditions.value?.language === language.value) return;
    nura.conditions(bearer, language.value).then((found) => (conditions.value = found), setError);
  }, [bearer, language.value]);

  const words = conditions.value?.conditions ?? [];
  const view = cloudView(words, picked.value, { showAll, lastPicked });

  const tap = (word: CloudWord) => {
    const next = toggle(words, picked.value, word.code);
    const nowPicked = next.includes(word.code);
    picked.value = next;
    answers.value = Object.fromEntries(Object.entries(answers.value).filter(([code]) => next.includes(code)));
    setLastPicked(nowPicked ? word.code : null);
    setStatus(nowPicked ? c.noted : c.removed);
    if (nowPicked) speak({ lines: word.term ? [word.name, fill(c.term, { term: word.term })] : [word.name], language: language.value });
  };

  /** "Or just tell me": free text run through the backend's tagger (`POST /onboarding/tell-
   *  me`). Nothing he typed leaves this function once it returns — only the codes it tagged
   *  are kept, folded into what is already picked, exactly as a tap would leave it. A red word
   *  tags no pill at all: the safety line shows instead, and his words are cleared, never sent
   *  anywhere else. */
  const sendTellMe = async () => {
    const said = tellText.trim();
    if (!said) return;
    setTellBusy(true);
    setError(null);
    try {
      const told = await nura.tellMe(said);
      setTellText("");
      if (told.red_flag) {
        setTellSafety(true);
        setStatus(null);
        return;
      }
      setTellSafety(false);
      if (told.conditions.length === 0) {
        setStatus(`${c.tellMeNothing} ${c.tellMeNothingSub}`);
        return;
      }
      const next = foldTold(picked.value, told.conditions);
      picked.value = next;
      setLastPicked(told.conditions[told.conditions.length - 1] ?? null);
      setStatus(c.noted);
      setTellOpen(false);
    } catch (failure) {
      setError(failure);
    } finally {
      setTellBusy(false);
    }
  };

  const done = async () => {
    if (asksFor(words, picked.value).length > 0) return to({ name: "asks" });
    setBusy(true);
    setError(null);
    try {
      await saveWordsAndGoOn();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const title = say(c.titleSelf, c.titleOther);
  const pickedWords = view.filter((word) => word.picked);
  const ack = acknowledgementLine(pickedWords, say(c.ackSelf, c.ackOther), c.and, { name: whose().name });
  return (
    <main class="screen onboarding" data-stage="cloud">
      <StepTitle title={title} />
      <p class="lead">{c.lead}</p>
      {/* The bubble cloud (docs/design/experience-blueprint.html `cloud` scene): floating,
          tappable bubbles, sized by how common the word is; a tick and heavier weight mark a
          pick, never colour alone (WCAG 1.4.1). The words, sizes, order and every test id below
          are exactly what the plain word-cloud markup this replaces already had — only the
          shape and the drift are new. */}
      <div class="cloud bubble-cloud" role="group" aria-label={title} data-testid="cloud">
        {view.map((word) => (
          <button
            key={word.code}
            type="button"
            class={`word bubble s${word.size}${word.picked ? " picked" : ""}${word.fresh ? " fresh" : ""}`}
            aria-pressed={word.picked}
            data-testid={`word-${word.code}`}
            data-size={word.size}
            onClick={() => tap(word)}
          >
            <span class="bubble-surface" aria-hidden="true" />
            {word.picked && (
              <span class="bubble-tick" aria-hidden="true">
                <Icon name="check" />
              </span>
            )}
            {word.name}
            {word.picked && word.term && <span class="term" data-testid="term">{` (${word.term})`}</span>}
          </button>
        ))}
      </div>
      {ack && (
        <div class="cloud-ack">
          <Orb size="sm" />
          <SoftText text={ack} pace="body" as="p" className="cloud-ack-line" testId="cloud-ack" />
        </div>
      )}
      <Status text={status} testId="cloud-status" />
      <p class="caption" data-testid="cloud-count">
        {picked.value.length > 0 ? fill(c.count, { n: picked.value.length }) : c.countNone}
      </p>
      <Pill quiet onClick={() => setShowAll(!showAll)} testId="more-words">
        {showAll ? c.fewer : c.more}
      </Pill>
      <Pill quiet onClick={() => setTellOpen(!tellOpen)} testId="tell-me-open">
        {c.tellMe}
      </Pill>
      {tellOpen && (
        <Sheet lines={[c.tellMeLead]} testId="tell-me">
          <Field
            name="tell-me"
            label={c.tellMeLabel}
            value={tellText}
            onInput={setTellText}
            disabled={tellBusy}
            big
          />
          <Pill plum onClick={() => void sendTellMe()} disabled={tellBusy || !tellText.trim()} testId="tell-me-send">
            {c.tellMeSend}
          </Pill>
        </Sheet>
      )}
      {tellSafety && <Sheet lines={[c.tellMeSafety, c.tellMeSafetySub]} testId="tell-me-safety" />}
      <Sheet glass lines={[c.lead, c.lead2, c.lead3]} testId="cloud-lead" />
      <Notice error={error} />
      <Pill plum onClick={() => void done()} disabled={busy || !conditions.value} testId="cloud-done">
        {picked.value.length > 0 ? c.done : s.onboarding.next}
      </Pill>
    </main>
  );
}
