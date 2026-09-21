import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ProfileOut } from "../api/types";
import { openProfile } from "../flow";
import { known, looking, refreshKnown, unreached } from "../store/profiles";
import { profile, token } from "../store/session";
import { fill, t } from "../strings";
import { Avatar, Icon, PaperTile, Sheet } from "../ui/kit";

/** Which words say what this key is: the same lines the doors use, so the two places that
 *  name a set of papers name it the same way. */
export function roleLine(each: ProfileOut): string {
  const s = t();
  if (each.standing === "owner") return s.switcher.roleOwner;
  if (each.standing === "steward") return s.switcher.roleSteward;
  if (each.role === "chief") return s.switcher.roleChief;
  if (each.role === "caregiver" || each.role === "helper") return s.switcher.roleCaregiver;
  return s.switcher.roleOther;
}

/** The switcher (product-reset.md §6): whose papers are open, on every screen, and the way to
 *  every other set this person can open. One app and one account — the tabs do not change with
 *  who is on screen; what changes is whose record the app is in, and this says which, by name,
 *  so someone acting on his record is never in doubt about whose it is.
 *
 *  Opening the sheet reads the doors again, so a key granted a moment ago is in the list
 *  without signing out and back in.
 *
 *  `compact` (cp3-home's merged header): the same button, sized to sit beside the greeting in
 *  one header row rather than its own — the avatar, the name and the chevron are all still
 *  there and still say `whose-name` (existing safety checks watch that name never paints ahead
 *  of a session's own refusal, e.g. `today.spec.ts`'s "a refused session on reopening"; a
 *  control that sometimes has no name-bearing element at all would leave that watch nothing to
 *  watch), just in the smaller type the header row's own line-height gives them. */
export function ProfileSwitcher({ compact }: { compact?: boolean } = {}): JSX.Element | null {
  const s = t();
  const papers = profile.value;
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (compact && known.value === null && token.value) void refreshKnown().catch(() => undefined);
  }, [compact, token.value]);
  if (!papers) return null;
  const own = papers.standing === "owner";
  const list = known.value ?? [];
  const others = list.filter((each) => each.profile_id !== papers.profile_id);
  return (
    <>
      <button
        type="button"
        class={["switcher", compact && "switcher-compact"].filter(Boolean).join(" ")}
        aria-haspopup="dialog"
        aria-label={own ? s.switcher.openOwn : fill(s.switcher.openOther, { name: papers.display_name })}
        onClick={() => {
          setOpen(true);
          void refreshKnown().catch(() => undefined);
        }}
        data-testid="whose"
      >
        <Avatar name={papers.display_name} soft />
        <span class="whose-name" data-testid="whose-name">
          {papers.display_name}
        </span>
        <Icon name="chevron" />
      </button>
      <Sheet title={s.switcher.title} open={open} onClose={() => setOpen(false)} closeLabel={s.shell.close} testId="switcher-sheet">
        <PaperTile testId="switcher-here">
          <p class="source-line">{roleLine(papers)}</p>
        </PaperTile>
        {others.length > 0 && (
          <nav class="place-rows" aria-label={s.switcher.title}>
            {others.map((each) => (
              <button
                key={each.profile_id}
                type="button"
                class="place-row"
                onClick={() => {
                  setOpen(false);
                  void openProfile(each);
                }}
                data-testid={`switch-to-${each.standing === "owner" ? "own" : "key"}`}
              >
                <Avatar name={each.display_name} soft />
                <span class="place-word">
                  {each.standing === "owner" ? s.switcher.own : each.display_name}
                  <span class="source-line">{roleLine(each)}</span>
                </span>
                <Icon name="chevron" />
              </button>
            ))}
          </nav>
        )}
        {unreached.value && (
          <PaperTile role="status" testId="switcher-unreached">
            <p>{s.switcher.cannotLook}</p>
          </PaperTile>
        )}
        {others.length === 0 && !looking.value && !unreached.value && (
          <PaperTile testId="switcher-only">
            <p>{s.switcher.onlyThese}</p>
          </PaperTile>
        )}
      </Sheet>
    </>
  );
}
