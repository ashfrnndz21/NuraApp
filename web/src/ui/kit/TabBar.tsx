import type { JSX } from "preact";
import { Icon, type IconName } from "./icons";

export interface TabItem {
  id: string;
  label: string;
  icon: IconName;
}

/** The tab bar (docs/design-system.md §3): glass, one row, an icon above each word, no badges.
 *  It sits in the page's own flow under the scrolling content (the shell reserves its space),
 *  so it never covers a line. The current tab is Plum and says so to the screen reader. */
export function TabBar({ tabs, current, onSelect, label }: { tabs: readonly TabItem[]; current: string | null; onSelect: (id: string) => void; label: string }): JSX.Element {
  return (
    <nav class="tabbar" aria-label={label} data-count={tabs.length}>
      {tabs.map((tab) => (
        <button key={tab.id} type="button" aria-current={current === tab.id ? "page" : undefined} onClick={() => onSelect(tab.id)} data-testid={`tab-${tab.id}`}>
          <Icon name={tab.icon} />
          <span class="tab-word">{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
