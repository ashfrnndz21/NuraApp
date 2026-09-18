import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { Refused } from "../api/client";
import type { InsightOut, InsightsReportOut } from "../api/types";
import { confidenceWordKey, sectionsFor, insightsTraceSteps, type SectionView } from "../health/insights";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { dateLine } from "../today/model";
import { useToday } from "../today/useToday";
import { Notice } from "../ui/components";
import { Chip, ChipRow, PillButton, SectionHeader, StepTrace, TintCard } from "../ui/kit";
import { Shell } from "./Shell";

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

/** The report itself: every section in order, then the boundary line last — the same rule
 *  `AnswerOut.boundary` is always drawn last on an answer. */
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
      {sectionsFor(report).map((section) => (
        <SectionCard key={section.key} section={section} s={s} name={name} askingId={askingId} askedIds={askedIds} onAsk={onAsk} hasNextVisit={hasNextVisit} />
      ))}
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

/** The weekly report (W1, docs/design/nura-concept-board.html): from Health's Insights card,
 *  "Generate now" or the card itself. `start`: a fresh report is wanted at once (the live
 *  trace, then the report); left off, the last one written is shown as it is, generated only
 *  on his own tap. */
export function InsightsScreen({ start }: { start?: boolean }): JSX.Element {
  const s = t();
  const v = useToday();
  const locale = LOCALE[language.value];
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";
  const [report, setReport] = useState<InsightsReportOut | null>(null);
  const [checked, setChecked] = useState(false);
  const [steps, setSteps] = useState<{ key: string; label: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [askingId, setAskingId] = useState<string | null>(null);
  const [askedIds, setAskedIds] = useState<ReadonlySet<string>>(new Set());
  const [askError, setAskError] = useState<unknown>(null);

  const load = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    try {
      setReport(await nura.insightsLatest(bearer, papers.profile_id));
    } catch (failure) {
      if (failure instanceof Refused && failure.status === 404) setReport(null);
      else setError(failure);
    } finally {
      setChecked(true);
    }
  };

  const generate = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    setSteps([]);
    try {
      const written = await nura.insightsStream(bearer, papers.profile_id, (key, label) => setSteps((was) => [...was, { key, label }]));
      setReport(written);
      setChecked(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
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
      setAskedIds((was) => new Set(was).add(insight.insight_id));
    } catch (failure) {
      setAskError(failure);
    } finally {
      setAskingId(null);
    }
  };

  const traceSteps = insightsTraceSteps(steps);
  return (
    <Shell tab="health" testId="insights-screen" topBar={{ variant: "board", title: owner ? s.insights.screenTitle : fill(s.insights.screenTitleOther, { name }), back: true }}>
      <Notice error={error} />
      <Notice error={askError} />
      {busy && <StepTrace steps={traceSteps} working={s.insights.working} testId="insights-trace" />}
      {!busy && report && (
        <ReportBody report={report} s={s} name={name} askingId={askingId} askedIds={askedIds} onAsk={askThis} hasNextVisit={Boolean(v.nextVisit)} locale={locale} />
      )}
      {!busy && checked && !report && (
        <TintCard tint="paper" testId="insights-none">
          <p>{owner ? s.insights.cardNone : fill(s.insights.cardNoneOther, { name })}</p>
        </TintCard>
      )}
      {!busy && (
        <PillButton variant="primary" onClick={() => void generate()} testId="insights-generate">
          {s.insights.generate}
        </PillButton>
      )}
    </Shell>
  );
}
