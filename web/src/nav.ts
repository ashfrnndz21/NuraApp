import type { Density } from "./store/session";
import type { Strings } from "./strings";
import type { TabItem } from "./ui/kit";

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
