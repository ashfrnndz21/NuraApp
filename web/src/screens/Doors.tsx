import { signal } from "@preact/signals";
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
import { Icon, MessageBubble, Orb, Reveal, SoftText, type IconName } from "../ui/kit";

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

/** His name, the moment the `who` scene's own reply has it — a fresh phone's name lives only
 *  here until his profile is created (`ConsentScreen.agree`), so the consent turn right after
 *  never asks for it again. Cleared once spent (`ConsentScreen`), same discipline as a
 *  one-time-use field. */
const pendingName = signal("");

/** The "who" scene's own reply, once "Me" is chosen (docs/design/experience-blueprint.html
 *  `who`): his name comes back as his own turn ("Me. My name is Tan."), then Nura's ("Good to
 *  meet you, Tan.") and the one privacy sentence, then a single Continue on to consent — never
 *  an instant jump with nothing said. A name already known from sign-in (`signInThroughTheApp`,
 *  the usual case) skips straight to that reply; a bare phone number with no name yet asks for
 *  one first, in the same turn. */
function WhoMeReply({ name, onName, onContinue }: { name: string; onName: (value: string) => void; onContinue: () => void }): JSX.Element {
  const s = t();
  const trimmed = name.trim();
  const [confirmed, setConfirmed] = useState(Boolean(me.value?.display_name?.trim()));
  // A name is never required here — a name typed nowhere at all is how E01-01's bare-profile
  // gate is tested, and stays real: skipping leaves `pendingName` empty, the same as never
  // having asked, and `ConsentScreen`'s own field still gets a later chance at it.
  const skip = () => {
    pendingName.value = "";
    onContinue();
  };
  return (
    <div class="who-me">
      {!confirmed ? (
        <Reveal>
          <Field name="who-name" label={s.signIn.nameLabel} value={name} onInput={onName} autoComplete="given-name" />
          <div class="choices two" role="group">
            <Pill plum onClick={() => setConfirmed(true)} disabled={!trimmed} testId="who-name-continue">
              {s.doors.continueWord}
            </Pill>
            <Pill quiet onClick={skip} testId="who-name-skip">
              {s.onboarding.notNow}
            </Pill>
          </div>
        </Reveal>
      ) : (
        <>
          <Reveal>
            {/* Two lines in the source (docs/plain-words.md rule 2, one idea a line) read as
             *  his one reply, the blueprint's own "Me. My name is Tan." in a single bubble. */}
            <MessageBubble from="person" testId="who-me-reply">
              {s.doors.meIntro} {fill(s.doors.meName, { name: trimmed })}
            </MessageBubble>
          </Reveal>
          <Reveal>
            <div class="who-say">
              <Orb size="sm" />
              <div class="who-say-lines">
                <SoftText text={fill(s.doors.met, { name: trimmed })} pace="headline" as="p" className="who-say-line" testId="who-met" />
                <SoftText text={s.doors.privacyKeeps} pace="body" as="p" className="who-say-line" />
                <SoftText text={s.doors.privacyChoose} pace="body" as="p" className="who-say-line" />
              </div>
            </div>
          </Reveal>
          <Reveal>
            <Pill
              plum
              onClick={() => {
                pendingName.value = trimmed;
                onContinue();
              }}
              testId="who-continue"
            >
              {s.doors.continueWord}
            </Pill>
          </Reveal>
        </>
      )}
    </div>
  );
}

/** The doors, one choice per tile: my own papers, papers waiting for me, papers I was let in
 *  to, and the two ways to begin. A chief with several keys sees every one here and picks. */
