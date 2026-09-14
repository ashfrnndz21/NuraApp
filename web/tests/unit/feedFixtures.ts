import type { FeedItemOut, FeedPageOut } from "../../src/api/types";

/** Feed items shaped as the backend answers them (checkpoint 8's page, trimmed). */
export function item(type: string, supply: string, extra: Partial<FeedItemOut> = {}): FeedItemOut {
  const id = extra.item_id ?? `${type}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    item_id: id,
    type,
    supply,
    status: "generated",
    rendered_from_state: "state-1",
    language: "en",
    format: "text",
    headline: `${type} headline`,
    body: [`${type} line one.`, `${type} line two.`],
    voice: [`${type} line one.`, `${type} line two.`],
    why: { kind: type, plain: `This is why ${type} is here.` },
    priority: 10,
    caps_class: "supply",
    scope: "records",
    deliver_to: "patient",
    autoplay: false,
    source_id: null,
    cite: null,
    boundary: null,
    day: "2026-09-14",
    created_at: "2026-09-14T01:00:00+00:00",
    expires_at: "2026-09-14T16:00:00+00:00",
    ...extra,
  };
}

export const BOUNDARY = "Nura explains one thing in simple words.\nThis is not a doctor's advice.\nAsk your doctor.";

export function learning(extra: Partial<FeedItemOut> = {}): FeedItemOut {
  const body = ["Sit down and rest for 5 minutes first.", "This comes from HealthHub.", ...BOUNDARY.split("\n")];
  return item("learning", "learning", {
    headline: "Taking your blood pressure at home",
    body,
    voice: body,
    boundary: BOUNDARY,
    source_id: "source-1",
    cite: { url: "https://www.healthhub.sg/x", title: "Measuring your blood pressure at home" },
    why: { kind: "learning", plain: "This is about your blood pressure, which is on your papers." },
    ...extra,
  });
}

export function page(items: FeedItemOut[], cursor: string | null, next: string | null, extra: Partial<FeedPageOut> = {}): FeedPageOut {
  return { audience: "patient", items, cursor, next_cursor: next, quiet: false, held_by_caps: {}, ...extra };
}
