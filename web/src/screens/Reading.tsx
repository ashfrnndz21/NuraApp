import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { go } from "../flow";
import { profile, token } from "../store/session";
import { t } from "../strings";
import { Field, Header, Notice, Pill, Tile } from "../ui/components";

/** A blood pressure typed in: two numbers, one Save. The route writes the event and the
 *  fact with his own word as the confirmation. */
export function ReadingScreen(): JSX.Element {
  const s = t();
  const [top, setTop] = useState("");
  const [bottom, setBottom] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const systolic = Number(top);
  const diastolic = Number(bottom);
  const ok = systolic >= 40 && systolic <= 300 && diastolic >= 20 && diastolic <= 200;

  const save = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers || !ok) return;
    setBusy(true);
    setError(null);
    try {
      await nura.addReading(bearer, papers.profile_id, systolic, diastolic);
      go({ name: "today", saved: true });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.reading.title} />
      <Tile paper>
        <p>{s.reading.lead}</p>
        <Field name="systolic" label={s.reading.top} value={top} onInput={setTop} inputMode="numeric" big maxLength={3} />
        <Field name="diastolic" label={s.reading.bottom} value={bottom} onInput={setBottom} inputMode="numeric" big maxLength={3} />
        <Pill plum onClick={save} disabled={busy || !ok} testId="save-reading">
          {s.reading.save}
        </Pill>
      </Tile>
      <Notice error={error} />
      <Pill quiet onClick={() => go({ name: "today" })}>
        {s.reading.cancel}
      </Pill>
    </main>
  );
}
