import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ReadBackLineOut } from "../../api/types";
import { closeSitting, inMyLanguage, who } from "../../onboarding/actions";
import { biography, to, whose } from "../../onboarding/state";
import { density } from "../../store/session";
import { fill, t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

/** The read-back (#117): the backend's lines about what he told Nura and what his papers said,
 *  one per screen, each with Yes and No on paper. Each line is a confirmed fact read back — the
 *  fact is its source — and a no opens a dispute against it; after a no, the backend's own line
 *  says who looks at the paper again. The client never writes one of these lines. */
export function ReadBackStep(): JSX.Element {
  const s = t();
  const r = s.onboarding.readBack;
  const patient = density() === "patient";
  const bio = biography.value;
  const lines = bio?.read_back ?? [];
  // The sitting's own words address him; a chief reads the app's.
  const own = whose().self && bio?.step === "read_back";
  const [ack, setAck] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

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

  const answer = (line: ReadBackLineOut, said: "yes" | "no") =>
    act(async () => {
      const { bearer, profileId } = who();
      const updated = await inMyLanguage(await nura.answerReadBack(bearer, profileId, line.fact_id, said));
      biography.value = updated;
      setAck(said === "yes" ? r.agreed : (updated.after_no ?? r.disputed));
      if (patient && !updated.read_back.some((each) => each.answer === null)) to({ name: "questions" });
    });

  const pending = lines.some((line) => line.answer === null);
  const next = (
    <Pill plum onClick={() => (lines.length === 0 ? void act(closeSitting) : to({ name: "questions" }))} disabled={busy || pending} testId="readback-next">
      {s.onboarding.next}
    </Pill>
  );

  if (lines.length === 0) {
    return (
      <main class="screen onboarding" data-stage="readBack">
        <StepTitle title={own ? bio.prompt.headline : r.title} />
        <Sheet lines={[r.nothing, r.nothingFine, r.nothingSub]} testId="readback-nothing" />
        <Notice error={error} />
        {next}
      </main>
    );
  }

  const current = lines.find((line) => line.answer === null);
  const shown = patient ? (current ? [current] : []) : lines;
  return (
    <main class="screen onboarding" data-stage="readBack">
      <StepTitle title={own ? bio.prompt.headline : r.title} />
      {(own && bio.prompt.lines.length ? bio.prompt.lines : [r.lead]).map((line, position) => (
        <p key={position} class="lead">
          {line}
        </p>
      ))}
      <Status text={ack} testId="readback-ack" />
      {shown.map((line) => (
        <Sheet
          key={line.fact_id}
          caption={patient ? fill(r.lineOf, { n: lines.indexOf(line) + 1, total: lines.length }) : undefined}
          big={line.line}
          testId="readback-line"
        >
          <div class="choices" role="group">
            <Pill onClick={() => void answer(line, "yes")} disabled={busy || line.answer !== null} extraClass="yes" pressed={line.answer === "yes"} testId="readback-yes">
              {r.yes}
            </Pill>
            <Pill onClick={() => void answer(line, "no")} disabled={busy || line.answer !== null} extraClass="no" pressed={line.answer === "no"} testId="readback-no">
              {r.no}
            </Pill>
          </div>
          {!patient && line.answer === "no" && <p>{bio?.after_no ?? r.disputed}</p>}
        </Sheet>
      ))}
      <Notice error={error} />
      {(!patient || !current) && next}
    </main>
  );
}
