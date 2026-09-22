import { useEffect, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AppointmentOut, PaperInsightKeepOut, ReviewCardOut } from "../api/types";
import { openMe } from "../flow";
import {
  cardVisitOf,
  initialPaperInsightState,
  lookedAtLabels,
  paperInsightHasNothingToAsk,
  paperInsightStatusText,
  withPaperInsightReport,
  withPaperInsightStep,
  type PaperInsightStreamState,
} from "../health/paperInsight";
import { fill, language, LOCALE, t } from "../strings";
import { profile, token } from "../store/session";
import { dayMonthLine } from "../today/model";
import { focusHeading } from "../ui/focus";
import { Notice } from "../ui/components";
import { Chip, ChipRow, ConnectionRow, Glass, Icon, Orb, SoftText, StatusLine, ThreeStateButton } from "../ui/kit";
import { recordNote, toRecord } from "./record/parts";
import { Shell } from "./Shell";

/** Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html` scene
 *  `insight`, package 7): the screen right after a paper is confirmed — the blueprint's own
 *  shape, like for like: the small orb beside the one status line while the stream works, the
 *  same orb beside the headline once it has (Ask's own "a finished turn keeps its orb"
 *  precedent); "Looked at" as quiet chips, only what the stream really named; one glass card,
 *  "For {doctor} on {date}" (the next visit's own real fields) or "For your next visit", the
 *  questions inside it as plain paragraphs; "Keep these for my visit" (three states), the
 *  ConnectionRow line under it once kept; "Not now". Reused, unchanged, between two callers —
 *  onboarding's own bare step (`screens/onboarding/Insight.tsx`) and the Record's Papers
 *  flow's top-level screen, below — so the streaming and the keep behaviour are one
 *  implementation, never two. */

interface PaperInsightViewProps {
  /** The just-confirmed card — freshly returned by `confirmReviewCard`, with any correction
   *  already merged into its fields. */
  card: ReviewCardOut;
  /** The one way on, before and after "Keep": always "Not now" (the blueprint's own words) —
   *  where it actually goes is the caller's own (the Record's Papers list, or onboarding's own
   *  next step), never this component's concern. */
  onLeave: () => void;
  testId?: string;
}

