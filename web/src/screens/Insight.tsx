import { useEffect, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { PaperInsightKeepOut, ReviewCardOut } from "../api/types";
import { openMe } from "../flow";
import {
  hasQuestionSelection,
  initialPaperInsightState,
  initialQuestionSelection,
  paperInsightHasNothingToAsk,
  paperInsightStatusText,
  standoutRows,
  toggleQuestionSelection,
  whereKept,
  withPaperInsightReport,
  withPaperInsightStep,
  type PaperInsightStreamState,
  type QuestionSelection,
} from "../health/paperInsight";
import { fill, language, LOCALE, t } from "../strings";
import { profile, token } from "../store/session";
import { focusHeading } from "../ui/focus";
import { Notice } from "../ui/components";
import { ConnectionRow, Flag, Glass, Icon, Orb, RevealGroup, SoftText, StatusLine, ThreeStateButton } from "../ui/kit";
import { recordNote, toRecord } from "./record/parts";
import { Shell } from "./Shell";

/** Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html` scene
 *  `insight`, package 7): the screen right after a paper is confirmed. Reused, unchanged,
 *  between two callers — onboarding's own bare step (`screens/onboarding/Insight.tsx`) and the
 *  Record's Papers flow's top-level screen, below — so the streaming, the selection and the
 *  keep behaviour are one implementation, never two. Nothing here is invented: the status line
 *  is only ever the backend's own next real step (`paperInsightStream`'s `onStep`), the
 *  headline and the questions are only ever `PaperInsightOut`'s own fields, and "what stands
 *  out" is computed off the confirmed card's own printed ranges — the same `reportRow` the
 *  report table already draws every row through. */

interface PaperInsightViewProps {
  /** The just-confirmed card — freshly returned by `confirmReviewCard`, with any correction
   *  already merged into its fields (never the stale, pre-confirm object): "what stands out"
   *  reads straight off it, with no second fetch. */
  card: ReviewCardOut;
  /** The one way on, before and after "Keep": onboarding's own "Next" back to the step that
   *  would have come next, or the Record's own "Back to your papers" — never invented here,
   *  always the caller's own words and the caller's own navigation. */
  leaveLabel: string;
  onLeave: () => void;
  testId?: string;
}

export function PaperInsightView({ card, leaveLabel, onLeave, testId }: PaperInsightViewProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const p = s.paperInsight;
  const locale = LOCALE[language.value];
  const papers = profile.value;
  const self = papers?.standing === "owner";
  const patientName = papers?.display_name ?? "";

  const [stream, setStream] = useState<PaperInsightStreamState>(initialPaperInsightState);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState<QuestionSelection>(new Set());
  const [keepResult, setKeepResult] = useState<PaperInsightKeepOut | null>(null);
  const [keepError, setKeepError] = useState<unknown>(null);

  const mountedRef = useRef(true);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      mountedRef.current = false;
      // Leaving the screen aborts the stream: no event, and no state update from one, ever
      // reaches a caller after this.
      controllerRef.current?.abort();
    },
    [],
  );

  const load = () => {
    const bearer = token.value;
    if (!bearer || !papers) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setStream(initialPaperInsightState);
    setError(null);
    setBusy(true);
    nura
      .paperInsightStream(
        bearer,
        papers.profile_id,
        card.artifact_id,
        (key, label) => {
          if (mountedRef.current) setStream((was) => withPaperInsightStep(was, key, label));
        },
        controller.signal,
      )
      .then((report) => {
        if (!mountedRef.current) return;
        setStream((was) => withPaperInsightReport(was, report));
      })
      .catch((failure: unknown) => {
        // An abort (leaving the screen, or a retry starting a fresh stream) is not a failure
        // to show: the controller that owns it already knows, and a stale one's rejection
        // must never paint over what a newer attempt is doing.
        if (!mountedRef.current || controller.signal.aborted) return;
        setError(failure);
      })
      .finally(() => {
        if (mountedRef.current && controllerRef.current === controller) setBusy(false);
      });
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [card.artifact_id]);

  const report = stream.report;
  useEffect(() => {
    if (report) setSelection(initialQuestionSelection(report.questions));
  }, [report?.report_id]);

  // The headline only exists once the real report has landed (never before: no invented
  // heading while Nura is still working) — so the app's own on-arrival focus (`app.tsx`'s
  // `focusHeading()` on the screen's first paint) is given again once it does, the same way
  // `Today.tsx`'s own heading, which also settles late, re-gives it (`useHomeHero`).
  useEffect(() => {
    if (report) focusHeading();
  }, [report?.report_id]);

  const keep = async () => {
    const bearer = token.value;
    if (!bearer || !papers) throw new Error("no session");
    try {
      const result = await nura.keepPaperInsight(bearer, papers.profile_id, card.artifact_id);
      if (mountedRef.current) {
        setKeepResult(result);
        setKeepError(null);
      }
    } catch (failure) {
      if (mountedRef.current) setKeepError(failure);
      throw failure;
    }
  };

  const rows = standoutRows(card, s, locale);
  const questionsTitle = self ? p.questionsTitle : fill(p.questionsTitleOther, { patient: patientName });
  const statusText = paperInsightStatusText(stream, s.feed.askThinking);
  const nothingToAsk = report ? paperInsightHasNothingToAsk(report) : false;
  const kept = whereKept({ filed: keepResult?.filed ?? "unfiled" });
  // "Kept for your next visit." (one line), or "Kept." / "Nura will add these once a visit is
  // booked." (two: `keptUnfiled` is two ideas, `plain-words` rule 2's own "one idea per line" —
  // ConnectionRow's own bold-name-then-small-line shape fits it exactly, so the two ideas are
  // never rejoined into one line here).
  const keptUnfiledLines = (self ? p.keptUnfiled : p.keptUnfiledOther).map((line) => fill(line, { patient: patientName }));

  return (
    <div data-testid={testId}>
      <Notice error={error} />
      {!report && !error && (
        <div class="report-row-top" data-testid="insight-thinking">
          <Orb thinking={busy} testId="insight-orb" />
          <StatusLine text={statusText} testId="insight-status" />
        </div>
      )}
      {/* The stream refused (a scope this key does not hold, a closing account) or the network
         did not answer at all: the backend's own sentence is already said above (`Notice`), and
         a way on either way — retry only really helps a network failure, but showing it beside
         "leave" on a refusal too costs nothing and is never wrong, since a repeat refusal only
         says the same sentence again. Never a dead end with nothing left to tap. */}
      {!report && error && (
        <div class="acts">
          <button type="button" class="btn" onClick={load} disabled={busy} data-testid="insight-retry">
            {s.errors.tryAgain}
          </button>
          <button type="button" class="btn" onClick={onLeave} data-testid="insight-leave">
            {leaveLabel}
          </button>
        </div>
      )}
      {report && (
        <>
          <SoftText as="h2" pace="headline" className="conversation-head" text={report.headline} testId="insight-headline" />
          {rows.length > 0 && (
            <>
              <p class="kick" data-testid="insight-standout-title">
                {p.standsOutTitle}
              </p>
              <RevealGroup testId="insight-standout-rows">
                {rows.map((row) => (
                  <Glass key={row.fieldId} shape="row" testId={`insight-standout-row-${row.fieldId}`}>
                    <div class="report-row-top">
                      <div class="report-row-name">
                        <b>{row.label}</b>
                      </div>
                      <span class="report-value-num">
                        {row.valueText}
                        {row.unit && <small>{row.unit}</small>}
                      </span>
                      {row.flagWord && <Flag state={row.tone === "ok" ? "ok" : "attention"}>{row.flagWord}</Flag>}
                    </div>
                  </Glass>
                ))}
              </RevealGroup>
            </>
          )}
          {!nothingToAsk && (
            <>
              <p class="kick" data-testid="insight-questions-title">
                {questionsTitle}
              </p>
              <RevealGroup testId="insight-questions">
                {report.questions.map((question) => (
                  <Glass key={question.insight_id} shape="row" testId="insight-question-row">
                    <label class="check">
                      <input
                        type="checkbox"
                        checked={selection.has(question.insight_id)}
                        onChange={() => setSelection((was) => toggleQuestionSelection(was, question.insight_id))}
                        data-testid="insight-question-checkbox"
                      />
                      <span>{question.text}</span>
                    </label>
                  </Glass>
                ))}
              </RevealGroup>
            </>
          )}
          <p class="note" data-testid="insight-safety">
            {self ? p.standoutSafety : fill(p.standoutSafetyOther, { patient: patientName })} {r.safetyNotAdvice}
          </p>
          {!nothingToAsk && (
            <div class="acts">
              <ThreeStateButton
                label={p.keepQuestions}
                busyLabel={p.keeping}
                doneLabel={p.kept}
                onAct={keep}
                disabled={!hasQuestionSelection(selection)}
                testId="insight-keep"
              />
              <button type="button" class="btn" onClick={onLeave} data-testid="insight-leave">
                {leaveLabel}
              </button>
            </div>
          )}
          {nothingToAsk && (
            <button type="button" class="btn light" onClick={onLeave} data-testid="insight-leave">
              {leaveLabel}
            </button>
          )}
          <Notice error={keepError} />
          {keepResult &&
            (kept.kind === "visit" ? (
              <ConnectionRow name={self ? p.keptForVisit : fill(p.keptForVisitOther, { patient: patientName })} trailing={<Icon name="check" />} testId="insight-kept-where" />
            ) : (
              <ConnectionRow name={keptUnfiledLines[0] ?? ""} line={keptUnfiledLines[1]} trailing={<Icon name="check" />} testId="insight-kept-where" />
            ))}
        </>
      )}
    </div>
  );
}

