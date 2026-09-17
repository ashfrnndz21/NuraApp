import type { JSX } from "preact";

/** Thin-line icons (docs/design-system.md §2, Iconography): a 1.5px stroke that stays 1.5px at
 *  any size (`vector-effect: non-scaling-stroke`), 24px, 28px in the patient's density. An icon
 *  never carries meaning alone: every place that draws one puts a word beside it, and the icon
 *  itself is hidden from the screen reader. */

export type IconName =
  | "today"
  | "home"
  | "medicines"
  | "pill"
  | "records"
  | "visits"
  | "timeline"
  | "plan"
  | "family"
  | "speaker"
  | "mic"
  | "search"
  | "camera"
  | "close"
  | "play"
  | "chevron"
  | "back"
  | "note"
  | "check";

export const ICONS: Record<IconName, readonly string[]> = {
  today: [
    "M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8z",
    "M12 2.5v2",
    "M12 19.5v2",
    "M2.5 12h2",
    "M19.5 12h2",
    "M5.3 5.3l1.4 1.4",
    "M17.3 17.3l1.4 1.4",
    "M5.3 18.7l1.4-1.4",
    "M17.3 6.7l1.4-1.4",
  ],
  home: ["M3.5 11L12 4l8.5 7", "M5.5 9.5V20h13V9.5", "M10 20v-5.5h4V20"],
  medicines: ["M4.6 12.4l7.8-7.8a4 4 0 0 1 5.66 5.66l-7.8 7.8a4 4 0 0 1-5.66-5.66z", "M8.5 8.5l7 7"],
  pill: ["M3.5 12a4.5 4.5 0 0 1 4.5-4.5h8a4.5 4.5 0 0 1 0 9H8A4.5 4.5 0 0 1 3.5 12z", "M12 7.5v9"],
  records: ["M6.5 3h7.5l4 4v14h-11.5z", "M14 3v4h4", "M9.5 12h5.5", "M9.5 16h5.5"],
  visits: ["M4 6h16v14H4z", "M4 10.5h16", "M8.5 3.5v4", "M15.5 3.5v4", "M12 13.5v4", "M10 15.5h4"],
  timeline: ["M4 7h2", "M4 12h2", "M4 17h2", "M9.5 7h10.5", "M9.5 12h10.5", "M9.5 17h7"],
  plan: ["M10 6.5h10", "M10 12h10", "M10 17.5h10", "M4 6.5l1.5 1.5 2.5-3", "M4 12l1.5 1.5 2.5-3", "M4 17.5l1.5 1.5 2.5-3"],
  family: [
    "M9 11a3.5 3.5 0 1 0 0-7a3.5 3.5 0 1 0 0 7z",
    "M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5",
    "M16 4.3a3.5 3.5 0 0 1 0 6.4",
    "M18 14.8c1.8.7 3 2.4 3.5 5.2",
  ],
  speaker: ["M4 10v4h3l4 4V6l-4 4H4z", "M15 9a4 4 0 0 1 0 6", "M17.5 6.5a8 8 0 0 1 0 11"],
  mic: ["M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z", "M5.5 11.5a6.5 6.5 0 0 0 13 0", "M12 18v3"],
  search: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "M20 20l-4-4"],
  camera: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 10a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z"],
  close: ["M6.5 6.5l11 11", "M17.5 6.5l-11 11"],
  play: ["M8.5 5.5v13l10-6.5z"],
  chevron: ["M9.5 6l6 6-6 6"],
  back: ["M14.5 6l-6 6 6 6"],
  note: ["M4 5h16v11H9.5L4 20z"],
  check: ["M5 12.5l4.5 4.5L19 7.5"],
};

export function Icon({ name }: { name: IconName }): JSX.Element {
  return (
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" data-icon={name}>
      {ICONS[name].map((d, at) => (
        <path key={at} d={d} />
      ))}
    </svg>
  );
}
