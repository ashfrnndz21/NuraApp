import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { ClaimableOut, DoorsOut, ProfileOut, WordingOut } from "../api/types";
import { afterSignIn, go, openProfile, reloadDoors } from "../flow";
import { me, token } from "../store/session";
import { fill, language, t } from "../strings";
import { Field, Header, Notice, Pill, Tile } from "../ui/components";

function roleLine(each: ProfileOut): string {
  const s = t();
  if (each.standing === "owner") return s.switcher.roleOwner;
  if (each.standing === "steward") return s.switcher.roleSteward;
  if (each.role === "chief") return s.switcher.roleChief;
  if (each.role === "caregiver" || each.role === "helper") return s.switcher.roleCaregiver;
  return s.switcher.roleOther;
}

/** The doors, one choice per tile: my own papers, papers waiting for me, papers I was let in
 *  to, and the two ways to begin. A chief with several keys sees every one here and picks. */
export function DoorsScreen({ doors }: { doors: DoorsOut }): JSX.Element {
  const s = t();
  const keys = [...doors.invited, ...doors.stewarding];
  const hasAny = doors.own || keys.length > 0 || doors.claimable.length > 0;
  return (
    <main class="screen">
      <Header title={hasAny ? s.switcher.title : s.doors.title} />
      {doors.own && (
        <Tile paper>
          <button type="button" class="choice" onClick={() => openProfile(doors.own!)} data-testid="door-own">
            <div class="title">{s.switcher.own}</div>
            <p>{s.switcher.roleOwner}</p>
          </button>
        </Tile>
      )}
      {doors.claimable.map((offer) => (
        <Tile paper key={offer.profile_id}>
          <button type="button" class="choice" onClick={() => go({ name: "claim", offer })} data-testid="door-claim">
            <div class="title">{s.doors.waiting}</div>
            <p>{fill(s.doors.waitingLine, { name: offer.set_up_by })}</p>
          </button>
        </Tile>
      ))}
      {keys.map((each) => (
        <Tile paper key={each.profile_id}>
          <button type="button" class="choice" onClick={() => openProfile(each)} data-testid="door-key">
            <div class="title">{each.display_name}</div>
            <p>{roleLine(each)}</p>
          </button>
        </Tile>
      ))}
      {!doors.own && doors.claimable.length === 0 && (
        <Tile paper>
          <button type="button" class="choice" onClick={() => go({ name: "consent" })} data-testid="door-for-me">
            <div class="title">{s.doors.forMe}</div>
            <p>{s.doors.forMeLine}</p>
          </button>
        </Tile>
      )}
      <Tile paper>
        <button type="button" class="choice" onClick={() => go({ name: "forSomeone" })} data-testid="door-for-someone">
          <div class="title">{s.doors.forSomeone}</div>
          <p>{s.doors.forSomeoneLine}</p>
        </button>
      </Tile>
    </main>
  );
}

/** The for-me door: today's words, read, then one "I agree". The version comes from the
 *  API with the words, so the yes is for exactly what was shown. */
export function ConsentScreen(): JSX.Element {
  const s = t();
  const [words, setWords] = useState<WordingOut | null>(null);
  const [name, setName] = useState(me.value?.display_name ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    nura.wording(language.value).then(setWords, setError);
  }, [language.value]);

  const agree = async () => {
    const bearer = token.value;
    if (!bearer || !words) return;
    setBusy(true);
    setError(null);
    try {
      const opened = await nura.openOwnProfile(bearer, {
        version: words.version,
        language: words.language,
        display_name: name.trim() || null,
      });
      await openProfile(opened);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.consent.title} onBack={reloadDoors} />
      <Tile paper sheet testId="consent-words">
        <p>{s.consent.lead}</p>
        <div class="lines">{words?.lines.map((line, index) => <p key={index}>{line}</p>)}</div>
        {!me.value?.display_name && <Field name="name" label={s.signIn.nameLabel} value={name} onInput={setName} autoComplete="given-name" />}
        <Pill plum onClick={agree} disabled={busy || !words} testId="agree">
          {s.consent.agree}
        </Pill>
      </Tile>
      <Notice error={error} />
    </main>
  );
}

/** Papers set up for his number: who did it, what they keep seeing, the words, one yes. */
export function ClaimScreen({ offer }: { offer: ClaimableOut }): JSX.Element {
  const s = t();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const claimIt = async () => {
    const bearer = token.value;
    if (!bearer) return;
    setBusy(true);
    setError(null);
    try {
      const yes = await nura.mintClaim(bearer, offer.profile_id, offer.words_language);
      const owned = await nura.claim(bearer, offer.profile_id, yes.confirmation_id, offer.words_language);
      await openProfile(owned);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const setUpBy = offer.relationship
    ? fill(s.claim.setUpBy, { name: offer.set_up_by, relationship: offer.relationship })
    : fill(s.doors.waitingLine, { name: offer.set_up_by });

  return (
    <main class="screen">
      <Header title={s.claim.title} onBack={reloadDoors} />
      <Tile paper sheet>
        <p>{setUpBy}</p>
        <div class="lines">{offer.hold_words.split("\n").map((line, index) => <p key={index}>{line}</p>)}</div>
        <p>{fill(s.claim.keepsSeeing, { name: offer.set_up_by })}</p>
        <div class="lines">{offer.sharing_words.split("\n").map((line, index) => <p key={index}>{line}</p>)}</div>
        <Pill plum onClick={claimIt} disabled={busy} testId="claim">
          {s.claim.mine}
        </Pill>
      </Tile>
      <Notice error={error} />
    </main>
  );
}

/** The for-someone door: their name and number, who they are to you, and that they asked. */
export function ForSomeoneScreen(): JSX.Element {
  const s = t();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("+65");
  const [relationship, setRelationship] = useState("");
  const [asked, setAsked] = useState(false);
  const [words, setWords] = useState<WordingOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    nura.wording(language.value).then(setWords, setError);
  }, [language.value]);

  const create = async () => {
    const bearer = token.value;
    if (!bearer || !words) return;
    setBusy(true);
    setError(null);
    try {
      const made = await nura.setUpForSomeone(bearer, {
        patient_phone_e164: phone.replace(/\s+/g, ""),
        display_name: name.trim(),
        language: words.language,
        version: words.version,
        relationship: relationship.trim() || null,
      });
      await openProfile(made);
      await afterSignIn();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.forSomeone.title} onBack={reloadDoors} />
      <Tile paper sheet>
        <p>{s.forSomeone.lead}</p>
        <Field name="their-name" label={s.forSomeone.theirName} value={name} onInput={setName} />
        <Field name="their-phone" label={s.forSomeone.theirPhone} value={phone} onInput={setPhone} type="tel" inputMode="tel" />
        <Field name="relationship" label={s.forSomeone.relationshipLabel} value={relationship} onInput={setRelationship} />
        <label class="check">
          <input type="checkbox" checked={asked} onChange={(event) => setAsked((event.target as HTMLInputElement).checked)} />
          <span>{s.forSomeone.asked}</span>
        </label>
        <div class="lines">{words?.lines.map((line, index) => <p key={index} class="caption">{line}</p>)}</div>
        <Pill plum onClick={create} disabled={busy || !words || !asked || name.trim().length === 0 || phone.replace(/\D/g, "").length < 8}>
          {s.forSomeone.create}
        </Pill>
      </Tile>
      <Notice error={error} />
    </main>
  );
}
