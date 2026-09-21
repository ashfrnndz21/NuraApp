import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { PromptOut } from "../../api/types";
import { sendPaperStream } from "../../capture/session";
import { planInMyLanguage, refreshPlan, who } from "../../onboarding/actions";
import { dayLine } from "../../onboarding/dates";
import { cardsToShow, invites, opensCamera, opensFile, tapsSetting } from "../../onboarding/plan";
import { closed, finish, plan, planNote, returnTo, to, whose } from "../../onboarding/state";
import { density, profile } from "../../store/session";
import { fill, language, LOCALE, t } from "../../strings";
import { Hear, Notice, Pill } from "../../ui/components";
import { ReadingProgress } from "./PaperReading";
import { usePaperTrace } from "./paperTrace";
import { Capture, Sheet, Status, StepTitle } from "./parts";

/** The Ready screen (#117's close and first week, docs/gaps-and-unlocks.md): the sitting's own
 *  closing words and summary, then the prompts still to do — one for the patient (the next, and
 *  how many follow), every one for the caregiver. "Do it now" opens what the backend says fills
 *  the gap: the camera, a file (a PDF), the one question (his breakfast), or the invite (on
 *  his own papers). The sitting's closing words address him, so a chief reads the app's own.
 *  "Later" sends it to the back of the week. Then Today. */
export function PlanStep(): JSX.Element {
  const s = t();
  const p = s.onboarding.plan;
  const r = s.onboarding.records;
  const patient = density() === "patient";
  const [status, setStatus] = useState<string | null>(planNote.value);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const paper = usePaperTrace();

  useEffect(() => {
    if (!plan.value) refreshPlan().catch(setError);
  }, [language.value]);

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

  const later = (prompt: PromptOut) =>
    act(async () => {
      const { bearer, profileId } = who();
      plan.value = await planInMyLanguage(await nura.laterOnPlan(bearer, profileId, prompt.prompt));
      setStatus(p.laterSaid);
    });

  const doItNow = (file: File) =>
    act(async () => {
      returnTo.value = "plan";
      paper.start();
      try {
        to({ name: "review", card: await sendPaperStream(file, paper.onStep) });
      } finally {
        paper.stop();
      }
    });

  const done = closed.value;
  const own = whose().self;
  const { shown, after } = cardsToShow(plan.value, density());
  const locale = LOCALE[language.value];
  return (
    <main class="screen onboarding" data-stage="plan">
      <StepTitle title={(own && done?.biography.prompt.headline) || p.title} />
      {own && done && done.biography.prompt.lines.length > 0 && <Sheet lines={done.biography.prompt.lines} testId="done-prompt" />}
      {done && done.summary.lines.length > 0 && <Sheet lines={done.summary.lines} testId="summary" />}
      <Sheet glass lines={[p.lead, p.cadence1, p.cadence2]} testId="cadence" />
      {shown.map((prompt) => {
        const when = fill(p.onDay, { date: dayLine(prompt.due_local.slice(0, 10), locale) });
        return (
          <section key={prompt.prompt} class="tile paper gap" data-testid="gap-card" data-gap={prompt.prompt} data-state-id={prompt.state_id}>
            <p class="caption">{p.missing}</p>
            {prompt.headline && <h2 class="title">{prompt.headline}</h2>}
            {prompt.line && <p>{prompt.line}</p>}
            <p class="caption">{when}</p>
            {opensCamera(prompt) && <Capture onFile={(file) => void doItNow(file)} busy={busy} photoLabel={prompt.action ?? r.photo} plum={patient} withFile={false} />}
            {opensFile(prompt) && <Capture onFile={(file) => void doItNow(file)} busy={busy} photoLabel={prompt.action ?? r.file} plum={patient} fileOnly />}
            {tapsSetting(prompt) && (
              <Pill
                plum={patient}
                onClick={() => {
                  returnTo.value = "plan";
                  to({ name: "about", only: tapsSetting(prompt)! });
                }}
                disabled={busy}
                testId="do-it-now"
              >
                {prompt.action ?? p.later}
              </Pill>
            )}
            {invites(prompt, profile.value?.standing) && (
              <Pill plum={patient} onClick={() => to({ name: "invite" })} disabled={busy} testId="do-it-now">
                {prompt.action ?? p.later}
              </Pill>
            )}
            <Pill quiet onClick={() => void later(prompt)} disabled={busy} testId="later">
              {p.later}
            </Pill>
            {prompt.source && (
              <p class="provenance" data-testid="source">
                {prompt.source}
              </p>
            )}
            <Hear lines={[prompt.headline, prompt.line, when].filter((line): line is string => Boolean(line))} />
          </section>
        );
      })}
      {after > 0 && (
        <p class="lead" data-testid="more-after">
          {after === 1 ? p.moreOne : fill(p.more, { count: after })}
        </p>
      )}
      {plan.value && shown.length === 0 && <Sheet lines={[p.nothing]} testId="plan-nothing" />}
      {paper.sending && <ReadingProgress status={paper.trace.length > 0 ? paper.trace[paper.trace.length - 1]!.text : r.looking} testId="plan-looking" />}
      <Status text={status} testId="plan-status" />
      <Notice error={error} />
      <Pill plum={!patient} onClick={finish} disabled={busy} testId="open-nura">
        {p.open}
      </Pill>
    </main>
  );
}
