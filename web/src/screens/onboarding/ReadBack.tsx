import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ReadBackLineOut } from "../../api/types";
import { biography, to } from "../../onboarding/state";
import { density, profile, token } from "../../store/session";
import { fill, t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

/** The read-back: the backend's lines about what he told it, one per screen, each with Yes
 *  and No on paper. No marks the line disputed and nothing is built on it. The client never
 *  writes one of these lines; it shows each one whole, with its source and its State. */
export function ReadBackStep(): JSX.Element {
  const s = t();
  const r = s.onboarding.readBack;
  const patient = density() === "patient";
  const lines = biography.value?.read_back ?? [];
  const [ack, setAck] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const answer = async (line: ReadBackLineOut, said: "yes" | "no") => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await nura.answerReadBack(bearer, papers.profile_id, line.line_id, said);
      biography.value = updated;
      setAck(said === "yes" ? r.agreed : r.disputed);
      if (patient && !updated.read_back.some((each) => each.answer === null)) to({ name: "records" });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const buttons = (line: ReadBackLineOut) => (
    <div class="choices" role="group">
      <Pill onClick={() => void answer(line, "yes")} disabled={busy} extraClass="yes" pressed={line.answer === "yes"} testId="readback-yes">
        {r.yes}
      </Pill>
      <Pill onClick={() => void answer(line, "no")} disabled={busy} extraClass="no" pressed={line.answer === "no"} testId="readback-no">
        {r.no}
      </Pill>
    </div>
  );

  const next = (
    <Pill plum onClick={() => to({ name: "records" })} disabled={busy} testId="readback-next">
      {s.onboarding.next}
    </Pill>
  );

  if (lines.length === 0) {
    return (
      <main class="screen onboarding" data-stage="readBack">
        <StepTitle title={r.title} />
        <Sheet lines={[r.nothing, r.nothingFine, r.nothingSub]} testId="readback-nothing" />
        {next}
      </main>
    );
  }

  const current = lines.find((line) => line.answer === null);
  const shown = patient ? (current ? [current] : []) : lines;
  return (
    <main class="screen onboarding" data-stage="readBack">
      <StepTitle title={r.title} />
      <p class="lead">{r.lead}</p>
      <Status text={ack} testId="readback-ack" />
      {shown.map((line) => (
        <Sheet
          key={line.line_id}
          caption={patient ? fill(r.lineOf, { n: lines.indexOf(line) + 1, total: lines.length }) : undefined}
          big={line.text}
          source={line.source}
          stateId={line.state_id}
          testId="readback-line"
        >
          {buttons(line)}
          {!patient && line.answer === "no" && <p>{r.disputed}</p>}
        </Sheet>
      ))}
      <Notice error={error} />
      {(!patient || !current) && next}
    </main>
  );
}
