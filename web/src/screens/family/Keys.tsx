import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { SharingPreviewOut } from "../../api/types";
import type { GrantOut, KeyRole, KeyWindow, RolePresetOut, Scope } from "../../api/familyTypes";
import { PARTS, partsOf, ROLES, WINDOWS } from "../../family/model";
import { Field, Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead, type Here } from "./common";

/** E12-01: every live key as a grant in his words; a key made with a role, the parts and a
 *  window; one made smaller in place on a yes; one closed. Wider is the backend's no, in its
 *  words — the parts and the windows are all offered, so a person can ask and be told. */
export function KeysPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const list = useRead(here ? () => family.grants(here.bearer, here.papers.profile_id, here.lang) : null, [here?.papers.profile_id, here?.lang]);
  if (!here) return null;
  return (
    <FamilyPage title={words.keys} part="keys">
      <Notice error={list.error} />
      {list.value?.map((grant) => (
        <GrantTile key={grant.key_id} grant={grant} here={here} act={a} reload={list.reload} />
      ))}
      <NewKey here={here} act={a} reload={list.reload} />
    </FamilyPage>
  );
}

type Act = ReturnType<typeof useAct>;

function toggle(parts: Scope[], part: Scope): Scope[] {
  return parts.includes(part) ? parts.filter((each) => each !== part) : PARTS.filter((each) => each === part || parts.includes(each));
}

function PartChoices({ chosen, onToggle, testId }: { chosen: Scope[]; onToggle: (part: Scope) => void; testId: string }): JSX.Element {
  const words = s();
  return (
    <div class="choices" role="group" aria-label={words.partsLabel} data-testid={testId}>
      {PARTS.map((part) => (
        <Pill key={part} chosen={chosen.includes(part)} onClick={() => onToggle(part)} testId={`${testId}-${part}`}>
          {words.parts[part]}
        </Pill>
      ))}
    </div>
  );
}

function WindowChoices({ chosen, onChoose, testId }: { chosen: KeyWindow | null; onChoose: (window: KeyWindow) => void; testId: string }): JSX.Element {
  const words = s();
  return (
    <div class="choices" role="group" aria-label={words.windowLabel} data-testid={testId}>
      {WINDOWS.map((window) => (
        <Pill key={window} chosen={chosen === window} onClick={() => onChoose(window)} testId={`${testId}-${window}`}>
          {words.windows[window]}
        </Pill>
      ))}
    </div>
  );
}

function GrantTile({ grant, here, act, reload }: { grant: GrantOut; here: Here; act: Act; reload: () => Promise<void> }): JSX.Element {
  const words = s();
  const [mode, setMode] = useState<"none" | "narrow" | "close">("none");
  const [parts, setParts] = useState<Scope[]>(partsOf(grant.scopes));
  const [window, setWindow] = useState<KeyWindow | null>(grant.window);
  const pid = here.papers.profile_id;
  const narrow = () =>
    act.act(grant.key_id, async () => {
      // The window is sent only when it changes: the same window again, from now, would end
      // later than the one the key has — wider, and refused.
      const shorter = window !== grant.window ? window : null;
      const yes = await family.mintKeyChange(here.bearer, pid, grant.key_id, parts, shorter);
      await family.narrowKey(here.bearer, pid, grant.key_id, parts, shorter, yes.confirmation_id);
      setMode("none");
      await reload();
    });
  const close = () =>
    act.act(grant.key_id, async () => {
      await family.closeKey(here.bearer, pid, grant.key_id);
      await reload();
    });
  return (
    <Tile paper testId="grant">
      <Lines lines={grant.lines} testId="grant-lines" />
      {mode === "none" && (
        <div class="row">
          <Pill onClick={() => setMode("narrow")} testId="narrow">
            {words.narrow}
          </Pill>
          <Pill onClick={() => setMode("close")} testId="close-key">
            {words.closeKey}
          </Pill>
        </div>
      )}
      {mode === "narrow" && (
        <>
          <p class="label">{words.partsLabel}</p>
          <PartChoices chosen={parts} onToggle={(part) => setParts(toggle(parts, part))} testId="narrow-part" />
          <p class="label">{words.windowLabel}</p>
          <WindowChoices chosen={window} onChoose={setWindow} testId="narrow-window" />
          <Pill plum onClick={() => void narrow()} disabled={act.busy} testId="narrow-yes">
            {words.narrowYes}
          </Pill>
          <Pill quiet onClick={() => (setMode("none"), act.clear())} testId="narrow-cancel">
            {words.notNow}
          </Pill>
        </>
      )}
      {mode === "close" && (
        <>
          <Pill plum onClick={() => void close()} disabled={act.busy} testId="close-yes">
            {words.closeYes}
          </Pill>
          <Pill quiet onClick={() => (setMode("none"), act.clear())} testId="close-cancel">
            {words.notNow}
          </Pill>
        </>
      )}
      <NoticeAt act={act} where={grant.key_id} />
    </Tile>
  );
}

