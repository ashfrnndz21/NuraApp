import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { ReviewCardOut } from "../api/types";
import { go } from "../flow";
import { base64Of } from "../onboarding/actions";
import { profile, token } from "../store/session";
import { t } from "../strings";
import { Field, Header, Notice, Pill, Tile } from "../ui/components";
import { Capture } from "./onboarding/parts";
import { ReviewStep } from "./onboarding/Records";

/** A blood pressure typed in: two numbers, one Save. The route writes the event and the
 *  fact with his own word as the confirmation. Or a photo of the machine's screen (E02-08):
 *  the backend reads the numbers, their units and the time off it into a review card, and one
 *  "Looks right" writes the reading — no typing. */
export function ReadingScreen(): JSX.Element {
  const s = t();
  const [top, setTop] = useState("");
  const [bottom, setBottom] = useState("");
  const [card, setCard] = useState<ReviewCardOut | null>(null);
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

  /** The machine's screen, photographed: its card comes back to be checked, not typed. */
  const screenPhoto = async (file: File) => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers) return;
    setBusy(true);
    setError(null);
    try {
      const data = await base64Of(file);
      const taken = new Date(file.lastModified || Date.now()).toISOString();
      setCard(await nura.addScreenPhoto(bearer, papers.profile_id, data, file.type || "image/jpeg", taken));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  if (card) {
    return (
      <ReviewStep
        key={card.card_id}
        card={card}
        onBack={() => setCard(null)}
        onPaper={screenPhoto}
        onDone={() => go({ name: "today", saved: true })}
      />
    );
  }

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
      <Tile paper testId="reading-photo">
        <p>{s.reading.photoLead}</p>
        <Capture onFile={(file) => void screenPhoto(file)} busy={busy} photoLabel={s.reading.photo} plum={false} withFile={false} />
      </Tile>
      <Notice error={error} />
      <Pill quiet onClick={() => go({ name: "today" })}>
        {s.reading.cancel}
      </Pill>
    </main>
  );
}