/** The compact header a nested screen owns for itself (the same seam `screens/Ask.tsx`'s own
 *  `AskHeader` draws it through, layout fix docs/design/experience-blueprint.html `head()`):
 *  one row, back · the screen's own `<h1>` · the menu, in place of the global
 *  menu+wordmark+switcher+bell header — never the board's own `topBar`, which is reserved for
 *  the five tab-root screens alone (`Shell.tsx`'s own `TopBarSpec` doc) and whose back button
 *  is hard-wired to Home, wrong for a screen reached from the Record's own Papers list. */
function InsightHeader({ title, onBack, backLabel, meLabel }: { title: string; onBack: () => void; backLabel: string; meLabel: string }): JSX.Element {
  return (
    <header class="shell-head board-top-bar" data-testid="insight-top-bar">
      <span class="head-start">
        <button type="button" class="head-button" aria-label={backLabel} onClick={onBack} data-testid="insight-back">
          <Icon name="back" />
        </button>
      </span>
      <span class="head-mid">
        <h1 class="title top-bar-title">{title}</h1>
      </span>
      <span class="head-end">
        <button type="button" class="head-button" aria-label={meLabel} aria-haspopup="dialog" onClick={openMe} data-testid="open-me">
          <Icon name="menu" />
        </button>
      </span>
    </header>
  );
}

