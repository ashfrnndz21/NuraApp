import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { FactOut, FoodCatalogItemOut, FoodEntryOut, HealthOverviewOut, InsightsReportOut, MetricKind } from "../api/types";
import { useToday } from "../today/useToday";
import { DoseSection, NextVisitTile } from "./Today";
import { bloodPressureRows, bloodSugarRows, foodWords, healthTitle, MEALS, mealsToday, medicinesShown, readingsWithheld } from "../health/model";
import { headlineInsight } from "../health/insights";
import { dateLine } from "../today/model";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { Icon, IconBadge, MetricRow, PaperTile, PillButton, ProgressRing, SectionHeader, type Tint, TintCard } from "../ui/kit";
import { Notice } from "../ui/components";
import { go } from "../flow";
import { session, toRecord, useRead } from "./record/parts";
import { Shell } from "./Shell";

/** The Health tab (docs/design/nura-concept-board.html, "3 · Health"): "This week"'s ring and
 *  his four everyday metrics, his readings, his day, his medicines and what is coming up. Every
 *  figure is the backend's own; this screen only lays them out and, for a key without the
 *  readings scope, says so plainly instead of leaving the block off in silence. */

const METRIC_TINT: Record<MetricKind, Tint> = { steps: "sage", heart_rate: "blush", sleep: "lavender", water: "sky" };

