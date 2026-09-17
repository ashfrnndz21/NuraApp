import type { ComponentChildren, JSX } from "preact";
import type { ProfileOut } from "../api/types";
import { batch } from "../capture/session";
import { go, openTab, type SoonPlace } from "../flow";
import { t } from "../strings";
import { CheckInFace } from "../ui/illustrations";
import { FeatureTile, Icon, IconBadge, PillButton, SectionHeader, SkeletonCard, TintCard, type IconName, type Tint } from "../ui/kit";

/** Home's warm parts (docs/design-direction.md, Reference B's Home): the daily check-in, "What
 *  would you like to do?", adding a health report, and what is coming up. Both densities draw the
 *  same parts; the density moves only their type and their targets. Every one of them opens
 *  something real, or says plainly that it is not built yet. */

/** Whether a key opens a scope: the owner opens everything; a key, what it was cut for. */
function opens(papers: ProfileOut | null, scope: string): boolean {
  return papers !== null && (papers.standing === "owner" || papers.scopes.includes(scope));
}

/** The daily check-in, as the board draws it: "Daily check-in", one line, Check in, and the round
 *  friendly face. Check in opens the existing way to say how he feels (E14-01) — said or typed,
 *  a red flag in it escalating on the backend exactly as the button does. */
export function CheckInCard({ papers }: { papers: ProfileOut | null }): JSX.Element | null {
  const s = t();
  if (!opens(papers, "records")) return null;
  return (
    <TintCard tint="peach" testId="daily-check-in" extra="check-in">
      <div class="check-in-text">
        <h2 class="card-title">{s.hub.checkTitle}</h2>
        <p class="card-line">{s.hub.checkLine}</p>
        <PillButton variant="primary" compact onClick={() => go({ name: "symptoms" })} testId="open-symptoms">
          {s.hub.checkIn}
        </PillButton>
      </div>
      <CheckInFace class="check-in-face" />
    </TintCard>
  );
}

interface Place {
  id: string;
  icon: IconName;
  tint: Tint;
  label: string;
  line: string;
  open: () => void;
}

/** "What would you like to do?": six places, each its own tint. A place this key does not open
 *  is not offered (tapping it would only reach the backend's no); a place Nura has not built
 *  yet opens a screen that says so, never a dead tap. */
export function DoGrid({ papers }: { papers: ProfileOut | null }): JSX.Element {
  const s = t();
  const h = s.hub;
  const soon = (place: SoonPlace) => () => go({ name: "soon", place });
  const places: (Place | false)[] = [
    { id: "health", icon: "track", tint: "blush", label: h.health, line: h.healthLine, open: () => openTab("health") },
    opens(papers, "medicines") && { id: "medicines", icon: "medication", tint: "sky", label: h.medicines, line: h.medicinesLine, open: () => go({ name: "record", at: { name: "medicines" } }) },
    opens(papers, "family") && { id: "connect", icon: "connect", tint: "sage", label: h.connect, line: h.connectLine, open: () => openTab("connect") },
    { id: "activities", icon: "activities", tint: "lavender", label: h.activities, line: h.activitiesLine, open: soon("activities") },
    { id: "care", icon: "care", tint: "peach", label: h.care, line: h.careLine, open: soon("care") },
    { id: "resources", icon: "resources", tint: "butter", label: h.resources, line: h.resourcesLine, open: soon("resources") },
  ];
  return (
    <section class="do-section" aria-labelledby="do-title">
      <h2 class="section-title" id="do-title">
        {h.doTitle}
      </h2>
      <div class="do-grid" data-testid="do-grid">
        {places.filter((place): place is Place => place !== false).map((place) => (
          <FeatureTile key={place.id} icon={place.icon} tint={place.tint} label={place.label} caption={place.line} onClick={place.open} testId={`do-${place.id}`} />
        ))}
      </div>
    </section>
  );
}

/** "Add a health report": a PDF, or a photo of a paper. The phone's own chooser opens — files,
 *  photos, and on a phone the camera too (no `capture`, so it offers all three). Choosing the
 *  file only picks it: it goes through the one upload path there is (E18-01's batch,
 *  `capture/batch.ts`), but not before its own confirm card on the Papers screen names the
 *  file and asks his own "Send it" (reviewer #237 item 6) — then opens on the review card every
 *  paper has. A key that cannot add to his papers is not offered it. */
export function AddReport({ papers }: { papers: ProfileOut | null }): JSX.Element | null {
  const s = t();
  if (!papers || !(papers.standing === "owner" || papers.scopes.includes("records"))) return null;
  const chosen = (event: Event) => {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    batch.forget();
    batch.pick([file]);
    go({ name: "papers", report: true });
  };
  return (
    <label class="action-row report" data-testid="add-report">
      <IconBadge icon="upload" tint="lavender" />
      <span class="action-text">
        <span class="action-title">{s.hub.report}</span>
        <span class="action-line">{s.hub.reportLine}</span>
        {/* Choosing the file only picks it (`chosen`, above): the Papers screen shows its name
            and his own "Send it" before it goes (reviewer #237 item 6). */}
        <span class="action-line">{s.hub.reportNote}</span>
      </span>
      <span class="action-go" aria-hidden="true">
        <Icon name="chevron" />
      </span>
      <input type="file" accept="application/pdf,image/*" onChange={chosen} data-testid="report-input" />
    </label>
  );
}

/** "Coming up", with See all when this key opens his visits, over the card the screen gives. */
export function Upcoming({ papers, children }: { papers: ProfileOut | null; children: ComponentChildren }): JSX.Element {
  const s = t();
  return (
    <section class="upcoming" data-testid="upcoming">
      <SectionHeader
        title={s.hub.upcoming}
        action={opens(papers, "visits") ? { word: s.hub.seeAll, label: s.hub.seeAllVisits, onClick: () => openTab("services"), testId: "upcoming-all" } : undefined}
      />
      {children}
    </section>
  );
}

/** Home while its page is on its way: the shapes of what is coming — a card, the grid, a card —
 *  softly shimmering, never a spinner on a blank page. The screen reader hears the one line. */
export function HomeSkeleton(): JSX.Element {
  const s = t();
  return (
    <div class="home-skeleton" role="status" data-testid="home-skeleton">
      <span class="sr-only">{s.talk.loading}</span>
      <SkeletonCard lines={2} />
      <div class="skeleton-grid">
        {[0, 1, 2, 3, 4, 5].map((at) => (
          <SkeletonCard key={at} shape="tile" lines={1} />
        ))}
      </div>
      <SkeletonCard lines={3} />
    </div>
  );
}