/** A key for one person: who, as what, which parts, for how long. The role's own words,
 *  said for the name typed, come from the backend (`GET /family/roles`).
 *
 *  Letting someone in at all rests on the owner's own agreement (`may_invite`): only he can
 *  give it, on his own basis, never a chief on his say-so. So the owner reads the sharing
 *  words the backend renders for this person and these parts (`POST
 *  /consents/sharing/preview`) and agrees to them before the key is cut, exactly as the
 *  invite gap of onboarding does (`Invite.tsx`) — changing who this is for, or the parts,
 *  after reading takes the words away. A chief cutting a key skips that: the key still
 *  rests on a sharing agreement, but it is one the owner already gave, earlier, himself; a
 *  chief naming someone the owner never let in is the backend's own refusal
 *  (`ConsentWithheld`), read where it happened. */
function NewKey({ here, act, reload }: { here: Here; act: Act; reload: () => Promise<void> }): JSX.Element {
  const words = s();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("+65");
  const [role, setRole] = useState<KeyRole | null>(null);
  const [parts, setParts] = useState<Scope[]>([]);
  const [window, setWindow] = useState<KeyWindow>("always");
  const [said, setSaid] = useState<RolePresetOut[] | null>(null);
  const [preview, setPreview] = useState<SharingPreviewOut | null>(null);
  const defaults = useRead(() => family.roles(here.bearer, here.lang, "Ash"), [here.lang]);
  useEffect(() => {
    const typed = name.trim();
    if (!typed) return setSaid(null);
    const timer = setTimeout(() => {
      family.roles(here.bearer, here.lang, typed).then(setSaid, () => setSaid(null));
    }, 250);
    return () => clearTimeout(timer);
  }, [name, here.lang]);
  // Changing who this is for, or what he is about to let them see, after reading the words
  // takes them away: the yes that follows is only ever for exactly what was shown.
  const changed = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setPreview(null);
  };
  // His own language changing under him (`Me.tsx`) takes the words away too: `asked()`
  // reads `here.lang`, and nothing else here would catch it.
  useEffect(() => setPreview(null), [here.lang]);
  const choose = (next: KeyRole) => {
    setRole(next);
    setPreview(null);
    const found = defaults.value?.find((each) => each.role === next);
    if (found) {
      setParts(partsOf(found.scopes));
      setWindow(found.window);
    }
  };
  const shown = role && said?.find((each) => each.role === role);
  const asked = () => ({
    holder_phone_e164: phone.replace(/\s+/g, ""),
    holder_display_name: name.trim(),
    scopes: parts,
    language: here.lang,
  });
  const seeWords = () =>
    act.act("new", async () => {
      setPreview(await family.previewSharing(here.bearer, here.papers.profile_id, asked()));
    });
  const cut = () =>
    act.act("new", async () => {
      if (!role) return;
      await family.makeKey(here.bearer, here.papers.profile_id, { holder_phone_e164: phone.replace(/\s+/g, ""), role, scopes: parts, window });
      setName("");
      setPhone("+65");
      setRole(null);
      setParts([]);
      await reload();
    });
  const agree = () =>
    act.act("new", async () => {
      if (!role || !preview) return;
      await family.letSomeoneIn(here.bearer, here.papers.profile_id, asked(), preview.wording_version);
      await family.makeKey(here.bearer, here.papers.profile_id, { holder_phone_e164: phone.replace(/\s+/g, ""), role, scopes: parts, window });
      setName("");
      setPhone("+65");
      setRole(null);
      setParts([]);
      setPreview(null);
      await reload();
    });
  const ready = !act.busy && !!name.trim() && phone.replace(/\D/g, "").length >= 8 && parts.length > 0;
  return (
    <Tile paper testId="new-key">
      <h2 class="title">{words.newKey}</h2>
      <Field name="key-holder-name" label={words.holderName} value={name} onInput={changed(setName)} autoComplete="off" />
      <Field name="key-holder-phone" label={words.holderPhone} value={phone} onInput={changed(setPhone)} type="tel" inputMode="tel" />
      <p class="label">{words.roleLabel}</p>
      <div class="choices" role="group" aria-label={words.roleLabel} data-testid="role">
        {ROLES.map((each) => (
          <Pill key={each} chosen={role === each} onClick={() => choose(each)} testId={`role-${each}`}>
            {words.roles[each]}
          </Pill>
        ))}
      </div>
      {shown && <Lines lines={shown.lines} testId="role-lines" />}
      {role && (
        <>
          <p class="label">{words.partsLabel}</p>
          <PartChoices chosen={parts} onToggle={(part) => changed(setParts)(toggle(parts, part))} testId="new-part" />
          <p class="label">{words.windowLabel}</p>
          <WindowChoices chosen={window} onChoose={changed(setWindow)} testId="new-window" />
          {!here.owner && (
            <Pill plum onClick={() => void cut()} disabled={!ready} testId="make-key">
              {words.makeKey}
            </Pill>
          )}
          {here.owner && !preview && (
            <Pill plum onClick={() => void seeWords()} disabled={!ready} testId="see-words">
              {words.seeWords}
            </Pill>
          )}
          {here.owner && preview && (
            <>
              <p class="label">{words.wordsLead}</p>
              <Lines lines={preview.lines} testId="new-words" />
              <Pill plum onClick={() => void agree()} disabled={act.busy} testId="agree-key">
                {words.agreeKey}
              </Pill>
            </>
          )}
        </>
      )}
      <NoticeAt act={act} where="new" />
    </Tile>
  );
}
