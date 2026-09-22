import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ReadBackLineOut } from "../../api/types";
import { closeSitting, inMyLanguage, who } from "../../onboarding/actions";
import { biography, to, whose } from "../../onboarding/state";
import { t } from "../../strings";
import { Notice, Pill } from "../../ui/components";
import { Reveal } from "../../ui/kit";
import { Sheet, Status, StepTitle } from "./parts";

/** The read-back (#117): the backend's lines about what he told Nura and what his papers said,
 *  every one on this same screen, each with its own Yes and No on paper — never a separate
 *  paged step, patient density or not (the register path, docs/design/onboarding-mock.html's
 *  own "Here's what I understood": one card, every statement, checked at once). Each line is a
 *  confirmed fact read back — the fact is its source — and a no opens a dispute against it;
 *  after a no, the backend's own line says who looks at the paper again. The client never
 *  writes one of these lines. */
export function ReadBackStep(): JSX.Element {
  const s = t();
  const r = s.onboarding.readBack;
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

  return (
    <main class="screen onboarding" data-stage="readBack">
      <StepTitle title={own ? bio.prompt.headline : r.title} />
      {(own && bio.prompt.lines.length ? bio.prompt.lines : [r.lead]).map((line, position) => (
        <p key={position} class="lead">
          {line}
        </p>
      ))}
      <Status text={ack} testId="readback-ack" />
      {lines.map((line) => (
        <Reveal key={line.fact_id}>
          <Sheet big={line.line} testId="readback-line">
            <div class="choices" role="group">
              <Pill onClick={() => void answer(line, "yes")} disabled={busy || line.answer !== null} extraClass="yes" pressed={line.answer === "yes"} testId="readback-yes">
                {r.yes}
              </Pill>
              <Pill onClick={() => void answer(line, "no")} disabled={busy || line.answer !== null} extraClass="no" pressed={line.answer === "no"} testId="readback-no">
                {r.no}
              </Pill>
            </div>
            {line.answer === "no" && <p>{bio?.after_no ?? r.disputed}</p>}
          </Sheet>
        </Reveal>
      ))}
      <Notice error={error} />
      {next}
    </main>
  );
}
