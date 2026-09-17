import type { Density } from "./store/session";
import type { Strings } from "./strings";
import type { TabItem } from "./ui/kit";
import type { RecordAt } from "./record/places";

/** One app, one account, one tab set (docs/product-reset.md §1 and §6). There is no "his app"
 *  and "her app": the tabs are the same list for everyone, and what changes with the density is
 *  the type scale, the target sizes, one thing per screen and how much is shown — density and
 *  language are settings on the profile, not a different product.
 *
 *  What does change the list is the key: a tab whose surface a key does not open is not shown,
 *  because tapping it would only reach the backend's no. That is scope, not persona.
 *
 *  The five tabs are the owner's reference's (docs/design-direction.md, "The bottom
 *  navigation"), each holding Nura's content:
 *  - Home: Today — the greeting, the check-in, "What would you like to do?", Upcoming.
 *  - Health: his medicines and doses, readings, papers and reports (the Record).
 *  - Connect: family and friends, the family thread, messages (Family).
 *  - Services: his visits and doctors, and getting ready for the next one.
 *  - Profile: him, his settings, language, text size, privacy (what the Me sheet holds). */
export type Tab = "home" | "health" | "connect" | "services" | "profile";

/** Which scope each tab needs to be worth showing. Home and Profile are always there: Home is
 *  where the app opens, Profile is the person's own settings. Health is not one scope but
 *  whatever places a key opens (`hubEntries`) — a helper with only the medicines still has his
 *  day and what changed to read — so it is always there too. */
const NEEDS: Partial<Record<Tab, string>> = {
  connect: "family",
  services: "visits",
};

export function tabsFor(density: Density, s: Strings, scopes: readonly string[] = [], owner = true): TabItem[] {
  const all: TabItem[] = [
    { id: "home", label: s.tabs.home, icon: "home" },
    { id: "health", label: s.tabs.health, icon: "health" },
    { id: "connect", label: s.tabs.connect, icon: "connect" },
    { id: "services", label: s.tabs.services, icon: "services" },
    { id: "profile", label: s.tabs.profile, icon: "profile" },
  ];
  // The owner of the papers opens all of them; a key opens what it was cut for. A tab whose
  // surface a key does not open is left off, because tapping it would only reach the
  // backend's no — that is the key's scope, not a second kind of app.
  if (owner) return all;
  return all.filter((tab) => {
    const needed = NEEDS[tab.id as Tab];
    return needed === undefined || scopes.includes(needed);
  });
}

/** Which tab a place in the Record (W5) is under: every place in his papers — his medicines
 *  and their story included — is Health, the same for everyone. Visits is the Services tab,
 *  not a place in the Record, so opening his written history never lights a tab he did not tap. */
export function recordTab(_at: RecordAt, _density: Density): Tab {
  return "health";
}