export function DoorsScreen({ doors, refusal }: { doors: DoorsOut; refusal?: string }): JSX.Element {
  const s = t();
  const keys = [...doors.invited, ...doors.stewarding];
  const hasAny = doors.own || keys.length > 0 || doors.claimable.length > 0;
  const [metMe, setMetMe] = useState(false);
  const [whoName, setWhoName] = useState(me.value?.display_name ?? "");
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
      {/* The `who` scene (docs/design/experience-blueprint.html): a conversation, not a pair of
          cards — Nura's question, his answer as chips, his choice echoed back as his own turn,
          then hers. A chief switching between keys she already holds sees the plain header
          above instead (`hasAny`), and keeps the plain choose-cards below unchanged: that is
          the switcher adding a profile, not a fresh phone's first minute. */}
      {!hasAny && !metMe && (
        <>
          <div class="who-say">
            <Orb size="sm" />
            <SoftText text={s.doors.greeting} pace="headline" as="p" className="who-say-line" testId="who-greeting" />
          </div>
          <div class="choices" role="group" aria-label={s.doors.greeting} data-testid="who-chips">
            <Pill onClick={() => setMetMe(true)} testId="door-for-me">
              {s.doors.forMe}
            </Pill>
            <Pill onClick={() => go({ name: "forSomeone" })} testId="door-for-someone">
              {s.doors.forSomeone}
            </Pill>
          </div>
        </>
      )}
      {!hasAny && metMe && <WhoMeReply name={whoName} onName={setWhoName} onContinue={() => go({ name: "consent" })} />}
      {hasAny && (
        <div class="choose-cards">
          {!doors.own && doors.claimable.length === 0 && (
            <ChooseCard icon="profile" title={s.doors.forMe} line={s.doors.forMeLine} onClick={() => go({ name: "consent" })} testId="door-for-me" />
          )}
          <ChooseCard icon="care" title={s.doors.forSomeone} line={s.doors.forSomeoneLine} onClick={() => go({ name: "forSomeone" })} testId="door-for-someone" />
        </div>
      )}
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
  // The `who` turn just before this one already has his name (typed at sign-in, or given right
  // there when it was not) — `pendingName`, set the moment its own Continue is tapped. This
  // screen never asks for it a second time; it only falls back to its own field on whatever
  // narrower path still reaches `consent` without going through `who` first.
  // `pendingName` is a signal seeded with "" (never nullish), so the trailing `?? ""` here never
  // fired — dropped.
  const [name, setName] = useState(me.value?.display_name ?? pendingName.value);
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
      const known = me.value?.display_name?.trim() || pendingName.value.trim() || "";
      const opened = await nura.openOwnProfile(bearer, {
        version: words.version,
        language: words.language,
        display_name: (known || name.trim()) || null,
      });
      pendingName.value = "";
      await startOnboarding(opened);
    } catch (failure) {
      // Spent the moment this attempt read it (`known`, above) whether it goes on to succeed or
      // not — a failed submit used to leave the old value sitting in this one-time-use signal,
      // so a later re-entry (back out of this screen, in again down a path that does not go
      // through `who` first) would reuse the stale name and hide the field a second time.
      pendingName.value = "";
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main class="screen">
      <Header title={s.consent.title} onBack={reloadDoors} />
      {/* The `consent` scene, as the blueprint's own conversation screens draw it (`signin`,
       *  `who`): the orb, one line of Nura's beside it — never a second headline, `Header`
       *  above already carries the screen's one `<h1>` (E15-04's rule, `.signin-say-line`'s own
       *  comment). No card, no form chrome: the versioned words themselves (`words.lines`,
       *  untouched — this is where their exact text lives) arrive one sentence at a time. */}
      <div class="consent-say">
        <Orb size="sm" />
        <SoftText text={s.consent.lead} pace="headline" as="p" className="consent-say-line" testId="consent-lead" />
      </div>
      <div class="consent-lines" data-testid="consent-words">
        {words?.lines.map((line, index) => (
          <Reveal key={index} className="consent-line">
            <SoftText text={line} pace="body" as="p" />
          </Reveal>
        ))}
      </div>
      {!me.value?.display_name && !pendingName.value && (
        <Reveal>
          <Field name="name" label={s.signIn.nameLabel} value={name} onInput={setName} autoComplete="given-name" />
        </Reveal>
      )}
      {/* Never a dimmed, hard-to-read pill on this dark ground while the words are still
       *  loading (`.pill:disabled`'s own `opacity: 0.6` reads fine on the old white card this
       *  screen no longer has) — the pill simply is not there yet, same discipline as every
       *  other "arrives when real" line on this screen. */}
      {words && (
        <Reveal>
          <Pill plum onClick={agree} disabled={busy} testId="agree">
            {s.consent.agree}
          </Pill>
        </Reveal>
      )}
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