function useReadings(scopes: readonly string[]): { bp: FactOut[]; sugar: FactOut[] } {
  const bearer = token.value;
  const papers = profile.value;
  const [rows, setRows] = useState<{ bp: FactOut[]; sugar: FactOut[] }>({ bp: [], sugar: [] });
  useEffect(() => {
    if (!bearer || !papers || readingsWithheld(scopes)) return setRows({ bp: [], sugar: [] });
    Promise.all([nura.facts(bearer, papers.profile_id, "blood_pressure"), nura.facts(bearer, papers.profile_id, "blood_sugar")]).then(
      ([bp, sugar]) => setRows({ bp, sugar }),
      () => setRows({ bp: [], sugar: [] }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bearer, papers?.profile_id, scopes.join(",")]);
  return rows;
}

function useMealsToday(): { entries: FoodEntryOut[]; catalog: FoodCatalogItemOut[] } {
  const bearer = token.value;
  const papers = profile.value;
  const [entries, setEntries] = useState<FoodEntryOut[]>([]);
  const [catalog, setCatalog] = useState<FoodCatalogItemOut[]>([]);
  useEffect(() => {
    if (!bearer || !papers) return;
    const midnight = new Date();
    midnight.setHours(0, 0, 0, 0);
    nura.food(bearer, papers.profile_id, language.value, midnight.toISOString()).then(setEntries, () => setEntries([]));
    nura.foodCatalog(language.value).then(setCatalog, () => setCatalog([]));
  }, [bearer, papers?.profile_id, language.value]);
  return { entries, catalog };
}

/** "This week": the ring — doses taken this week, never a score — and steps, heart rate, sleep
 *  and water, each already in the backend's own plain words, each grounded by when it was
 *  said (`ProgressRing`, `MetricRow`: neither draws without its source line). */
function ThisWeek({ overview, locale, owner, name }: { overview: HealthOverviewOut | null; locale: string; owner: boolean; name: string }): JSX.Element {
  const s = t();
  return (
    <TintCard tint="peach" testId="health-week">
      {overview && (
        <ProgressRing
          done={overview.ring.value}
          of={overview.ring.total ?? 0}
          figure={overview.ring.words}
          label={overview.ring.label}
          source={fill(s.health.asOf, { date: dateLine(new Date(overview.ring.as_of), locale) })}
          testId="health-ring"
        />
      )}
      {overview?.metrics.map((row) => (
        <MetricRow
          key={row.kind}
          icon={row.kind}
          tint={METRIC_TINT[row.kind]}
          label={row.label}
          value={row.status === "logged" ? (row.value_words ?? "") : ""}
          source={
            row.status === "logged" && row.last_logged_at
              ? fill(owner ? s.health.metricSource : s.health.metricSourceOther, { date: dateLine(new Date(row.last_logged_at), locale), name })
              : row.status_words
          }
          testId={`metric-${row.kind}`}
        />
      ))}
    </TintCard>
  );
}

/** His readings — blood pressure and blood sugar, from his blood pressure book, the newest
 *  first — or, for a key whose scope does not cover them, the block named and said withheld
 *  (never left off the screen in silence). */
function Readings({ scopes, owner, name }: { scopes: readonly string[]; owner: boolean; name: string }): JSX.Element {
  const s = t();
  const locale = LOCALE[language.value];
  const { bp, sugar } = useReadings(scopes);
  if (readingsWithheld(scopes)) {
    return (
      <TintCard tint="paper" testId="readings-withheld">
        <p>{fill(s.health.readingsWithheld, { name })}</p>
      </TintCard>
    );
  }
  const bpRows = bloodPressureRows(bp);
  const sugarRows = bloodSugarRows(sugar);
  if (bpRows.length === 0 && sugarRows.length === 0) {
    return (
      <TintCard tint="blush" testId="readings">
        <p>{s.health.readingsNone}</p>
      </TintCard>
    );
  }
  return (
    <TintCard tint="blush" testId="readings">
      {bpRows[0] && (
        <MetricRow icon="gauge" tint="blush" label={s.health.bloodPressure} value={bpRows[0].words} unit="mmHg" source={fill(owner ? s.health.readingSource : s.health.readingSourceOther, { date: dateLine(new Date(bpRows[0].at), locale), name })} testId="reading-bp" />
      )}
      {sugarRows[0] && (
        <MetricRow icon="gauge" tint="coral" label={s.health.bloodSugar} value={sugarRows[0].words} unit="mmol/L" source={fill(owner ? s.health.readingSource : s.health.readingSourceOther, { date: dateLine(new Date(sugarRows[0].at), locale), name })} testId="reading-sugar" />
      )}
    </TintCard>
  );
}

/** His day: the meals he answered today, in his own words when he typed them — "no breakfast"
 *  an answered day, a blank day blank (docs/recommendation-engine.md §2.7). Nothing shows when
 *  he has said nothing today: an empty day is not a row of "not written down". */
function DayLogs({ owner, name }: { owner: boolean; name: string }): JSX.Element | null {
  const s = t();
  const { entries, catalog } = useMealsToday();
  const byMeal = mealsToday(entries, new Date());
  const meals = MEALS.filter((meal) => byMeal[meal]);
  if (meals.length === 0) return null;
  return (
    <>
      <SectionHeader title={owner ? s.health.dayTitle : fill(s.health.dayTitleOther, { name })} />
      <TintCard tint="butter" testId="day-logs">
        {meals.map((meal) => {
          const entry = byMeal[meal]!;
          return (
            <div class="metric-row" key={meal} data-testid={`meal-${meal}`}>
              <IconBadge icon="meal" tint="butter" size="small" />
              <span class="metric-label">{entry.meal_label}</span>
              <span class="metric-value">{entry.status === "skipped" ? "" : foodWords(entry, catalog)}</span>
              <span class="metric-source">{entry.status === "skipped" ? (owner ? s.health.mealNotHad : fill(s.health.mealNotHadOther, { name })) : entry.amount || ""}</span>
            </div>
          );
        })}
      </TintCard>
    </>
  );
}

function useLatestInsights(): { report: InsightsReportOut | null; checked: boolean } {
  const bearer = token.value;
  const papers = profile.value;
  const [report, setReport] = useState<InsightsReportOut | null>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (!bearer || !papers) return;
    setChecked(false);
    nura.insightsLatest(bearer, papers.profile_id).then(
      (found) => {
        setReport(found);
        setChecked(true);
      },
      () => {
        // A 404 (nothing generated yet) and any other failure both leave the card in its "not
        // looked at yet" state: quiet, never an error banner on a card this small.
        setReport(null);
        setChecked(true);
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bearer, papers?.profile_id]);
  return { report, checked };
}

/** The Insights card (W1, docs/design/nura-concept-board.html): "Your week, looked at
 *  closely", when it was last looked at and the one line most worth a look, with "Generate
 *  now" beside it. Tapping the card opens the report as it stands; "Generate now" opens it and
 *  starts a fresh one at once. No hook, so it renders the same from a test as on the screen. */
export function InsightsCard({
  s,
  owner,
  name,
  report,
  checked,
  locale,
  onOpen,
  onGenerate,
}: {
  s: Strings;
  owner: boolean;
  name: string;
  report: InsightsReportOut | null;
  checked: boolean;
  locale: string;
  onOpen: () => void;
  onGenerate: () => void;
}): JSX.Element {
  const headline = report ? headlineInsight(report) : null;
  return (
    <TintCard tint="lavender" testId="insights-card">
      <button type="button" class="insights-card-open" onClick={onOpen} data-testid="insights-open">
        <IconBadge icon="trends" tint="lavender" />
        <span class="insights-card-text">
          <span class="insights-card-title">{owner ? s.insights.cardTitle : fill(s.insights.cardTitleOther, { name })}</span>
          {report && (
            <span class="caption" data-testid="insights-last-looked">
              {fill(s.insights.cardLastLooked, { date: dateLine(new Date(report.generated_at), locale) })}
            </span>
          )}
          {!report && checked && (
            <span class="caption" data-testid="insights-none">
              {owner ? s.insights.cardNone : fill(s.insights.cardNoneOther, { name })}
            </span>
          )}
          {headline && (
            <span class="insights-card-headline" data-testid="insights-headline">
              {headline.text}
            </span>
          )}
        </span>
      </button>
      <PillButton variant="primary" onClick={onGenerate} testId="insights-generate">
        {s.insights.generate}
      </PillButton>
    </TintCard>
  );
}

export function HealthScreen(): JSX.Element {
  const s = t();
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";
  const scopes = papers?.scopes ?? [];
  const locale = LOCALE[language.value];
  const v = useToday();
  const { data: overview, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.healthOverview(bearer, profileId, language.value);
  }, [language.value]);
  const { report: latestInsights, checked: insightsChecked } = useLatestInsights();

  return (
    <Shell
      tab="health"
      testId="health-screen"
      topBar={{ variant: "board", title: healthTitle(owner, name, s), back: true, action: { icon: "calendar", label: s.health.addReading, onClick: () => go({ name: "reading" }) } }}
    >
      <InsightsCard
        s={s}
        owner={owner}
        name={name}
        report={latestInsights}
        checked={insightsChecked}
        locale={locale}
        onOpen={() => go({ name: "insights" })}
        onGenerate={() => go({ name: "insights", start: true })}
      />

      <SectionHeader title={s.health.thisWeek} />
      <Notice error={error} />
      <ThisWeek overview={overview} locale={locale} owner={owner} name={name} />

      <SectionHeader title={s.health.readingsTitle} />
      <Readings scopes={scopes} owner={owner} name={name} />

      <DayLogs owner={owner} name={name} />

      {medicinesShown(owner, scopes) && <DoseSection v={v} />}

      <SectionHeader title={s.health.comingUpTitle} />
      {v.nextVisit ? <NextVisitTile visit={v.nextVisit} /> : (
        <TintCard tint="paper" testId="coming-up-none">
          <p>{owner ? s.visit.none : fill(s.places.visitsNoneOther, { name })}</p>
        </TintCard>
      )}

      <PaperTile testId="health-more">
        <nav class="place-rows" aria-label={owner ? s.record.title : fill(s.record.titleOther, { name })}>
          {medicinesShown(owner, scopes) && (
            <button type="button" class="place-row" onClick={() => toRecord({ name: "medicines" })} data-testid="health-medicines">
              <Icon name="medicines" />
              <span class="place-word">{s.record.medicines}</span>
              <Icon name="chevron" />
            </button>
          )}
          <button type="button" class="place-row" onClick={() => toRecord({ name: "hub" })} data-testid="health-record-hub">
            <Icon name="records" />
            <span class="place-word">{owner ? s.record.title : fill(s.record.titleOther, { name })}</span>
            <Icon name="chevron" />
          </button>
        </nav>
      </PaperTile>
    </Shell>
  );
}
