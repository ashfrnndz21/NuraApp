import type { JSX } from "preact";
import type { BodySystem } from "../api/types";
import { t } from "../strings";
import { PillButton } from "./kit";
import "./bodyMap.css";

/** The body-systems map (#175, docs/design-system.md §4): "A quiet outline figure with soft
 *  Plum glows on the systems an insight touches; doubles as a filter on Timeline and feed."
 *
 *  Minimal and local on purpose (per the owner's Eldora-style direction, docs/design-direction.md):
 *  the foundation another builder is landing will carry the tinted card and the
 *  icon-in-a-tinted-square this screen's surrounding tile should eventually use — this file
 *  owns only the outline figure and the glow, and the filter row below it, so there is nothing
 *  here to unpick when that lands. Swap the wrapping `<div class="body-map">` for the shared
 *  tinted card then; nothing about the figure or the filter logic needs to change.
 *
 *  `systems` is what the screen's own items actually touch — read off their episodes'
 *  `body_systems` (`app.memory.models.BodySystem`), never worked out here: the map glows only
 *  where a real tag says to. The figure is decorative (`aria-hidden`); the row of buttons under
 *  it is the one way to filter, in every density, with a screen reader, and at 200% text — an
 *  icon never carries meaning alone, and in the patient's own density the figure is read-only
 *  (the row still works, so it is never the only way to reach the filter). */

const SYSTEMS: readonly BodySystem[] = ["head", "heart", "lungs", "digestive", "kidneys", "joints", "skin", "general"];

/** Where each system's soft glow sits over the outline figure, in the figure's own 100×160
 *  viewBox: a circle's centre and radius. Approximate, not anatomical — enough to read as
 *  "roughly there" on a quiet outline, never a diagram a clinician would rely on. */
const GLOW_AT: Record<BodySystem, { cx: number; cy: number; r: number }> = {
  head: { cx: 50, cy: 18, r: 16 },
  heart: { cx: 43, cy: 56, r: 14 },
  lungs: { cx: 50, cy: 54, r: 22 },
  digestive: { cx: 50, cy: 78, r: 16 },
  kidneys: { cx: 50, cy: 82, r: 24 },
  joints: { cx: 50, cy: 60, r: 34 },
  skin: { cx: 50, cy: 90, r: 46 },
  general: { cx: 50, cy: 85, r: 58 },
};

export interface BodySystemsMapProps {
  /** The systems this screen's own items touch — from their episodes' real tags, oldest
   *  question first: never invented here. Only these ever glow, or appear as a filter. */
  systems: readonly BodySystem[];
  /** The system the reader has filtered to, or null for everything. */
  active: BodySystem | null;
  onSelect: (system: BodySystem | null) => void;
  /** Read-only (docs/design-system.md §5, Dad's density): the figure still shows what is
   *  touched, but tapping a chip does nothing. The map is never the only way to reach a
   *  screen's content, so a read-only map never hides anything — it is decoration only. */
  readOnly?: boolean;
  testId?: string;
}

/** The quiet outline figure: a head and a rounded shoulder-to-hip silhouette, 1.5px stroke,
 *  no fill — the same thin-line language as `ui/kit/icons.tsx`. Every glow this screen's items
 *  touch sits over it at 8–12% opacity; everything else stays unlit. */
function Figure({ touched }: { touched: ReadonlySet<BodySystem> }): JSX.Element {
  return (
    <svg class="body-map-figure" viewBox="0 0 100 160" aria-hidden="true" focusable="false">
      <defs>
        <filter id="body-map-blur" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
      </defs>
      {SYSTEMS.filter((system) => touched.has(system)).map((system) => {
        const at = GLOW_AT[system];
        return (
          <circle
            key={system}
            class="body-map-glow"
            data-system={system}
            cx={at.cx}
            cy={at.cy}
            r={at.r}
            filter="url(#body-map-blur)"
          />
        );
      })}
      <circle class="body-map-outline" cx="50" cy="18" r="14" />
      <path class="body-map-outline" d="M28 46c0-14 10-22 22-22s22 8 22 22v8c0 6-4 10-8 12l4 60c0 6-6 10-14 10h-8c-8 0-14-4-14-10l4-60c-4-2-8-6-8-12z" />
    </svg>
  );
}

export function BodySystemsMap({ systems, active, onSelect, readOnly, testId }: BodySystemsMapProps): JSX.Element | null {
  const s = t();
  const touched = new Set(systems);
  if (touched.size === 0) return null;
  const shown = SYSTEMS.filter((system) => touched.has(system));
  return (
    <section class="body-map" data-testid={testId ?? "body-map"}>
      <Figure touched={touched} />
      <div class="body-map-filters" role="group" aria-label={s.record.bodyMapShowEverything}>
        {shown.map((system) => (
          <PillButton
            key={system}
            variant="secondary"
            compact
            pressed={active === system}
            disabled={readOnly}
            onClick={() => onSelect(active === system ? null : system)}
            testId={`body-map-${system}`}
          >
            {s.record.bodyMapSystems[system]}
          </PillButton>
        ))}
        {active && !readOnly && (
          <PillButton variant="quiet" compact onClick={() => onSelect(null)} testId="body-map-clear">
            {s.record.bodyMapShowEverything}
          </PillButton>
        )}
      </div>
      {active && (
        <p class="caption" role="status" data-testid="body-map-showing">
          {s.record.bodyMapShowing[active]}
        </p>
      )}
    </section>
  );
}
