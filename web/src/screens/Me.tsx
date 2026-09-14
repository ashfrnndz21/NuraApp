import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { MeSummaryOut } from "../api/types";
import { go, openTab, reloadDoors, signOutEverywhere } from "../flow";
import { wantsHomeScreenHint } from "../offline/register";
import { startOnboarding } from "../onboarding/state";
import { density, densityChosen, me, profile, setDensity, setLanguage, token } from "../store/session";
import { fill, LANGUAGES, language, t, type Language } from "../strings";
import { Header, Hear, Pill, TabBar, Tile } from "../ui/components";

/** Me: who is signed in, the language, how Nura looks, whose papers, sign out. */
export function MeScreen(): JSX.Element {
  const s = t();
  const names: Record<Language, string> = { en: s.me.en, ms: s.me.ms, zh: s.me.zh };
  const bearer = token.value;
  const papers = profile.value;
  // The number that only goes up (E17-04), on his own Me page, in the backend's words.
  const [proud, setProud] = useState<MeSummaryOut | null>(null);
  useEffect(() => {
    if (!bearer || !papers || papers.standing !== "owner") return setProud(null);
    nura.meSummary(bearer, papers.profile_id, language.value).then(setProud, () => setProud(null));
  }, [bearer, papers?.profile_id, language.value]);
  return (
    <main class="screen">
      <Header title={s.me.title} />
      {proud && (
        <Tile paper testId="me-proud">
          <div class="number" data-testid="me-proud-number">
            {proud.proud_days}
          </div>
          <div class="lines" data-testid="me-proud-lines">
            {proud.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
          <p class="provenance">{s.today.fromDays}</p>
          <Hear lines={proud.lines} />
        </Tile>
      )}
      <Tile paper>
        <p>{fill(s.me.signedInAs, { name: me.value?.display_name || "" })}</p>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.language}</p>
        <div class="row" role="group" aria-label={s.me.language}>
          {LANGUAGES.map((code) => (
            <Pill key={code} plum={language.value === code} onClick={() => void setLanguage(code)} testId={`lang-${code}`}>
              {names[code]}
            </Pill>
          ))}
        </div>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.look}</p>
        <div class="row" role="group" aria-label={s.me.look}>
          <Pill plum={density() === "patient"} onClick={() => void setDensity("patient")} testId="density-patient">
            {s.me.patient}
          </Pill>
          <Pill plum={density() === "caregiver"} onClick={() => void setDensity("caregiver")} testId="density-caregiver">
            {s.me.caregiver}
          </Pill>
        </div>
        {densityChosen.value && (
          <Pill quiet onClick={() => void setDensity(null)}>
            {s.me.lookAuto}
          </Pill>
        )}
      </Tile>
      <Tile paper>
        <Pill onClick={() => void reloadDoors()} testId="switch-profile">
          {s.me.switchProfile}
        </Pill>
        {profile.value && (
          <Pill onClick={() => void startOnboarding(profile.value!)} testId="set-up">
            {s.me.setUp}
          </Pill>
        )}
      </Tile>
      {wantsHomeScreenHint() && (
        <Tile glass>
          <p>{s.today.homeScreen1}</p>
          <p>{s.today.homeScreen2}</p>
        </Tile>
      )}
      <Tile paper>
        <Pill onClick={() => void signOutEverywhere()} testId="sign-out">
          {s.me.signOut}
        </Pill>
      </Tile>
      <TabBar current="me" onSelect={openTab} />
    </main>
  );
}
