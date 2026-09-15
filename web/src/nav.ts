import type { Density } from "./store/session";
import type { Strings } from "./strings";
import type { TabItem } from "./ui/kit";
import type { RecordAt } from "./record/places";

/** The tabs, per persona (docs/design-system.md §3, docs/ui-mockup-v2.html — where v1 and v2
 *  differ, v2 wins). His: Today · Medicines · Records · Visits, nothing deeper than two taps.
 *  Hers: Home · Timeline · Medicines · Plan · Family. "Me" is not a tab: it is the sheet the
 *  header's avatar opens, on every screen. */
export type Tab = "today" | "medicines" | "records" | "visits" | "timeline" | "plan" | "family";

export function tabsFor(density: Density, s: Strings): TabItem[] {
  if (density === "patient") {
    return [
      { id: "today", label: s.tabs.today, icon: "today" },
      { id: "medicines", label: s.tabs.medicines, icon: "medicines" },
      { id: "records", label: s.tabs.records, icon: "records" },
      { id: "visits", label: s.tabs.visits, icon: "visits" },
    ];
  }
  return [
    { id: "today", label: s.tabs.home, icon: "home" },
    { id: "timeline", label: s.tabs.timeline, icon: "timeline" },
    { id: "medicines", label: s.tabs.medicines, icon: "medicines" },
    { id: "plan", label: s.tabs.plan, icon: "plan" },
    { id: "family", label: s.tabs.family, icon: "family" },
  ];
}

/** Which tab a place in the Record (W5) is under. His: the medicines, their story and adding one
 *  under Medicines; everything else of his papers under Records. Hers: the medicines and his
 *  blood tests under Medicines, his day's routine under Plan, the rest under Timeline. */
export function recordTab(at: RecordAt, density: Density): Tab {
  const medicine = at.name === "medicines" || at.name === "story" || at.name === "add" || at.name === "more";
  if (density === "patient") return medicine ? "medicines" : "records";
  if (medicine || at.name === "trends") return "medicines";
  if (at.name === "routine" || at.name === "builder") return "plan";
  return "timeline";
}
