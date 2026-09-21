import { useEffect, useReducer, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { InsightOut, InsightsReportOut, InsightsReportSummaryOut } from "../api/types";
import {
  ANALYST_STREAM_IDLE,
  analystStreamReducer,
  askWhoLabel,
  confidenceWordKey,
  headlineInsight,
  lookedAtParts,
  pastReportsNewestFirst,
  sectionInsightsView,
  sectionsFor,
  type SectionView,
} from "../health/insights";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { dateLine } from "../today/model";
import { useToday } from "../today/useToday";
import { Notice } from "../ui/components";
import { Chip, ChipRow, Icon, IconBadge, ListRow, LookedAt, Orb, PillButton, RevealGroup, SectionHeader, SoftText, StatusLine, TintCard } from "../ui/kit";
import { Shell } from "./Shell";
import "../ui/health.css";

/** The chip, the "Ask … this" action and the "Why" disclosure that follow an insight's own
 *  sentence — pulled out of `InsightRow` so the screen's own headline (package 10 review: "say
 *  it once") can carry the *same* row of actions without repeating the sentence itself.
 *
 *  "Why" is a real disclosure, not an orphan label: a native `<details>`/`<summary>` (kept
 *  hookless, like every other component in this file and `ui/kit/Conversation.tsx`, so it
 *  renders the same from the static-tree unit tests as it does on the screen) with the same
 *  chevron `ReportTable.tsx`'s "About this paper" toggle uses, rotating open/closed by CSS off
 *  `details[open]` rather than a component-owned `aria-expanded` (`.insight-why` in
 *  `ui/health.css`) — closed by default (a `<details>` with no `open` attribute), and never
 *  rendered at all when the insight carries no `why_plain` to show.
 *
 *  Who "Ask … this" names is composed here, never read off `ask_who` verbatim: the backend's
 *  `ask_who` is one of `"doctor"`, `"pharmacist"`, `"nobody"` — a role, never a literal name
 *  (`askWhoLabel`). `"nobody"` (and any row with none of the three) shows no action at all. */
function InsightActions({
  insight,
  s,
  owner,
  name,
  nextVisitDoctor,
  asking,
  asked,
  onAsk,
}: {
  insight: InsightOut;
  s: Strings;
  owner: boolean;
  name: string;
  nextVisitDoctor: string | null;
  asking: boolean;
  asked: boolean;
  onAsk?: (insight: InsightOut) => void;
}): JSX.Element {
  const who = askWhoLabel(insight.ask_who, s, owner, name, nextVisitDoctor);
  return (
    <div class="insight-meta">
      <div class="insight-actions-row">
        <Chip>{s.insights[confidenceWordKey(insight.confidence)]}</Chip>
        {who &&
          (onAsk ? (
            <PillButton variant="quiet" compact onClick={() => onAsk(insight)} disabled={asking || asked} testId="insight-ask">
              {fill(s.insights.askThis, { who })}
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
      {insight.why_plain && (
        <details class="insight-why" data-testid="insight-why">
          <summary>
            <span>{s.insights.why}</span>
            <Icon name="chevron" />
          </summary>
          <div data-testid="insight-why-body">
            <p>{insight.why_plain}</p>
            {insight.evidence.length > 0 && (
              <ChipRow testId="insight-evidence">
                {insight.evidence.map((one) => (
                  <Chip key={one.id}>{one.label}</Chip>
                ))}
              </ChipRow>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

/** One line of the weekly report, drawn exactly as the backend wrote it: his sentence, then
 *  `InsightActions`. No hook of its own, so it renders the same from a test as it does on the
 *  screen (the "why" toggle's own state lives in `InsightActions`, not here). */
export function InsightRow({
  insight,
  s,
  owner,
  name,
  nextVisitDoctor,
  asking,
  asked,
  onAsk,
  testId,
}: {
  insight: InsightOut;
  s: Strings;
  owner: boolean;
  name: string;
  nextVisitDoctor: string | null;
  asking: boolean;
  asked: boolean;
  onAsk?: (insight: InsightOut) => void;
  testId?: string;
}): JSX.Element {
  return (
    <div class="insight-row" data-testid={testId ?? "insight"}>
      <p class="insight-text">{insight.text}</p>
      <InsightActions insight={insight} s={s} owner={owner} name={name} nextVisitDoctor={nextVisitDoctor} asking={asking} asked={asked} onAsk={onAsk} />
    </div>
  );
}

/** One section: the backend's own title and lines when it sent the section at all; a plain
 *  line, never silence, when this key's scope leaves it out, or when Nura looked and found
 *  nothing to say. `promotedId`: the one insight already shown as the screen's own headline —
 *  left out of this section's own list (`sectionInsightsView`), never repeated, and never
 *  mistaken for "nothing to say" when it is the only reason the list is empty. */
export function SectionCard({
  section,
  s,
  name,
  owner,
  nextVisitDoctor,
  askingId,
  askedIds,
  onAsk,
  hasNextVisit,
  promotedId,
}: {
  section: SectionView;
  s: Strings;
  name: string;
  owner: boolean;
  nextVisitDoctor: string | null;
  askingId: string | null;
  askedIds: ReadonlySet<string>;
  onAsk?: (insight: InsightOut) => void;
  hasNextVisit: boolean;
  promotedId?: string | null;
}): JSX.Element {
  const title = section.state === "present" ? section.title : s.insights.sectionTitles[section.key as keyof typeof s.insights.sectionTitles] ?? section.key;
  const view = section.state === "present" ? sectionInsightsView(section.insights, promotedId) : { insights: [], emptyBecausePromoted: false };
  return (
    <TintCard tint="paper" testId={`insights-section-${section.key}`}>
      <SectionHeader title={title} />
      {section.state === "withheld" && <p class="caption">{fill(s.insights.sectionWithheld, { name })}</p>}
      {section.state === "present" && view.insights.length === 0 && !view.emptyBecausePromoted && <p class="caption">{s.insights.sectionEmpty}</p>}
      {section.state === "present" &&
        view.insights.map((insight) => (
          <InsightRow
            key={insight.insight_id}
            insight={insight}
            s={s}
            owner={owner}
            name={name}
            nextVisitDoctor={nextVisitDoctor}
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
  owner,
  nextVisitDoctor,
  askingId,
  askedIds,
  onAsk,
  hasNextVisit,
  locale,
  promotedId,
  testId,
}: {
  report: InsightsReportOut;
  s: Strings;
  name: string;
  owner: boolean;
  nextVisitDoctor: string | null;
  askingId: string | null;
  askedIds: ReadonlySet<string>;
  onAsk?: (insight: InsightOut) => void;
  hasNextVisit: boolean;
  locale: string;
  promotedId?: string | null;
  testId?: string;
}): JSX.Element {
  return (
    <div data-testid={testId ?? "insights-report"}>
      <p class="caption" data-testid="insights-week-of">
        {fill(s.insights.weekOf, { date: dateLine(new Date(report.week_of), locale) })}
      </p>
      <RevealGroup testId="insights-sections">
        {sectionsFor(report).map((section) => (
          <SectionCard
            key={section.key}
            section={section}
            s={s}
            name={name}
            owner={owner}
            nextVisitDoctor={nextVisitDoctor}
            askingId={askingId}
            askedIds={askedIds}
            onAsk={onAsk}
            hasNextVisit={hasNextVisit}
            promotedId={promotedId}
          />
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
  const nextVisitDoctor = v.nextVisit?.doctor ?? null;

  const [state, dispatch] = useReducer(analystStreamReducer, ANALYST_STREAM_IDLE);
  const [checked, setChecked] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [streamError, setStreamError] = useState<unknown>(null);
  const [steps, setSteps] = useState<{ key: string; label: string; name: string }[]>([]);
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
        (key, label, stepName) => {
          if (!mounted.current) return;
          setSteps((was) => [...was, { key, label, name: stepName }]);
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
          {/* The orb beside the headline, finished (not thinking) — the same treatment Ask
           *  gives a settled turn (`Orb testId="ask-earlier-orb"`, no `thinking`). The
           *  headline is the one insight promoted out of its section (`promotedId` below),
           *  its own chip/why/ask row carried here instead of repeated in the list. */}
          <div class="analyst-headline-row">
            <Orb size="sm" testId="insights-orb-done" />
            <div class="analyst-headline-body">
              {headline && <SoftText key={report.report_id} text={headline.text} as="h2" pace="body" className="analyst-headline" testId="insights-headline" />}
              {headline && (
                <InsightActions
                  insight={headline}
                  s={s}
                  owner={owner}
                  name={name}
                  nextVisitDoctor={nextVisitDoctor}
                  asking={askingId === headline.insight_id}
                  asked={askedIds.has(headline.insight_id)}
                  onAsk={v.nextVisit ? askThis : undefined}
                />
              )}
            </div>
          </div>
          {/* "What Nura looked at": the real stages' bare nouns, once, collapsed into the same
           *  line Ask's own turns give (`feed.askLookedAt`, `LookedAt`) — never five chips
           *  still standing after the report is assembled, and never shown for a report read
           *  back without a stream having just run (nothing real to say there). */}
          {steps.length > 0 && (
            <LookedAt
              summary={fill(s.feed.askLookedAt, { parts: lookedAtParts(steps) })}
              steps={steps.map((step) => ({ key: step.key, text: step.label, done: true }))}
              testId="insights-looked-at"
            />
          )}
          <ReportBody
            key={report.report_id}
            report={report}
            s={s}
            name={name}
            owner={owner}
            nextVisitDoctor={nextVisitDoctor}
            askingId={askingId}
            askedIds={askedIds}
            onAsk={askThis}
            hasNextVisit={Boolean(v.nextVisit)}
            locale={locale}
            promotedId={headline?.insight_id ?? null}
          />
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
