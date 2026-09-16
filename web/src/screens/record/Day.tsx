import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { RoutineDayIn } from "../../api/types";
import {
  ANALYTES,
  ANCHORS,
  dayInOrder,
  dayOf,
  numberText,
  pointRangeLine,
  rangeSourceLine,
  READINGS,
  clockLine,
  trendLines,
  withReading,
  withTime,
  withWalk,
  type Analyte,
} from "../../record/model";
import { density, profile } from "../../store/session";
import { fill, language, LOCALE, t } from "../../strings";
import { Field, Hear, Notice, Pill, Tile } from "../../ui/components";
import { RecordFrame, recordNote, session, takeNote, toRecord, useDateOf, useRead } from "./parts";

function isAnalyte(code: string | null): code is Analyte {
  return code !== null && (ANALYTES as readonly string[]).includes(code);
}

/** His blood tests (E09-01): pick one, and read it over time — each result against the range
 *  that fits him, the direction in the backend's words, the boundary line last. */
export function TrendsScreen({ analyte }: { analyte: string | null }): JSX.Element {
  const s = t();
  if (!isAnalyte(analyte)) {
    return (
      <RecordFrame title={s.record.trends} back={{ name: "hub" }} testId="record-trends">
        <Tile paper testId="analytes">
          <p>{s.record.trendsLead}</p>
          {ANALYTES.map((code) => (
            <Pill key={code} onClick={() => toRecord({ name: "trends", analyte: code })} testId={`analyte-${code}`}>
              {s.record.analytes[code]}
            </Pill>
          ))}
        </Tile>
      </RecordFrame>
    );
  }
  return <TrendScreen analyte={analyte} />;
}

