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
 *  The names are the design system's (docs/design-system.md §3) for the surfaces that exist:
 *  Today, Medicines, Records, Visits, Family. Her Home is Today, her Timeline and her Plan are
 *  places inside Records and Visits, each one tap from the tab — so every feature is still at
 *  most two taps away. */
export type Tab = "today" | "medicines" | "records" | "visits" | "family";

/** Which scope each tab needs to be worth showing. Today is always there: it is where the app
 *  opens. Papers is not one scope but whatever places a key opens (`hubEntries`) — a helper
 *  with only the medicines still has his day and what changed to read. */
const NEEDS: Partial<Record<Tab, string>> = {
  medicines: "medicines",
  visits: "visits",
  family: "family",
};

export function tabsFor(density: Density, s: Strings, scopes: readonly string[] = [], owner = true): TabItem[] {
  const all: TabItem[] = [
    { id: "today", label: s.tabs.today, icon: "today" },
    { id: "medicines", label: s.tabs.medicines, icon: "medicines" },
    { id: "records", label: s.tabs.records, icon: "records" },
    { id: "visits", label: s.tabs.visits, icon: "visits" },
    { id: "family", label: s.tabs.family, icon: "family" },
  ];
  // The owner of the papers opens all of them; a key opens what it was cut for. A tab whose
  // surface a key does not open is left off, because tapping it would only reach the
  // backend's no — that is the key's scope, not a second kind of app.
  if (owner) return all;
  return all.filter((tab) => {
    // Today and Papers are always there. Papers is not gated on a scope because "what changed"
    // is readable under any key (`hubEntries`, PART null), so the tab always opens something;
    // which places are on it is the key's business, not the bar's.
    if (tab.id === "today" || tab.id === "records") return true;
    const needed = NEEDS[tab.id as Tab];
    return needed === undefined || scopes.includes(needed);
  });
}

/** Which tab a place in the Record (W5) is under, the same for everyone: the medicines, their
 *  story, adding one and "I have more at home." under Medicines; every other place in his
 *  papers under Records. Visits is the appointments surface, not a place in the Record, so
 *  opening his written history never lights a tab he did not tap. */
export function recordTab(at: RecordAt, _density: Density): Tab {
  const medicine = at.name === "medicines" || at.name === "story" || at.name === "add" || at.name === "more";
  return medicine ? "medicines" : "records";
}
