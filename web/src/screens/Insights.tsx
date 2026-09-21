import { useEffect, useReducer, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { Refused, Unreachable } from "../api/client";
import type { InsightOut, InsightsReportOut, InsightsReportSummaryOut } from "../api/types";
import {
  ANALYST_STREAM_IDLE,
  analystStreamReducer,
  confidenceWordKey,
  headlineInsight,
  pastReportsNewestFirst,
  sectionsFor,
  type SectionView,
} from "../health/insights";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { dateLine } from "../today/model";
import { useToday } from "../today/useToday";
import { Notice } from "../ui/components";
import { Chip, ChipRow, IconBadge, ListRow, Orb, PillButton, RevealGroup, SectionHeader, SoftText, StatusLine, TintCard } from "../ui/kit";
import { Shell } from "./Shell";
import "../ui/health.css";

/** One line of the weekly report, drawn exactly as the backend wrote it: his sentence, how
 *  sure Nura is, the why (its evidence, in his papers' own words), and, when a doctor's name
 *  comes with it, the one button that takes it to the visit. No hook, so it renders the same
 *  from a test as it does on the screen. */
export function InsightRow({
  insight,
  s,
  asking,
  asked,
  onAsk,
  testId,
}: {
  insight: InsightOut;
  s: Strings;
  asking: boolean;
  asked: boolean;
  onAsk?: (insight: InsightOut) => void;
  testId?: string;
}): JSX.Element {
  return (
    <div class="insight-row" data-testid={testId ?? "insight"}>
      <p class="insight-text">{insight.text}</p>
      <ChipRow testId="insight-confidence">
        <Chip>{s.insights[confidenceWordKey(insight.confidence)]}</Chip>
      </ChipRow>
      <details class="insight-why" data-testid="insight-why">
        <summary>{s.insights.why}</summary>
        <p>{insight.why_plain}</p>
        {insight.evidence.length > 0 && (
          <ChipRow testId="insight-evidence">
            {insight.evidence.map((one) => (
              <Chip key={one.id}>{one.label}</Chip>
            ))}
          </ChipRow>
        )}
      </details>
      {insight.ask_who &&
        (onAsk ? (
          <PillButton variant="secondary" onClick={() => onAsk(insight)} disabled={asking || asked} testId="insight-ask">
            {fill(s.insights.askThis, { who: insight.ask_who })}
          </PillButton>
        ) : (
          <p class="caption" data-testid="insight-no-visit">
            {s.insights.noVisit}
          </p>
        ))}
      {asked && (
        <p class="caption" data-testid="insight-asked">
          {s.insights.asked}
        </p>
      )}
    </div>
  );
}

/** One section: the backend's own title and lines when it sent the section at all; a plain
 *  line, never silence, when this key's scope leaves it out, or when Nura looked and found
 *  nothing to say. */
export function SectionCard({
  section,
  s,
  name,
  askingId,
  askedIds,
  onAsk,
  hasNextVisit,
}: {
  section: SectionView;
  s: Strings;
  name: string;
  askingId: string | null;
  askedIds: ReadonlySet<string>;
  onAsk?: (insight: InsightOut) => void;
  hasNextVisit: boolean;
}): JSX.Element {
  const title = section.state === "present" ? section.title : s.insights.sectionTitles[section.key as keyof typeof s.insights.sectionTitles] ?? section.key;
  return (
    <TintCard tint="paper" testId={`insights-section-${section.key}`}>
      <SectionHeader title={title} />
      {section.state === "withheld" && <p class="caption">{fill(s.insights.sectionWithheld, { name })}</p>}
      {section.state === "present" && section.insights.length === 0 && <p class="caption">{s.insights.sectionEmpty}</p>}
      {section.state === "present" &&
        section.insights.map((insight) => (
          <InsightRow
            key={insight.insight_id}
            insight={insight}
            s={s}
            asking={askingId === insight.insight_id}
            asked={askedIds.has(insight.insight_id)}
            onAsk={hasNextVisit ? onAsk : undefined}
          />
        ))}
    </TintCard>
  );
}

/** The report itself: every section in order, assembling in with `RevealGroup` — headline,
 *  then structure, then rows one by one (docs/design/README.md rule 4) — then the boundary
 *  line last, the same rule `AnswerOut.boundary` is always drawn last on an answer. Keyed by
 *  the caller on `report.report_id`, so opening a *different* report remounts this and plays
 *  the reveal again, while a re-render of the same report (an ask settling, a language switch)
 *  never replays it. */
export function ReportBody({
  report,
  s,
  name,
  askingId,
  askedIds,
  onAsk,
  hasNextVisit,
  locale,
  testId,
}: {
  report: InsightsReportOut;
  s: Strings;
  name: string;
  askingId: string | null;
  askedIds: ReadonlySet<string>;
  onAsk?: (insight: InsightOut) => void;
  hasNextVisit: boolean;
  locale: string;
  testId?: string;
}): JSX.Element {
  return (
    <div data-testid={testId ?? "insights-report"}>
      <p class="caption" data-testid="insights-week-of">
        {fill(s.insights.weekOf, { date: dateLine(new Date(report.week_of), locale) })}
      </p>
      <RevealGroup testId="insights-sections">
        {sectionsFor(report).map((section) => (
          <SectionCard key={section.key} section={section} s={s} name={name} askingId={askingId} askedIds={askedIds} onAsk={onAsk} hasNextVisit={hasNextVisit} />
        ))}
      </RevealGroup>
      {report.boundary.length > 0 && (
        <div class="lines boundary" data-testid="insights-boundary">
          {report.boundary.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
      )}
    </div>
  );
}

/** What Nura looked at this run (package 10, the blueprint's `looked()`): the real step labels
 *  the stream just reported, once, right under the headline — never re-said per section, and
 *  never shown at all for a report read back without a stream just having run (a loaded latest
 *  report, an earlier report opened from the list): there is nothing real to say there. */
function LookedAt({ steps, title }: { steps: readonly { key: string; label: string }[]; title: string }): JSX.Element | null {
  if (steps.length === 0) return null;
  return (
    <ChipRow testId="insights-looked-at" label={title}>
      {steps.map((step) => (
        <Chip key={step.key}>{step.label}</Chip>
      ))}
    </ChipRow>
  );
}

/** The weekly report (W1, the blueprint's `analyst` scene): from Health's Health Analyst card,
 *  "Generate now" or the card itself. `start`: a fresh report is wanted at once (the orb, ONE
 *  in-place status line for each real stage, then the headline and the report); left off, the
 *  last one written is shown as it is, "Look again" starting a fresh one on his own tap.
 *
 *  Leaving this screen — the back button, a tab, closing the tab — aborts a stream still in
 *  flight (`AbortController`, `signal` on `nura.insightsStream`) and never updates state after
 *  unmount (`mounted`, checked before every dispatch a callback settling late might otherwise
 *  reach): package 10 §4. */
export function InsightsScreen({ start }: { start?: boolean }): JSX.Element {
  const s = t();
  const v = useToday();
  const locale = LOCALE[language.value];
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";

  const [state, dispatch] = useReducer(analystStreamReducer, ANALYST_STREAM_IDLE);
  const [checked, setChecked] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [streamError, setStreamError] = useState<unknown>(null);
  const [steps, setSteps] = useState<{ key: string; label: string }[]>([]);
  const [pastReports, setPastReports] = useState<InsightsReportSummaryOut[]>([]);
  const [askingId, setAskingId] = useState<string | null>(null);
  const [askedIds, setAskedIds] = useState<ReadonlySet<string>>(new Set());
  const [askError, setAskError] = useState<unknown>(null);

  const mounted = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      mounted.current = false;
      abortRef.current?.abort();
    },
    [],
  );

  const loadPast = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    try {
      const rows = await nura.insightsList(bearer, papers.profile_id);
      if (mounted.current) setPastReports(pastReportsNewestFirst(rows));
    } catch {
      // The quiet list is a nicety, not the report itself: a failure here says nothing on
      // its own rather than putting a second error banner beside the report's own.
    }
  };

  const load = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    try {
      const found = await nura.insightsLatest(bearer, papers.profile_id);
      if (!mounted.current) return;
      if (found) dispatch({ type: "report", report: found });
    } catch (failure) {
      if (mounted.current) setLoadError(failure);
    } finally {
      if (mounted.current) setChecked(true);
    }
  };

  const generate = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    abortRef.current?.abort();
    const control = new AbortController();
    abortRef.current = control;
    setSteps([]);
    setStreamError(null);
    setLoadError(null);
    dispatch({ type: "start" });
    try {
      const written = await nura.insightsStream(
        bearer,
        papers.profile_id,
        (key, label) => {
          if (!mounted.current) return;
          setSteps((was) => [...was, { key, label }]);
          dispatch({ type: "step", label });
        },
        control.signal,
      );
      if (!mounted.current) return;
      dispatch({ type: "report", report: written });
      setChecked(true);
      setPastReports((was) => pastReportsNewestFirst([{ report_id: written.report_id, generated_at: written.generated_at, week_of: written.week_of }, ...was]));
    } catch (failure) {
      if (!mounted.current || control.signal.aborted) return;
      setStreamError(failure);
      dispatch({ type: "error", message: failure instanceof Error ? failure.message : "unreachable" });
    }
  };

  const openPast = async (reportId: string) => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    setLoadError(null);
    try {
      const found = await nura.insightsById(bearer, papers.profile_id, reportId);
      if (mounted.current) dispatch({ type: "report", report: found });
    } catch (failure) {
      if (mounted.current) setLoadError(failure);
    }
  };

  useEffect(() => {
    void loadPast();
    if (start) void generate();
    else void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start]);

  const askThis = async (insight: InsightOut) => {
    const bearer = token.value;
    const papers = profile.value;
    const appointmentId = v.nextVisit?.appointment_id;
    if (!bearer || !papers || !appointmentId || askingId) return;
    setAskingId(insight.insight_id);
    setAskError(null);
    try {
      const change = { text: insight.text };
      const yes = await nura.mintQuestionYes(bearer, papers.profile_id, appointmentId, change);
      await nura.changeQuestion(bearer, papers.profile_id, appointmentId, change, yes.confirmation_id);
      if (mounted.current) setAskedIds((was) => new Set(was).add(insight.insight_id));
    } catch (failure) {
      if (mounted.current) setAskError(failure);
    } finally {
      if (mounted.current) setAskingId(null);
    }
  };

  const working = state.phase === "working";
  const report = state.phase === "done" ? state.report : null;
  const headline = report ? headlineInsight(report) : null;
  const generateLabel = report ? s.insights.lookAgain : s.insights.generate;
  const retrying = state.phase === "error";

  return (
    <Shell tab="health" testId="insights-screen" topBar={{ variant: "board", title: owner ? s.insights.screenTitle : fill(s.insights.screenTitleOther, { name }), back: true }}>
      <Notice error={askError} />

      {working && (
        <div class="analyst-working" data-testid="insights-thinking">
          <Orb size="sm" thinking testId="insights-orb" />
          <StatusLine text={state.statusText || s.insights.working} testId="insights-status" />
        </div>
      )}

      {retrying && (
        <>
          {state.statusText && (
            <div class="analyst-working" data-testid="insights-thinking-stopped">
              <Orb size="sm" testId="insights-orb" />
              <StatusLine text={state.statusText} testId="insights-status" />
            </div>
          )}
          <Notice error={streamError ?? loadError} />
        </>
      )}
      {!retrying && <Notice error={loadError} />}

      {!working && report && (
        <>
          {headline && <SoftText key={report.report_id} text={headline.text} as="h2" pace="body" className="analyst-headline" testId="insights-headline" />}
          {/* "What Nura looked at": the same catalogue string `talk.lookedAt` already says
           *  for Ask's own conversation trace — reused, never a second translation of the
           *  same words (`make language`, "the same words every time"). */}
          <LookedAt steps={steps} title={s.talk.lookedAt} />
          <ReportBody key={report.report_id} report={report} s={s} name={name} askingId={askingId} askedIds={askedIds} onAsk={askThis} hasNextVisit={Boolean(v.nextVisit)} locale={locale} />
        </>
      )}

      {!working && !report && checked && state.phase !== "error" && (
        <TintCard tint="paper" testId="insights-none">
          <p>{owner ? s.insights.cardNone : fill(s.insights.cardNoneOther, { name })}</p>
        </TintCard>
      )}

      {!working && pastReports.length > 0 && (
        <>
          <SectionHeader title={s.insights.pastTitle} />
          <div data-testid="insights-past-list">
            {pastReports.map((row) => (
              <ListRow
                key={row.report_id}
                lead={<IconBadge icon="trends" tint="lavender" size="small" />}
                title={fill(s.insights.weekOf, { date: dateLine(new Date(row.week_of), locale) })}
                line={dateLine(new Date(row.generated_at), locale)}
                onClick={() => void openPast(row.report_id)}
                testId={`insights-past-${row.report_id}`}
              />
            ))}
          </div>
        </>
      )}

      {!working && (
        <PillButton variant="primary" onClick={() => void generate()} testId="insights-generate">
          {retrying ? s.insights.retryAfterError : generateLabel}
        </PillButton>
      )}
    </Shell>
  );
}
