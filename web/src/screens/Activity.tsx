import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { FoodCatalogItemOut, FoodEntryOut, HealthOverviewOut, Meal, MetricKind } from "../api/types";
import { MEALS, foodWords, mealsToday } from "../health/model";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { dateLine } from "../today/model";
import { Field, Notice, Pill, Tile } from "../ui/components";
import { MetricRow, ProgressRing, SectionHeader, TintCard, type Tint } from "../ui/kit";
import { Shell } from "./Shell";

/** Home's "Things to do" (docs/design/nura-concept-board.html, the board's Home tile "Stay
 *  busy."): his day's activity — the same week ring the Health tab shows, and today's steps,
 *  water and meals, each a real write through PR #235's lifestyle logs (`POST
 *  /profiles/{id}/metrics/{kind}`, `POST /profiles/{id}/food`), on his own explicit Save or
 *  tap — never a placeholder, and never written while he is still typing. A key without the
 *  readings scope does not reach this screen (`nav.ts`/`HomeParts.tsx` leave the tile's write
 *  path to the owner and a key that opens it); every write goes through his own `KeyContext`
 *  on the backend regardless. */
export function ActivityScreen(): JSX.Element {
  const s = t();
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";
  const [overview, setOverview] = useState<HealthOverviewOut | null>(null);
  const [entries, setEntries] = useState<FoodEntryOut[]>([]);
  const [catalog, setCatalog] = useState<FoodCatalogItemOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  const reload = async () => {
    const bearer = token.value;
    const at = profile.value;
    if (!bearer || !at) return;
    const midnight = new Date();
    midnight.setHours(0, 0, 0, 0);
    const [nextOverview, nextEntries, nextCatalog] = await Promise.all([
      nura.healthOverview(bearer, at.profile_id, language.value),
      nura.food(bearer, at.profile_id, language.value, midnight.toISOString()),
      nura.foodCatalog(language.value),
    ]);
    setOverview(nextOverview);
    setEntries(nextEntries);
    setCatalog(nextCatalog);
  };

  useEffect(() => {
    reload().catch(setError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [papers?.profile_id, language.value]);

  const afterSave = async () => {
    setSaved(true);
    setError(null);
    await reload().catch(setError);
  };

  const byMeal = mealsToday(entries, new Date());
  const stepsRow = overview?.metrics.find((row) => row.kind === "steps") ?? null;
  const waterRow = overview?.metrics.find((row) => row.kind === "water") ?? null;

  return (
    <Shell tab="home" testId="activity-screen">
      <h1 class="title">{s.activity.title}</h1>

      <SectionHeader title={s.activity.weekTitle} />
      <TintCard tint="lavender" testId="activity-week">
        {overview && (
          <ProgressRing
            done={overview.ring.value}
            of={overview.ring.total ?? 0}
            figure={overview.ring.words}
            label={overview.ring.label}
            source={fill(s.health.asOf, { date: dateLine(new Date(overview.ring.as_of), LOCALE[language.value]) })}
            testId="activity-ring"
          />
        )}
      </TintCard>

      <MetricLog kind="steps" label={s.activity.stepsLabel} saveLabel={s.activity.stepsSave} row={stepsRow} savedLine={saved ? s.activity.saved : null} onSaved={afterSave} onError={setError} />
      <MetricLog kind="water" label={s.activity.waterLabel} saveLabel={s.activity.waterSave} skipLabel={s.activity.waterSkip} row={waterRow} savedLine={saved ? s.activity.saved : null} onSaved={afterSave} onError={setError} />

      <SectionHeader title={owner ? s.activity.mealsTitle : fill(s.activity.mealsTitleOther, { name })} />
      <TintCard tint="butter" testId="activity-meals">
        {MEALS.map((meal) => (
          <MealRow key={meal} meal={meal} entry={byMeal[meal]} catalog={catalog} s={s} owner={owner} name={name} onSaved={afterSave} onError={setError} />
        ))}
      </TintCard>

      <Notice error={error} />
    </Shell>
  );
}

const METRIC_TINT: Record<"steps" | "water", Tint> = { steps: "sage", water: "sky" };

/** One metric — steps or water — as its current value (the same backend words the Health tab
 *  shows) and a way to log a new one: a number typed in, his own explicit Save, the same
 *  confirm-flow shape `Reading.tsx` already uses. Water also offers its own "none" — a real
 *  answer, not a blank (docs/recommendation-engine.md §2.7). */
function MetricLog({
  kind,
  label,
  saveLabel,
  skipLabel,
  row,
  savedLine,
  onSaved,
  onError,
}: {
  kind: Extract<MetricKind, "steps" | "water">;
  label: string;
  saveLabel: string;
  skipLabel?: string;
  row: { value_words: string | null; status: string } | null;
  savedLine: string | null;
  onSaved: () => Promise<void>;
  onError: (failure: unknown) => void;
}): JSX.Element {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const number = Number(value);
  const ok = value.trim() !== "" && Number.isFinite(number) && number >= 0;

  const save = async (skipped: boolean) => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    if (!skipped && !ok) return;
    setBusy(true);
    try {
      await nura.metricLog(bearer, papers.profile_id, kind, skipped ? { skipped: true } : { value: number });
      setValue("");
      await onSaved();
    } catch (failure) {
      onError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <TintCard tint={METRIC_TINT[kind]} testId={`activity-${kind}`}>
      <MetricRow icon={kind} tint={METRIC_TINT[kind]} label={label} value={row?.status === "logged" ? (row.value_words ?? "") : ""} source={savedLine ?? ""} testId={`activity-${kind}-row`} />
      <Field name={kind} label={label} value={value} onInput={setValue} inputMode="numeric" maxLength={5} />
      <Pill plum onClick={() => void save(false)} disabled={busy || !ok} testId={`activity-${kind}-save`}>
        {saveLabel}
      </Pill>
      {skipLabel && (
        <Pill quiet onClick={() => void save(true)} disabled={busy} testId={`activity-${kind}-skip`}>
          {skipLabel}
        </Pill>
      )}
    </TintCard>
  );
}

/** One meal slot: what he already logged today, or — nothing yet — a tap from the catalogue
 *  (no calories, no grams, docs/design-direction.md) and "I did not have this", the same real
 *  answer `app.lifestyle.food` keeps as `skipped`, never a blank row. */
function MealRow({
  meal,
  entry,
  catalog,
  s,
  owner,
  name,
  onSaved,
  onError,
}: {
  meal: Meal;
  entry: FoodEntryOut | undefined;
  catalog: readonly FoodCatalogItemOut[];
  s: Strings;
  owner: boolean;
  name: string;
  onSaved: () => Promise<void>;
  onError: (failure: unknown) => void;
}): JSX.Element {
  const [busy, setBusy] = useState(false);
  const log = async (opts: { catalog_id?: string; skipped?: boolean }) => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    setBusy(true);
    try {
      await nura.foodAdd(bearer, papers.profile_id, { meal, ...opts }, language.value);
      await onSaved();
    } catch (failure) {
      onError(failure);
    } finally {
      setBusy(false);
    }
  };
  if (entry) {
    return (
      <div class="metric-row" data-testid={`activity-meal-${meal}`}>
        <span class="metric-label">{entry.meal_label}</span>
        <span class="metric-value">{entry.status === "skipped" ? "" : foodWords(entry, catalog)}</span>
        <span class="metric-source">{entry.status === "skipped" ? (owner ? s.activity.skipped : fill(s.activity.skippedOther, { patient: name })) : ""}</span>
      </div>
    );
  }
  const label = s.activity.meal[meal];
  return (
    <Tile paper testId={`activity-meal-${meal}`}>
      <p class="label">{label}</p>
      <div class="row" role="group" aria-label={label}>
        {catalog.slice(0, 6).map((item) => (
          <Pill key={item.id} onClick={() => void log({ catalog_id: item.id })} disabled={busy} testId={`activity-meal-${meal}-${item.id}`}>
            {item.label}
          </Pill>
        ))}
        <Pill quiet onClick={() => void log({ skipped: true })} disabled={busy} testId={`activity-meal-${meal}-skip`}>
          {s.activity.skipMeal}
        </Pill>
      </div>
    </Tile>
  );
}
