import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { SettingsIn } from "../../api/types";
import { openSitting, refreshPlan, saveSettings } from "../../onboarding/actions";
import { ABOUT_ITEMS, BREAKFAST_TIMES, DECADES, isSwitch, startingSettings, type AboutItem } from "../../onboarding/about";
import { biography, draft, finish, picked, say, settings, to, whose } from "../../onboarding/state";
import { density, profile, setLanguage, token } from "../../store/session";
import { fill, isLanguage, LANGUAGES, language, t, type Language } from "../../strings";
import { Field, Notice, Pill } from "../../ui/components";
import { Sheet, StepTitle } from "./parts";

/** About you (E01-03, #117's settings): name, language, birth decade, the doctor, breakfast,
 *  then one plain question per switch the settings hold, and how much to show at once. The
 *  patient answers one question per screen — a tap on a choice is the answer — and the
 *  caregiver density shows them all on one page. Nothing is sent here: the answers wait as a
 *  draft and go in one PUT with the words he taps next (#117 keeps the words in the settings).
 *  His language takes effect the moment he picks it. The sitting is opened here, so its own
 *  words for the step lead the screen. */
export function AboutStep({ only }: { only?: AboutItem } = {}): JSX.Element {
  const s = t();
  const a = s.onboarding.about;
  const papers = profile.value;
  const bearer = token.value;
  const patient = density() === "patient";
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!bearer || !papers) return;
    openSitting().catch(setError);
    nura.settings(bearer, papers.profile_id).then(
      (saved) => {
        settings.value = saved;
        if (!draft.value) {
          draft.value = startingSettings(saved, papers, language.value);
          picked.value = saved.conditions ?? [];
        }
      },
      (failure: unknown) => {
        setError(failure);
        if (!draft.value) draft.value = startingSettings(null, papers, language.value);
      },
    );
  }, [bearer, papers?.profile_id]);

  const current = draft.value;
  const bio = biography.value;
  // The sitting's own words for the step address him; a chief reads the app's.
  const own = whose().self && bio?.step === "about_you";
  const title = own ? bio.prompt.headline : say(a.titleSelf, a.titleOther);
  if (!current) {
    return (
      <main class="screen onboarding" data-stage="about">
        <StepTitle title={title} />
        <Notice error={error} />
      </main>
    );
  }

  const answer = (patch: Partial<SettingsIn>, advance: boolean) => {
    draft.value = { ...current, ...patch };
    if (only) {
      // One question from a gap card: save it with everything else, and back to the week.
      if (advance) {
        void saveSettings()
          .then(refreshPlan)
          .then(() => to({ name: "plan" }), setError);
      }
      return;
    }
    if (patch.language && isLanguage(patch.language) && papers?.standing === "owner") void setLanguage(patch.language);
    if (!patient || !advance) return;
    if (index + 1 < ABOUT_ITEMS.length) setIndex(index + 1);
    else to({ name: "cloud" });
  };

  const items = only ? [only] : patient ? [ABOUT_ITEMS[index]!] : [...ABOUT_ITEMS];
  const lead = own && bio.prompt.lines.length > 0 ? bio.prompt.lines : [say(a.leadSelf, a.leadOther)];
  const typed = ABOUT_ITEMS[index] === "name" || ABOUT_ITEMS[index] === "doctor";

  return (
    <main class="screen onboarding" data-stage="about" data-item={patient ? items[0] : "all"}>
      <StepTitle title={title} />
      {index === 0 &&
        !only &&
        lead.map((line, position) => (
          <p key={position} class="lead" data-testid="about-lead">
            {line}
          </p>
        ))}
      {items.map((item) => (
        <Question key={item} item={item} draft={current} answer={answer} patient={patient} />
      ))}
      <Notice error={error} />
      {only ? null : patient ? (
        <>
          {typed && (
            <Pill plum onClick={() => (index + 1 < ABOUT_ITEMS.length ? setIndex(index + 1) : to({ name: "cloud" }))} testId="about-next">
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
        <Pill plum onClick={() => to({ name: "cloud" })} testId="about-next">
          {s.onboarding.next}
        </Pill>
      )}
      {index === 0 && !only && (
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
}

function Question({ item, draft, answer, patient }: QuestionProps): JSX.Element {
  const s = t();
  const a = s.onboarding.about;
  const skip = (patch: Partial<SettingsIn>) =>
    patient ? (
      <Pill quiet onClick={() => answer(patch, true)} testId={`${item}-not-now`}>
        {s.onboarding.notNow}
      </Pill>
    ) : null;

  if (isSwitch(item)) {
    return (
      <Sheet title={say(a.switchSelf[item], a.switchOther[item])} testId={`about-${item}`}>
        <div class="choices two" role="group">
          <Pill onClick={() => answer({ [item]: true }, true)} testId={`${item}-yes`} chosen={!patient && draft[item]}>
            {a.yes}
          </Pill>
          <Pill onClick={() => answer({ [item]: false }, true)} testId={`${item}-no`} chosen={!patient && !draft[item]}>
            {a.no}
          </Pill>
        </div>
      </Sheet>
    );
  }

  switch (item) {
    case "name":
      return (
        <Sheet title={say(a.nameSelf, a.nameOther)} testId="about-name">
          <Field name="preferred-name" label={a.nameLabel} value={draft.preferred_name ?? ""} onInput={(value) => answer({ preferred_name: value }, false)} autoComplete="nickname" />
        </Sheet>
      );
    case "language": {
      const names: Record<Language, string> = { en: s.me.en, ms: s.me.ms, zh: s.me.zh };
      return (
        <Sheet title={say(a.languageSelf, a.languageOther)} testId="about-language">
          <div class="choices" role="group">
            {LANGUAGES.map((code) => (
              <Pill key={code} onClick={() => answer({ language: code }, true)} testId={`about-lang-${code}`} chosen={draft.language === code}>
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
              <Pill key={decade} onClick={() => answer({ birth_decade: decade }, true)} testId={`decade-${decade}`} chosen={draft.birth_decade === decade}>
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
          <Field name="doctor" label={a.doctorLabel} value={draft.doctor_name ?? ""} onInput={(value) => answer({ doctor_name: value }, false)} />
        </Sheet>
      );
    case "breakfast":
      return (
        <Sheet title={say(a.breakfastSelf, a.breakfastOther)} lines={[a.breakfastHint]} testId="about-breakfast">
          <div class="choices two" role="group">
            {BREAKFAST_TIMES.map((time) => (
              <Pill key={time} onClick={() => answer({ breakfast_time: time }, true)} testId={`breakfast-${time}`} chosen={draft.breakfast_time === time}>
                {a.times[time]}
              </Pill>
            ))}
          </div>
          {skip({ breakfast_time: null })}
        </Sheet>
      );
    default:
      return (
        <Sheet title={say(a.densitySelf, a.densityOther)} testId="about-density">
          <div class="choices" role="group">
            <Pill onClick={() => answer({ density: "simple" }, true)} testId="density-simple" chosen={draft.density === "simple"}>
              {a.densitySimple}
            </Pill>
            <Pill onClick={() => answer({ density: "detailed" }, true)} testId="density-detailed" chosen={draft.density === "detailed"}>
              {a.densityDetailed}
            </Pill>
          </div>
        </Sheet>
      );
  }
}
