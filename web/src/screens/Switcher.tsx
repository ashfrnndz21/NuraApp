import { useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ProfileOut } from "../api/types";
import { openProfile } from "../flow";
import { known, looking, refreshKnown } from "../store/profiles";
import { profile } from "../store/session";
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
 *  without signing out and back in. */
export function ProfileSwitcher(): JSX.Element | null {
  const s = t();
  const papers = profile.value;
  const [open, setOpen] = useState(false);
  if (!papers) return null;
  const own = papers.standing === "owner";
  const list = known.value ?? [];
  const others = list.filter((each) => each.profile_id !== papers.profile_id);
  return (
    <>
      <button
        type="button"
        class="switcher"
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
          {own ? s.switcher.own : papers.display_name}
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
        {others.length === 0 && !looking.value && (
          <PaperTile testId="switcher-only">
            <p>{s.switcher.onlyThese}</p>
          </PaperTile>
        )}
      </Sheet>
    </>
  );
}
