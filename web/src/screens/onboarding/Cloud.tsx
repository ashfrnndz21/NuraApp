import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import { saveWordsAndGoOn } from "../../onboarding/actions";
import { asksFor, cloudView, foldTold, packCloud, phaseOf, tapHint, toggle, type CloudWord } from "../../onboarding/cloud";
import { answers, conditions, picked, say, to, whose } from "../../onboarding/state";
import { speak } from "../../speech/speak";
import { token } from "../../store/session";
import { fill, language, t } from "../../strings";
import { Field, Notice, Pill } from "../../ui/components";
import { Icon, Orb, Reveal, SoftText } from "../../ui/kit";
import { Sheet, Status } from "./parts";

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

  // Nura's one line under the cloud, in his own words or hers (say(), the same self/other
  // dispatch every other turn on this screen already uses) — `{who}` only ever appears in the
  // "other" half of each pair.
  const hintTemplates = {
    picked: say(c.pickedPlainSelf, c.pickedPlainOther),
    added: say(c.pickedAddedSelf, c.pickedAddedOther),
    removed: say(c.removedSelf, c.removedOther),
    removedSub: c.removedSub,
  };

  const tap = (word: CloudWord) => {
    const next = toggle(words, picked.value, word.code);
    const nowPicked = next.includes(word.code);
    picked.value = next;
    answers.value = Object.fromEntries(Object.entries(answers.value).filter(([code]) => next.includes(code)));
    setLastPicked(nowPicked ? word.code : null);
    setStatus(tapHint(word, nowPicked, hintTemplates, { who: whose().name }));
    if (nowPicked) speak({ lines: word.term ? [word.name, fill(c.term, { term: word.term })] : [word.name], language: language.value });
  };

  /** A picked word's own follow-up ("For how long?"), answered right here under the cloud
   *  (docs/design/onboarding-mock.html `renderAsk()`) — never the separate `asks` screen a tap
   *  used to leave for. A second tap changes the answer; there is no toggle-off, the same as
   *  the screen this replaces — leaving it unanswered is simply not tapping it. */
  const chooseAsk = (wordId: string, optionId: string) => {
    answers.value = { ...answers.value, [wordId]: optionId };
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
  const head = say(c.headSelf, c.headOther);
  const asks = asksFor(words, picked.value);
  const { circles, height } = packCloud(view);
  return (
    <main class="screen onboarding" data-stage="cloud">
      {/* The conversation head (docs/design/experience-blueprint.html `cloud` scene: "What is
          part of your health? Tap what fits." beside the orb, 25px light) — never a title over
          a separate grey subtitle. */}
      <div class="who-say">
        <Orb size="sm" />
        <SoftText text={head} pace="headline" as="h1" className="who-say-line conversation-head" testId="cloud-head" />
      </div>
      {/* The bubble cloud (docs/design/experience-blueprint.html `cloud` scene): a floating
          cloud of different-sized circles — the word's own weight, `onboarding/cloud.ts`'s own
          `sizeOf` — scattered and drifting, never a grid of same-sized pills. `packCloud` places
          every circle once, in `view`'s own order, so Tab still walks it in reading order; only
          where each one SITS is new here, the tap target and its hit box (a tick and heavier
          weight mark a pick, never colour alone, WCAG 1.4.1) are exactly what they always were.
          Each bubble's own `phaseOf(word.code)` gives its drift a different delay and duration
          (on the inner `.bubble-surface`, never the button itself) so neighbours never move in
          lockstep. */}
      <div class="cloud bubble-cloud" role="group" aria-label={title} data-testid="cloud" style={{ height: `${height}px` }}>
        {circles.map((word, at) => {
          const phase = phaseOf(word.code);
          return (
            <button
              key={word.code}
              type="button"
              class={`word bubble s${word.size}${word.picked ? " picked" : ""}${word.fresh ? " fresh" : ""}`}
              aria-pressed={word.picked}
              data-testid={`word-${word.code}`}
              data-size={word.size}
              onClick={() => tap(word)}
              style={{ left: `${word.leftPercent}%`, top: `${word.top}px`, width: `${word.diameter}px`, height: `${word.diameter}px` }}
            >
              <span class="bubble-surface" aria-hidden="true" style={{ animationDelay: `${-phase * 7}s`, animationDuration: `${5 + phase * 3}s` }} />
              {word.picked && (
                <span class="bubble-tick" aria-hidden="true">
                  <Icon name="check" />
                </span>
              )}
              {word.name}
              {word.picked && word.term && <span class="term" data-testid="term">{` (${word.term})`}</span>}
            </button>
          );
        })}
      </div>
      {/* A picked word's own follow-up, right under the cloud (docs/design/onboarding-mock.html
          `renderAsk()`) — never a screen of its own any more (`Asks.tsx` still answers that
          question when a gap card reopens exactly one of these later). Answering one, or
          leaving it, never blocks "That is everything" below. */}
      {asks.length > 0 && (
        <div class="cloud-asks" data-testid="cloud-asks">
          <p class="caption">{s.onboarding.asks.lead}</p>
          {asks.map((word) => (
            <Reveal key={word.code}>
              <Sheet caption={word.name} title={word.ask!.question} testId={`ask-${word.code}`}>
                <div class="choices" role="group">
                  {word.ask!.options.map((option) => (
                    <Pill key={option.id} onClick={() => chooseAsk(word.code, option.id)} chosen={answers.value[word.code] === option.id} testId={`option-${option.id}`}>
                      {option.text}
                    </Pill>
                  ))}
                </div>
              </Sheet>
            </Reveal>
          ))}
        </div>
      )}
      {/* Nura's own line, changed in place on every tap (docs/design/onboarding-mock.html
          `pick()`'s own `cloudmsg`) — what this one tap just did, never an accumulating list of
          everything picked so far. */}
      {status && (
        <div class="cloud-ack" data-testid="cloud-ack">
          <Orb size="sm" />
          <Status text={status} testId="cloud-status" />
        </div>
      )}
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
