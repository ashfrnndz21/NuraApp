import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { SettingsIn } from "../../api/types";
import { ABOUT_ITEMS, BREAKFAST_TIMES, DECADES, deviceEffects, FUNCTION_TILES, isFunctionItem, startingSettings, tidy, type AboutItem } from "../../onboarding/about";
import { finish, say, settings, to } from "../../onboarding/state";
import { density, profile, setDensity, setLanguage, token } from "../../store/session";
import { fill, isLanguage, LANGUAGES, language, t, type Language } from "../../strings";
import { Field, Notice, Pill } from "../../ui/components";
import { Sheet, Status, StepTitle } from "./parts";

/** About you (E01-03): name, language, birth decade, the doctor, breakfast, and four yes/no
 *  tiles. The patient answers one question per screen — a tap on a choice is the answer and
 *  the next question comes; the caregiver density shows them all on one page. One PUT at
 *  the end; his language takes effect the moment he picks it. */
export function AboutStep(): JSX.Element {
  const s = t();
  const a = s.onboarding.about;
  const papers = profile.value;
  const bearer = token.value;
  const patient = density() === "patient";
  const [draft, setDraft] = useState<SettingsIn | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!bearer || !papers) return;
    nura.settings(bearer, papers.profile_id).then(
      (saved) => {
        settings.value = saved;
        setDraft(startingSettings(saved, papers, language.value));
      },
      (failure: unknown) => {
        setError(failure);
        setDraft(startingSettings(null, papers, language.value));
      },
    );
  }, [bearer, papers?.profile_id]);

  const save = async (final: SettingsIn) => {
    if (!bearer || !papers) return;
    setBusy(true);
    setError(null);
    try {
      const clean = tidy(final);
      settings.value = await nura.putSettings(bearer, papers.profile_id, clean);
      const effects = deviceEffects(clean, papers.standing);
      if (effects.language) await setLanguage(effects.language);
      if (effects.density) await setDensity(effects.density);
      to({ name: "cloud" });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  if (!draft) {
    return (
      <main class="screen onboarding" data-stage="about">
        <StepTitle title={say(a.titleSelf, a.titleOther)} />
        <Notice error={error} />
      </main>
    );
  }

  /** Change one answer; in the patient density a choice also moves to the next question. */
  const answer = (patch: Partial<SettingsIn>, advance: boolean) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    if (patch.language && isLanguage(patch.language) && papers?.standing === "owner") void setLanguage(patch.language);
    if (!patient || !advance) return;
    if (index + 1 < ABOUT_ITEMS.length) setIndex(index + 1);
    else void save(next);
  };

  const items = patient ? [ABOUT_ITEMS[index]!] : [...ABOUT_ITEMS];
  const last = index === ABOUT_ITEMS.length - 1;

  return (
    <main class="screen onboarding" data-stage="about" data-item={patient ? items[0] : "all"}>
      <StepTitle title={say(a.titleSelf, a.titleOther)} />
      <p class="lead">{say(a.leadSelf, a.leadOther)}</p>
      {items.map((item) => (
        <Question key={item} item={item} draft={draft} answer={answer} patient={patient} busy={busy} />
      ))}
      {busy && <Status text={s.onboarding.saving} />}
      <Notice error={error} />
      {patient ? (
        <>
          {(ABOUT_ITEMS[index] === "name" || ABOUT_ITEMS[index] === "doctor") && (
            <Pill plum disabled={busy} onClick={() => (last ? void save(draft) : setIndex(index + 1))} testId="about-next">
              {s.onboarding.next}
            </Pill>
          )}
          {index > 0 && (
            <Pill quiet onClick={() => setIndex(index - 1)} testId="about-back">
              {s.onboarding.back}
            </Pill>
          )}
        </>
      ) : (
        <Pill plum disabled={busy} onClick={() => void save(draft)} testId="about-next">
          {s.onboarding.next}
        </Pill>
      )}
      {index === 0 && (
        <Pill quiet onClick={finish} testId="set-up-later">
          {s.onboarding.later}
        </Pill>
      )}
    </main>
  );
}