/** The Record's Papers flow (`onDone`, `screens/record/Papers.tsx`'s `PaperScreen`): a full,
 *  Shell-wrapped screen, tab bar included, reached with `go({ name: "insight", card })`.
 *  Onboarding reaches the same content through its own bare step instead
 *  (`screens/onboarding/Insight.tsx`), never this wrapper — onboarding has no tab bar until it
 *  is done. The way back is always "back to your papers": the one place this screen is ever
 *  reached from, so its own leaving is never asked of a caller the way `PaperInsightView`'s
 *  other prop, `card`, is. */
export function InsightScreen({ card }: { card: ReviewCardOut }): JSX.Element {
  const s = t();
  const papers = profile.value;
  const self = papers?.standing === "owner";
  const patientName = papers?.display_name ?? "";
  const title = self ? s.paperInsight.screenTitle : fill(s.paperInsight.screenTitleOther, { patient: patientName });
  const leaveLabel = self ? s.record.back : fill(s.record.backOther, { patient: patientName });
  const leave = () => {
    recordNote.value = [s.onboarding.records.saved];
    toRecord({ name: "papers" });
  };
  return (
    <Shell tab="health" testId="insight-screen" ask={false} header={<InsightHeader title={title} onBack={leave} backLabel={leaveLabel} meLabel={s.tabs.me} />}>
      <PaperInsightView card={card} leaveLabel={leaveLabel} onLeave={leave} testId="insight-body" />
    </Shell>
  );
}