function TrendScreen({ analyte }: { analyte: Analyte }): JSX.Element {
  const s = t();
  // Who he is, not how dense his screen reads: the unit and the range are hers to see, and
  // an owner who switches to the caregiver density for the bigger-print layout must not
  // thereby read them too (#166 review, same root as the roster gate in Family.tsx).
  const patient = profile.value?.standing === "owner";
  const dateOf = useDateOf();
  const { data: trend, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.trend(bearer, profileId, analyte, language.value);
  }, [analyte, language.value]);
  const said = trend ? trendLines(trend) : null;
  return (
    <RecordFrame title={s.record.analytes[analyte]} back={{ name: "trends" }} testId="record-trend">
      <Notice error={error} />
      {trend && said && (
        <Tile paper testId="trend" >
          <div class="lines" data-testid="trend-lines">
            {said.body.map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </div>
          <div class="lines" data-testid="trend-points">
            {trend.points.map((point) => (
              <div class="lines" key={point.fact_id} data-band={point.band} data-testid="trend-point">
                {/* The unit is hers: his line is the number and the day (plain words, rule 12). */}
                <p class="label">{fill(patient ? s.record.resultOn : s.record.resultOnUnit, { value: numberText(point.value), unit: point.unit ?? trend.unit, date: dateOf(point.on) })}</p>
                <p data-testid="range">{pointRangeLine(point, s, !patient)}</p>
                {rangeSourceLine(point.range, s) && <p class="caption">{rangeSourceLine(point.range, s)}</p>}
              </div>
            ))}
          </div>
          <div class="lines boundary" data-testid="boundary">
            {said.boundary.map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </div>
          <Hear lines={trend.lines} />
        </Tile>
      )}
    </RecordFrame>
  );
}

/** The day (E10-01): to him, one line per moment, in his words; to her, a table of every
 *  moment with its time, its medicines and what to check. The chief sets it on her yes. */
export function RoutineScreen(): JSX.Element {
  const s = t();
  const [note] = useState(takeNote);
  const persona = density() === "patient" ? "patient" : "caregiver";
  const { data: routine, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.routine(bearer, profileId, persona, language.value);
  }, [persona, language.value]);
  return (
    <RecordFrame title={s.record.routine} back={{ name: "hub" }} testId="record-routine">
      {note && (
        <Tile paper settled role="status" testId="record-note">
          {note.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </Tile>
      )}
      <Notice error={error} />
      {routine && !routine.set && (
        <Tile paper testId="routine-not-set">
          <p>{s.record.notSet}</p>
        </Tile>
      )}
      {routine && routine.persona === "patient" && (
        <Tile paper testId="routine-lines">
          <div class="lines">
            {routine.lines.map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </div>
          <Hear lines={routine.lines} />
        </Tile>
      )}
      {routine && routine.persona === "caregiver" && (
        <Tile glass testId="routine-table">
          <div class="table-scroll">
            <table class="record-table">
              <thead>
                <tr>
                  <th>{s.record.tableMoment}</th>
                  <th>{s.record.tableTime}</th>
                  <th>{s.record.tableMedicines}</th>
                  <th>{s.record.tableReadings}</th>
                </tr>
              </thead>
              <tbody>
                {routine.table.map((moment) => (
                  <tr key={moment.anchor} data-anchor={moment.anchor}>
                    <td>{s.record.anchors[moment.anchor as keyof typeof s.record.anchors] ?? moment.anchor}</td>
                    <td>{moment.at}</td>
                    <td>
                      {moment.medicines.map((medicine) => (
                        <span key={medicine.line_id} class="cell-line">
                          {medicine.generic} {medicine.strength} ×{numberText(medicine.amount)}
                        </span>
                      ))}
                    </td>
                    <td>
                      {(moment.readings ?? []).map((reading) => (
                        <span key={reading} class="cell-line">
                          {s.record.readings[reading as keyof typeof s.record.readings] ?? reading}
                        </span>
                      ))}
                      {moment.walk && <span class="cell-line">{s.record.walk}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Tile>
      )}
      {routine && density() === "caregiver" && (
        <Pill plum onClick={() => toRecord({ name: "builder" })} testId="set-day">
          {s.record.setDay}
        </Pill>
      )}
    </RecordFrame>
  );
}

/** The chief's builder: the five moments of his day, what he checks at each, the walks, and
 *  when his Today page comes; then the day read back, and her yes for exactly it. */
export function BuilderScreen(): JSX.Element {
  const s = t();
  const [changed, setDay] = useState<RoutineDayIn | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: routine, error: readError } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.routine(bearer, profileId, "caregiver", language.value);
  }, []);
  // The day as it is set now until she changes it: read, not copied in a frame later.
  const day = changed ?? (routine ? dayOf(routine) : null);

  const save = async () => {
    if (!day) return;
    setBusy(true);
    setError(null);
    try {
      const { bearer, profileId } = session();
      const yes = await nura.mintRoutine(bearer, profileId, day);
      await nura.setRoutine(bearer, profileId, day, yes.confirmation_id, "caregiver", language.value);
      recordNote.value = [s.record.daySaved];
      toRecord({ name: "routine" });
    } catch (failure) {
      setError(failure);
      setAsking(false);
    } finally {
      setBusy(false);
    }
  };

  const checked = (reading: string, anchor: string) => day?.reading_prompts.some(([code, at]) => code === reading && at === anchor) ?? false;
  return (
    <RecordFrame title={s.record.setDay} back={{ name: "routine" }} testId="record-builder">
      <Notice error={readError ?? error} />
      {day && !asking && (
        <>
          {ANCHORS.map((anchor) => (
            <Tile paper key={anchor} testId={`builder-${anchor}`}>
              <h2 class="title">{s.record.anchors[anchor]}</h2>
              <Field name={`at-${anchor}`} label={s.record.timeLabel} type="time" value={day.anchors[anchor] ?? ""} onInput={(value) => setDay(withTime(day, anchor, value))} />
              {READINGS.map((reading) => (
                <Pill
                  key={reading}
                  chosen={checked(reading, anchor)}
                  onClick={() => setDay(withReading(day, reading, anchor, !checked(reading, anchor)))}
                  testId={`reading-${reading}-${anchor}`}
                >
                  {s.record.readings[reading]}
                </Pill>
              ))}
              <Pill chosen={day.walks.includes(anchor)} onClick={() => setDay(withWalk(day, anchor, !day.walks.includes(anchor)))} testId={`walk-${anchor}`}>
                {s.record.walkAfter}
              </Pill>
            </Tile>
          ))}
          <Tile paper testId="builder-morning">
            <Field name="morning-card" label={s.record.morningCard} type="time" value={day.morning_card_at} onInput={(value) => setDay({ ...day, morning_card_at: value })} />
          </Tile>
          <Pill plum onClick={() => setAsking(true)} disabled={!dayInOrder(day)} testId="check-day">
            {s.record.checkDay}
          </Pill>
        </>
      )}
      {day && asking && (
        <Tile paper testId="day-ask">
          <p>{s.record.dayAsk}</p>
          {ANCHORS.map((anchor) => (
            <div class="lines" key={anchor}>
              <p class="label">
                {s.record.anchors[anchor]} {clockLine(day.anchors[anchor] ?? "", LOCALE[language.value])}
              </p>
              {day.reading_prompts
                .filter(([, at]) => at === anchor)
                .map(([code]) => (
                  <p key={code}>{s.record.readings[code as keyof typeof s.record.readings]}</p>
                ))}
              {day.walks.includes(anchor) && <p>{s.record.walkAfter}</p>}
            </div>
          ))}
          <p class="label">
            {s.record.morningCard} {clockLine(day.morning_card_at, LOCALE[language.value])}
          </p>
          <Pill plum onClick={() => void save()} disabled={busy} testId="day-yes">
            {s.record.dayYes}
          </Pill>
          <Pill quiet onClick={() => setAsking(false)} disabled={busy}>
            {s.onboarding.back}
          </Pill>
        </Tile>
      )}
    </RecordFrame>
  );
}