export function PaperInsightView({ card, onLeave, testId }: PaperInsightViewProps): JSX.Element {
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
  const [visits, setVisits] = useState<AppointmentOut[]>([]);
  const [keepResult, setKeepResult] = useState<PaperInsightKeepOut | null>(null);
  const [keepError, setKeepError] = useState<unknown>(null);
  // With no upcoming visit, the backend keeps nothing at all (#303 review, B3, the honest
  // fallback: `filed` is `"unfiled"`, `kept_count` is `0`) — never `keepResult`, so the
  // three-state button is never shown as "Kept" for a keep that did not really happen.
  const [keepNoVisit, setKeepNoVisit] = useState(false);

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

  // The next visit's own doctor and date, for the card's own title — the same real read
  // `screens/tabs.tsx`'s own `VisitList` already makes (`nura.appointments`, soonest first),
  // reused here rather than a new route: no visit booked, or one with no doctor named yet,
  // never invents either.
  useEffect(() => {
    const bearer = token.value;
    if (!bearer || !papers) return;
    nura.appointments(bearer, papers.profile_id).then(setVisits, () => setVisits([]));
  }, [papers?.profile_id]);

  const report = stream.report;

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
    let result: PaperInsightKeepOut;
    try {
      result = await nura.keepPaperInsight(bearer, papers.profile_id, card.artifact_id);
    } catch (failure) {
      if (mountedRef.current) setKeepError(failure);
      throw failure;
    }
    if (!mountedRef.current) return;
    if (result.filed !== "visit") {
      // No upcoming visit: the honest fallback (#303 review, B3) — nothing was kept at all,
      // so the three-state button is told this failed (reverts to idle, never "Kept") and
      // the screen says plainly why, instead.
      setKeepNoVisit(true);
      setKeepError(null);
      throw new Error("no visit booked");
    }
    setKeepResult(result);
    setKeepError(null);
    setKeepNoVisit(false);
  };

  const statusText = paperInsightStatusText(stream, s.feed.askThinking);
  const nothingToAsk = report ? paperInsightHasNothingToAsk(report) : false;
  const lookedAt = report ? lookedAtLabels(report) : [];
  // "Nothing kept" is two lines, one idea each — `plain-words` rule 2, "one idea per line".
  const keepNoVisitLines = (self ? p.keepNoVisit : p.keepNoVisitOther).map((line) => fill(line, { patient: patientName }));
  const keepLabel = self ? p.keepForVisit : fill(p.keepForVisitOther, { patient: patientName });

  const visit = cardVisitOf(visits);
  const cardTitle =
    visit.kind === "named"
      ? fill(p.forDoctorOn, { doctor: visit.doctor, date: dayMonthLine(new Date(visit.scheduledAt), locale) })
      : self
        ? p.forNextVisit
        : fill(p.forNextVisitOther, { patient: patientName });

  return (
    <div data-testid={testId} class="insight-blocks">
      <Notice error={error} />
      {!report && !error && (
        <div class="insight-turn" data-testid="insight-thinking">
          <Orb thinking={busy} testId="insight-orb" />
          <StatusLine text={statusText} testId="insight-status" />
        </div>
      )}
      {/* The stream refused (a scope this key does not hold, a closing account) or the network
         did not answer at all: the backend's own sentence is already said above (`Notice`), and
         a way on either way — retry only really helps a network failure, but showing it beside
         "Not now" on a refusal too costs nothing and is never wrong, since a repeat refusal
         only says the same sentence again. Never a dead end with nothing left to tap. */}
      {!report && error && (
        <div class="insight-actions">
          <button type="button" class="btn" onClick={load} disabled={busy} data-testid="insight-retry">
            {s.errors.tryAgain}
          </button>
          <button type="button" class="btn" onClick={onLeave} data-testid="insight-leave">
            {p.notNow}
          </button>
        </div>
      )}
      {report && (
        <>
          <div class="insight-turn" data-testid="insight-turn">
            <Orb testId="insight-orb" />
            <SoftText as="h2" pace="headline" className="conversation-head" text={report.headline} testId="insight-headline" />
          </div>
          {lookedAt.length > 0 && (
            <ChipRow testId="insight-looked-at">
              <span class="caption" data-testid="insight-looked-at-label">
                {p.lookedAt}
              </span>
              {lookedAt.map((label) => (
                <Chip key={label}>{label}</Chip>
              ))}
            </ChipRow>
          )}
          {!nothingToAsk && (
            <Glass shape="card" testId="insight-card">
              <h3>{cardTitle}</h3>
              {report.questions.map((question) => (
                <p key={question.insight_id} data-testid="insight-question">
                  {question.text}
                </p>
              ))}
            </Glass>
          )}
          <p class="note" data-testid="insight-safety">
            {p.questionsNotAnswers} {r.safetyNotAdvice}
          </p>
          {!nothingToAsk && (
            <div class="insight-actions">
              <ThreeStateButton label={keepLabel} busyLabel={p.keeping} doneLabel={p.kept} onAct={keep} testId="insight-keep" />
              {keepResult && (
                <ConnectionRow
                  name={self ? p.keptForVisit : fill(p.keptForVisitOther, { patient: patientName })}
                  trailing={<Icon name="check" />}
                  testId="insight-kept-where"
                />
              )}
              {keepNoVisit && (
                <p class="note" data-testid="insight-keep-no-visit">
                  {keepNoVisitLines[0]} {keepNoVisitLines[1]}
                </p>
              )}
              <Notice error={keepError} />
            </div>
          )}
          <button type="button" class="btn" onClick={onLeave} data-testid="insight-leave">
            {p.notNow}
          </button>
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

/** The Record's Papers flow (`onDone`, `screens/record/Papers.tsx`'s `PaperScreen`) and Home's
 *  own single-report "Add a paper" (`screens/Papers.tsx`, D-5): a full, Shell-wrapped screen,
 *  tab bar included, reached with `go({ name: "insight", card })`. Onboarding reaches the same
 *  content through its own bare step instead (`screens/onboarding/Insight.tsx`), never this
 *  wrapper — onboarding has no tab bar until it is done. The way back is always "back to your
 *  papers", from both callers, so its own leaving is never asked of a caller the way
 *  `PaperInsightView`'s other prop, `card`, is. */
export function InsightScreen({ card }: { card: ReviewCardOut }): JSX.Element {
  const s = t();
  const papers = profile.value;
  const self = papers?.standing === "owner";
  const patientName = papers?.display_name ?? "";
  const title = self ? s.paperInsight.screenTitle : fill(s.paperInsight.screenTitleOther, { patient: patientName });
  const backLabel = self ? s.record.back : fill(s.record.backOther, { patient: patientName });
  const leave = () => {
    recordNote.value = [s.onboarding.records.saved];
    toRecord({ name: "papers" });
  };
  return (
    <Shell tab="health" testId="insight-screen" ask={false} header={<InsightHeader title={title} onBack={leave} backLabel={backLabel} meLabel={s.tabs.me} />}>
      <PaperInsightView card={card} onLeave={leave} testId="insight-body" />
    </Shell>
  );
}
