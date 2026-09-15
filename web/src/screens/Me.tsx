import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { MeSummaryOut } from "../api/types";
import { closeMe, go, meOpen, openTab, reloadDoors, signOutEverywhere } from "../flow";
import { emergencyOnly } from "../offline/emergencyCache";
import { wantsHomeScreenHint } from "../offline/register";
import { startOnboarding } from "../onboarding/state";
import { backendFor, browserEnv, remindersState, turnOff, turnOn, type RemindersState } from "../push/reminders";
import { pushKey } from "../store/deployment";
import { density, densityChosen, me, profile, setDensity, setLanguage, token } from "../store/session";
import { fill, LANGUAGES, language, t, type Language } from "../strings";
import { proudLine } from "../today/model";
import { todayPage } from "../today/page";
import { Hear, Pill, Tile } from "../ui/components";
import { Sheet } from "../ui/kit";

/** Me (D1): a sheet from the header's avatar, over whatever screen is open — never a tab. Who
 *  is signed in; the number that only goes up; the language; how Nura looks; his family (the
 *  chief has Family as a tab); whose papers; setting up; reminders on this phone; sign out.
 *  Everything that was on the Me tab is here, one tap from any screen. */
export function MeSheet(): JSX.Element | null {
  const s = t();
  const open = meOpen.value;
  // A key to the emergency card alone: nothing here opens more of the papers than that.
  const only = profile.value ? emergencyOnly(profile.value) : false;
  const names: Record<Language, string> = { en: s.me.en, ms: s.me.ms, zh: s.me.zh };
  const bearer = token.value;
  const papers = profile.value;
  const patient = density() === "patient";
  // The number that only goes up (E17-04), on his own Me, in the backend's words.
  // "failed": the summary could not be read (offline) — then the count Today read stands in.
  const [summary, setSummary] = useState<MeSummaryOut | "failed" | null>(null);
  const owner = papers?.standing === "owner";
  useEffect(() => {
    if (!open || !bearer || !papers || !owner) return setSummary(null);
    nura.meSummary(bearer, papers.profile_id, language.value).then(setSummary, () => setSummary("failed"));
  }, [open, bearer, papers?.profile_id, language.value]);
  const said = summary !== null && summary !== "failed" ? summary : null;
  // His own count waits for his own words; anyone else's view, or his offline, is Today's.
  // Today's page stands in only for the papers it was read from: never another profile's count.
  const page = todayPage.value !== null && todayPage.value.profileId === papers?.profile_id ? todayPage.value.model : null;
  const standIn = page !== null && (!owner || summary === "failed");
  // Escape closes it; opening it puts the screen reader on its title.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMe();
    };
    document.addEventListener("keydown", onKey);
    document.getElementById("sheet-title")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Anyone else's view of the count, or his own when the summary cannot be read (offline):
  // the number Today read, never one counted here.
  const counted = page?.proud ?? null;
  const counts = proudLine(counted, s);
  return (
    <Sheet title={s.me.title} open={open} onClose={closeMe} closeLabel={s.shell.close} testId="me-sheet">
      {said ? (
        <Tile paper testId="me-proud">
          <div class="number" data-testid="me-proud-number">
            {said.proud_days}
          </div>
          <div class="lines" data-testid="me-proud-lines">
            {said.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
          <p class="provenance">{s.today.fromDays}</p>
          <Hear lines={said.lines} />
        </Tile>
      ) : (
        standIn && (
          <Tile paper testId="proud">
            <div class="number" data-testid="proud-number">
              {counted ?? 0}
            </div>
            <p>{counts}</p>
            <p class="caption">{s.today.proudSub}</p>
            <p class="provenance">{s.today.fromDays}</p>
            <Hear lines={[counts, s.today.proudSub]} />
          </Tile>
        )
      )}
      <Tile paper>
        <p>{fill(s.me.signedInAs, { name: me.value?.display_name || "" })}</p>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.language}</p>
        <div class="row" role="group" aria-label={s.me.language}>
          {LANGUAGES.map((code) => (
            <Pill key={code} chosen={language.value === code} onClick={() => void setLanguage(code)} testId={`lang-${code}`}>
              {names[code]}
            </Pill>
          ))}
        </div>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.look}</p>
        <div class="row" role="group" aria-label={s.me.look}>
          <Pill chosen={density() === "patient"} onClick={() => void setDensity("patient")} testId="density-patient">
            {s.me.patient}
          </Pill>
          <Pill chosen={density() === "caregiver"} onClick={() => void setDensity("caregiver")} testId="density-caregiver">
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
        {patient && papers && (
          <Pill onClick={() => openTab("family")} testId="me-family">
            {s.tabs.family}
          </Pill>
        )}
        <Pill onClick={() => void reloadDoors()} testId="switch-profile">
          {s.me.switchProfile}
        </Pill>
        {papers && !only && (
          <Pill onClick={() => void startOnboarding(papers)} testId="set-up">
            {s.me.setUp}
          </Pill>
        )}
        {profile.value && (profile.value.standing === "owner" || profile.value.scopes.includes("records")) && (
          <Pill onClick={() => go({ name: "papers" })} testId="open-papers">
            {s.papers.open}
          </Pill>
        )}
      </Tile>
      <Reminders />
      {papers && (papers.standing === "owner" || papers.scopes.includes("emergency")) && (
        <Tile paper>
          <Pill
            onClick={() => {
              closeMe();
              go({ name: "emergency" });
            }}
            testId="me-emergency"
          >
            {s.today.emergencyTitle}
          </Pill>
        </Tile>
      )}
      {wantsHomeScreenHint() && (
        <Tile glass>
          <p>{s.today.homeScreen1}</p>
          <p>{s.today.homeScreen2}</p>
          <p>{s.today.homeScreen3}</p>
        </Tile>
      )}
      <Tile paper>
        <Pill onClick={() => void signOutEverywhere()} testId="sign-out">
          {s.me.signOut}
        </Pill>
      </Tile>
    </Sheet>
  );
}

/** "Get reminders on this phone" (Web Push, ADR 0001): only where this deployment has Web Push
 *  and this browser can take it. Nothing is asked of the phone until the button is tapped. */
function Reminders(): JSX.Element | null {
  const s = t();
  const env = browserEnv();
  const [state, setState] = useState<RemindersState>("unsupported");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void remindersState(env).then(setState);
  }, []);
  const key = pushKey.value;
  const bearer = token.value;
  const profileId = profile.value?.profile_id;
  if (!key || !env || !bearer || !profileId || state === "unsupported") return null;
  const tap = async (on: boolean) => {
    setBusy(true);
    try {
      const backend = backendFor(bearer, profileId);
      setState(on ? await turnOn(env, key, backend) : await turnOff(env, backend));
    } catch {
      setState(await remindersState(env));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Tile paper>
      {state === "on" && <p data-testid="reminders-on">{s.me.remindersOn}</p>}
      {state === "denied" && (
        <div data-testid="reminders-denied">
          <p>{s.me.remindersDenied1}</p>
          <p>{s.me.remindersDenied2}</p>
        </div>
      )}
      {state === "on" ? (
        <Pill onClick={() => void tap(false)} disabled={busy} testId="reminders-stop">
          {s.me.remindersStop}
        </Pill>
      ) : (
        state === "off" && (
          <Pill plum onClick={() => void tap(true)} disabled={busy} testId="reminders-get">
            {s.me.remindersGet}
          </Pill>
        )
      )}
    </Tile>
  );
}