interface QuestionProps {
  item: AboutItem;
  draft: SettingsIn;
  answer: (patch: Partial<SettingsIn>, advance: boolean) => void;
  patient: boolean;
  busy: boolean;
}

function Question({ item, draft, answer, patient, busy }: QuestionProps): JSX.Element {
  const s = t();
  const a = s.onboarding.about;
  const skip = (patch: Partial<SettingsIn>) =>
    patient ? (
      <Pill quiet onClick={() => answer(patch, true)} testId={`${item}-not-now`}>
        {s.onboarding.notNow}
      </Pill>
    ) : null;

  switch (item) {
    case "name": {
      const question = say(a.nameSelf, a.nameOther);
      return (
        <Sheet title={question} testId="about-name">
          <Field name="preferred-name" label={a.nameLabel} value={draft.preferred_name ?? ""} onInput={(value) => answer({ preferred_name: value }, false)} autoComplete="nickname" />
        </Sheet>
      );
    }
    case "language": {
      const names: Record<Language, string> = { en: s.me.en, ms: s.me.ms, zh: s.me.zh };
      return (
        <Sheet title={say(a.languageSelf, a.languageOther)} testId="about-language">
          <div class="choices" role="group">
            {LANGUAGES.map((code) => (
              <Pill key={code} onClick={() => answer({ language: code }, true)} testId={`about-lang-${code}`} chosen={draft.language === code} disabled={busy}>
                {names[code]}
              </Pill>
            ))}
          </div>
        </Sheet>
      );
    }
    case "born":
      return (
        <Sheet title={say(a.bornSelf, a.bornOther)} testId="about-born">
          <div class="choices two" role="group">
            {DECADES.map((decade) => (
              <Pill key={decade} onClick={() => answer({ birth_decade: decade }, true)} testId={`decade-${decade}`} chosen={draft.birth_decade === decade} disabled={busy}>
                {fill(a.decade, { decade })}
              </Pill>
            ))}
          </div>
          {skip({ birth_decade: null })}
        </Sheet>
      );
    case "doctor":
      return (
        <Sheet title={say(a.doctorSelf, a.doctorOther)} lines={[a.doctorHint]} testId="about-doctor">
          <Field name="doctor" label={a.doctorLabel} value={draft.doctor ?? ""} onInput={(value) => answer({ doctor: value }, false)} />
        </Sheet>
      );
    case "breakfast":
      return (
        <Sheet title={say(a.breakfastSelf, a.breakfastOther)} lines={[a.breakfastHint]} testId="about-breakfast">
          <div class="choices two" role="group">
            {BREAKFAST_TIMES.map((time) => (
              <Pill key={time} onClick={() => answer({ breakfast_time: time }, true)} testId={`breakfast-${time}`} chosen={draft.breakfast_time === time} disabled={busy}>
                {a.times[time]}
              </Pill>
            ))}
          </div>
          {skip({ breakfast_time: null })}
        </Sheet>
      );
    default: {
      if (!isFunctionItem(item)) return <></>;
      const field = FUNCTION_TILES[item];
      const question = {
        sight: say(a.sightSelf, a.sightOther),
        hearing: say(a.hearingSelf, a.hearingOther),
        hands: say(a.handsSelf, a.handsOther),
        memory: say(a.memorySelf, a.memoryOther),
      }[item];
      return (
        <Sheet title={question} testId={`about-${item}`}>
          <div class="choices two" role="group">
            <Pill onClick={() => answer({ [field]: true }, true)} testId={`${item}-yes`} chosen={!patient && draft[field]} disabled={busy}>
              {a.yes}
            </Pill>
            <Pill onClick={() => answer({ [field]: false }, true)} testId={`${item}-no`} chosen={!patient && !draft[field]} disabled={busy}>
              {a.no}
            </Pill>
          </div>
        </Sheet>
      );
    }
  }
}
