import type { JSX } from "preact";
import type { ProfileOut, SignalFamily } from "../api/types";
import { fill, LANGUAGES, type Language, type Strings } from "../strings";
import { Pill } from "../ui/components";
import { Avatar, IconBadge, ListRow, SectionHeader, TintCard } from "../ui/kit";

/** Profile's warm parts (docs/design/nura-concept-board.html, the Profile screen): the person's
 *  own name and photo, the language picker, and the list of settings — each a working row to a
 *  screen that already exists. No hooks here, so every piece renders straight from its props and
 *  is worth testing on its own (tests/unit/profile.test.tsx), the same shape as `HomeParts.tsx`.
 *
 *  Whoever opens Profile sees her own name at the top — never whoever's papers happen to be open
 *  elsewhere in the app (docs/product-reset.md §6: one account, always plainly whose). Where a
 *  row is about someone else's papers, it says that person's name instead of "you" or "your"
 *  (the `*Other` twin of the same string, matching `whose` in `screens/family/common.tsx`), so a
 *  chief reading her own Profile is never told it is hers when it is his. */

/** The signed-in person: their photo or initial, and their name, as the board draws it — a plain
 *  row, nothing to tap. */
export function ProfileHeader({ s, name }: { s: Strings; name: string }): JSX.Element {
  return (
    <TintCard tint="paper" testId="profile-me">
      <ListRow lead={<Avatar name={name} size="large" />} title={name} line={fill(s.me.signedInAs, { name })} />
    </TintCard>
  );
}

/** The language picker (docs/design/nura-concept-board.html): his own three, said in each one's
 *  own name, one of them always chosen. Setting it is instant — no save, nothing to confirm. */
export function LanguageRow({
  s,
  code,
  names,
  onSet,
}: {
  s: Strings;
  code: Language;
  names: Record<Language, string>;
  onSet: (code: Language) => void;
}): JSX.Element {
  return (
    <>
      <SectionHeader title={s.me.language} />
      <TintCard tint="paper" testId="profile-language">
        <div class="row" role="group" aria-label={s.me.language}>
          {LANGUAGES.map((each) => (
            <Pill key={each} chosen={code === each} onClick={() => onSet(each)} testId={`lang-${each}`}>
              {names[each]}
            </Pill>
          ))}
        </div>
      </TintCard>
    </>
  );
}

export interface ProfileNavProps {
  s: Strings;
  /** Whose papers are open here — never null once signed in. */
  papers: ProfileOut;
  /** The signed-in person owns the papers now open (patient density, "your"); a chief reads
   *  his name instead, on every row below that is about them (the `*Other` twin). */
  owner: boolean;
  showEmergency: boolean;
  onOpenEmergency: () => void;
  onOpenKeys: () => void;
  onOpenConsents: () => void;
  onOpenOnlyMe: () => void;
  onSwitchProfile: () => void;
  /** Null where the feature does not apply (a key already claimed, or no papers to open). */
  onSetUp: (() => void) | null;
  onOpenPapers: (() => void) | null;
}

/** The rest of the board's list (docs/design/nura-concept-board.html, the Profile screen): the
 *  emergency card, "Change who can see what" (the family's keys), what he agreed to, what he
 *  keeps to himself, and the ways to look at or set up another set of papers. Every row opens a
 *  screen that already exists (`flow.ts`'s `family` and `emergency` places) — nothing here is
 *  drawn without something real behind it. */
export function ProfileNav(props: ProfileNavProps): JSX.Element {
  const { s, papers, owner, showEmergency, onOpenEmergency, onOpenKeys, onOpenConsents, onOpenOnlyMe, onSwitchProfile, onSetUp, onOpenPapers } = props;
  const name = papers.display_name;
  return (
    <TintCard tint="paper" testId="profile-list">
      {showEmergency && (
        <ListRow lead={<IconBadge icon="heart" tint="blush" />} title={s.today.emergencyTitle} onClick={onOpenEmergency} testId="me-emergency" />
      )}
      <ListRow lead={<IconBadge icon="lock" tint="lavender" />} title={s.family.keys} onClick={onOpenKeys} testId="profile-keys" />
      <ListRow
        lead={<IconBadge icon="privacy" tint="sage" />}
        title={owner ? s.family.consentsSelf : fill(s.family.consentsOther, { name })}
        onClick={onOpenConsents}
        testId="profile-consents"
      />
      <ListRow lead={<IconBadge icon="records" tint="sky" />} title={s.family.onlyMe} onClick={onOpenOnlyMe} testId="profile-only-me" />
      <ListRow lead={<IconBadge icon="family" tint="butter" />} title={s.me.switchProfile} onClick={onSwitchProfile} testId="switch-profile" />
      {onSetUp && <ListRow lead={<IconBadge icon="plan" tint="peach" />} title={s.me.setUp} onClick={onSetUp} testId="set-up" />}
      {onOpenPapers && <ListRow lead={<IconBadge icon="records" tint="cream" />} title={s.papers.open} onClick={onOpenPapers} testId="open-papers" />}
    </TintCard>
  );
}

/** The sign-out row, on its own card at the foot of the screen, as it was on Me. */
export function SignOutRow({ s, onSignOut }: { s: Strings; onSignOut: () => void }): JSX.Element {
  return (
    <TintCard tint="paper" testId="profile-sign-out">
      <ListRow lead={<IconBadge icon="close" tint="blush" />} title={s.me.signOut} onClick={onSignOut} testId="sign-out" />
    </TintCard>
  );
}

/** "What Nura uses" (RE-05, docs/recommendation-engine.md §3.6) reads as his own — "Your
 *  medicines" — when the papers open are his own; a chief reading someone else's reads his name
 *  instead, the `*FamiliesOther` twin of the same string (matching `whose` in
 *  `screens/family/common.tsx`, the same rule Family already keeps). */
export function signalLabel(s: Strings, owner: boolean, family: SignalFamily, patientName: string): string {
  return owner ? s.me.whatNuraUsesFamilies[family] : fill(s.me.whatNuraUsesFamiliesOther[family], { patient: patientName });
}

/** The lead line above the switches, with the same twin: "for you" on his own Profile, "for
 *  {name}" on a chief's read of someone else's. */
export function signalLead(s: Strings, owner: boolean, patientName: string): string {
  return owner ? s.me.whatNuraUsesLead : fill(s.me.whatNuraUsesLeadOther, { patient: patientName });
}
