import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { Part, SharingIn, SharingPreviewOut } from "../../api/types";
import { who } from "../../onboarding/actions";
import { plan, planNote, to } from "../../onboarding/state";
import { density } from "../../store/session";
import { language, t } from "../../strings";
import { Field, Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

const PARTS: readonly Part[] = ["medicines", "visits", "readings", "records"];

/** The invite gap (E12): who, which parts, then the words — rendered by the backend for this
 *  person and these parts by `POST /consents/sharing/preview`, the function the consent keeps
 *  them with — and his one "I agree". Then the sharing consent, and the key
 *  that rests on it, to the same parts and no wider. Only his own papers come here: the
 *  consent route takes the owner's own yes (`Plan.tsx`, `invites`). Changing the person or
 *  the parts after reading takes the words away, so the yes is for exactly what was shown. */
export function InviteStep(): JSX.Element {
  const s = t();
  const i = s.onboarding.invite;
  const patient = density() === "patient";
  const [screen, setScreen] = useState<0 | 1 | 2>(0);
  const [phone, setPhone] = useState("+65");
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [parts, setParts] = useState<Part[]>([]);
  const [words, setWords] = useState<SharingPreviewOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const asked = (): SharingIn => ({
    holder_phone_e164: phone.replace(/\s+/g, ""),
    holder_display_name: name.trim(),
    scopes: PARTS.filter((part) => parts.includes(part)),
    relationship: relationship.trim() || null,
    language: language.value,
  });
  const changed = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setWords(null);
  };
  const toggle = (part: Part) => changed(setParts)(parts.includes(part) ? parts.filter((each) => each !== part) : [...parts, part]);
  const phoneOk = phone.replace(/\D/g, "").length >= 8 && name.trim().length > 0;

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

  const seeWords = () =>
    act(async () => {
      const { bearer, profileId } = who();
      setWords(await nura.previewSharing(bearer, profileId, asked()));
      setScreen(2);
    });

  const agree = () =>
    act(async () => {
      if (!words) return;
      const { bearer, profileId } = who();
      const body = asked();
      await nura.letSomeoneIn(bearer, profileId, body, words.wording_version);
      await nura.cutKey(bearer, profileId, body.holder_phone_e164, body.scopes);
      planNote.value = i.done;
      plan.value = await nura.plan(bearer, profileId, language.value);
      to({ name: "plan" });
    });

  const whoSheet = (
    <Sheet lines={[i.lead]} testId="invite-who">
      <Field name="holder-name" label={i.nameLabel} value={name} onInput={changed(setName)} autoComplete="off" />
      <Field name="holder-phone" label={i.phoneLabel} value={phone} onInput={changed(setPhone)} type="tel" inputMode="tel" />
      <Field name="relationship" label={i.relationshipLabel} value={relationship} onInput={changed(setRelationship)} />
    </Sheet>
  );
  const partsSheet = (
    <Sheet lines={[i.partsLead]} testId="invite-parts">
      <div class="choices" role="group">
        {PARTS.map((part) => (
          <Pill key={part} onClick={() => toggle(part)} chosen={parts.includes(part)} disabled={busy} testId={`part-${part}`}>
            {i.parts[part]}
          </Pill>
        ))}
      </div>
    </Sheet>
  );
  const wordsSheet = words && (
    <Sheet caption={i.wordsLead} lines={words.lines} testId="invite-words">
      <Pill plum onClick={() => void agree()} disabled={busy} testId="invite-agree">
        {i.agree}
      </Pill>
    </Sheet>
  );
  const seeButton = (
    <Pill plum={!words} onClick={() => void seeWords()} disabled={busy || !phoneOk || parts.length === 0} testId="invite-see-words">
      {i.seeWords}
    </Pill>
  );

  return (
    <main class="screen onboarding" data-stage="invite">
      <StepTitle title={i.title} />
      {patient ? (
        <>
          {screen === 0 && whoSheet}
          {screen === 1 && partsSheet}
          {screen === 2 && wordsSheet}
          {screen === 0 && (
            <Pill plum onClick={() => setScreen(1)} disabled={!phoneOk} testId="invite-next">
              {s.onboarding.next}
            </Pill>
          )}
          {screen === 1 && seeButton}
        </>
      ) : (
        <>
          {whoSheet}
          {partsSheet}
          {!words && seeButton}
          {wordsSheet}
        </>
      )}
      {busy && <Status text={s.onboarding.saving} />}
      <Notice error={error} />
      <Pill quiet onClick={() => (patient && screen > 0 ? setScreen(screen === 2 ? 1 : 0) : to({ name: "plan" }))} testId="invite-back">
        {s.onboarding.back}
      </Pill>
    </main>
  );
}
