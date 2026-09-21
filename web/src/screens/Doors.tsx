import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { ClaimableOut, DoorsOut, ProfileOut, WordingOut } from "../api/types";
import { go, openProfile, reloadDoors } from "../flow";
import { startOnboarding } from "../onboarding/state";
import { me, token } from "../store/session";
import { fill, language, t, RELATIONSHIPS, type Relationship } from "../strings";
import { canPickContact, pickContact } from "../onboarding/contact";
import { Field, Header, Notice, Pill, RefusalNotice, Tile } from "../ui/components";
import { Icon, Orb, SoftText, type IconName } from "../ui/kit";

/** One of the two large choose-cards a fresh phone sees (`who` scene: "for me" / "for someone I
 *  look after"). A plain `<button>`, kept at its existing test id, only its shape and look are
 *  new. */
function ChooseCard({ icon, title, line, onClick, testId }: { icon: IconName; title: string; line: string; onClick: () => void; testId: string }): JSX.Element {
  return (
    <button type="button" class="choose-card" onClick={onClick} data-testid={testId}>
      <span class="choose-card-icon" aria-hidden="true">
        <Icon name={icon} />
      </span>
      <span class="choose-card-body">
        <span class="choose-card-title">{title}</span>
        <span class="choose-card-line">{line}</span>
      </span>
    </button>
  );
}

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
export function DoorsScreen({ doors, refusal }: { doors: DoorsOut; refusal?: string }): JSX.Element {
  const s = t();
  const keys = [...doors.invited, ...doors.stewarding];
  const hasAny = doors.own || keys.length > 0 || doors.claimable.length > 0;
  return (
    <main class="screen">
      <Header title={hasAny ? s.switcher.title : s.doors.title} />
      <RefusalNotice refusal={refusal} />
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
      {/* The `who` scene (docs/design/experience-blueprint.html): Nura's own line, only for a
          phone with nothing open yet — a chief switching between keys she already holds sees
          the plain header above instead, unchanged. */}
      {!hasAny && (
        <div class="who-say">
          <Orb size="sm" />
          <SoftText text={s.doors.greeting} pace="headline" as="p" className="who-say-line" testId="who-greeting" />
        </div>
      )}
      <div class="choose-cards">
        {!doors.own && doors.claimable.length === 0 && (
          <ChooseCard icon="profile" title={s.doors.forMe} line={s.doors.forMeLine} onClick={() => go({ name: "consent" })} testId="door-for-me" />
        )}
        <ChooseCard icon="care" title={s.doors.forSomeone} line={s.doors.forSomeoneLine} onClick={() => go({ name: "forSomeone" })} testId="door-for-someone" />
      </div>
      {/* Someone waiting to be let in is sitting here when the key is cut. One tap asks the
          doors again, so the papers appear without signing out and back in. */}
      <Pill quiet onClick={() => void reloadDoors()} testId="doors-look-again">
        {s.doors.lookAgain}
      </Pill>
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
      // His name may already be known (typed at sign-in, `SignIn.tsx`) even though `/me` had
      // not yet answered when this screen first drew: the field then hides (the line below),
      // but `name`'s own state was seeded from `me.value?.display_name` at that same early
      // moment and never learns of a later answer — a plain `useState` does not re-read a
      // signal that changes after mount. Reading `me.value` again here, at the moment he taps
      // "I agree" rather than at the moment this screen first drew, is what the bug was:
      // sent as `null`, a self-registered profile's name came back blank, and every greeting
      // after it — "Good morning." with no name at all — was this one skipped answer.
      const known = me.value?.display_name?.trim() || "";
      const opened = await nura.openOwnProfile(bearer, {
        version: words.version,
        language: words.language,
        display_name: (known || name.trim()) || null,
      });
      await startOnboarding(opened);
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

  const setUpBy = offer.relationship_words
    ? fill(s.claim.setUpBy, { name: offer.set_up_by, relationship: offer.relationship_words })
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
  const [relationship, setRelationship] = useState<Relationship | null>(null);
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
        relationship,
      });
      await startOnboarding(made);
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
        {!phone.trim().startsWith("+") && (
          <p class="caption" data-testid="country-code">
            {s.signIn.phoneHint}
          </p>
        )}
        {canPickContact() && (
          <Pill
            quiet
            onClick={() =>
              void pickContact().then((picked) => {
                if (picked?.phone) setPhone(picked.phone);
                if (picked?.name && !name.trim()) setName(picked.name);
              })
            }
            testId="pick-contact"
          >
            {s.forSomeone.pickContact}
          </Pill>
        )}
        <p class="label">{s.forSomeone.relationshipLabel}</p>
        <div class="choices two" role="group" aria-label={s.forSomeone.relationshipLabel} data-testid="relationship">
          {RELATIONSHIPS.map((each) => (
            <Pill key={each} chosen={relationship === each} onClick={() => setRelationship(relationship === each ? null : each)} testId={`relationship-${each}`}>
              {s.forSomeone.relationships[each]}
            </Pill>
          ))}
        </div>
        <label class="check">
          <input type="checkbox" checked={asked} onChange={(event) => setAsked((event.target as HTMLInputElement).checked)} />
          <span>{s.forSomeone.asked}</span>
        </label>
        <div class="lines">{words?.lines.map((line, index) => <p key={index} class="caption">{line}</p>)}</div>
        <Pill plum onClick={create} disabled={busy || !words || !asked || name.trim().length === 0 || !phone.trim().startsWith("+") || phone.replace(/\D/g, "").length < 8}>
          {s.forSomeone.create}
        </Pill>
      </Tile>
      <Notice error={error} />
    </main>
  );
}
