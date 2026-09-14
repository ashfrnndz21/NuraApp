import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { dropStaleFeed, loadFeed, saveFeed } from "../../src/offline/feedCache";
import { bindingOf, clearAllProfileData, clearProfileData, saveToday, zoneOf } from "../../src/offline/todayCache";
import { kvKeys } from "../../src/store/kv";
import type { TodayModel } from "../../src/today/model";
import { item, page } from "./feedFixtures";

const owner: ProfileOut = { profile_id: "p1", display_name: "Pa", language: "en", region: "SG", role: null, scopes: ["medicines", "records"], standing: "owner", key_id: null };
const narrowed: ProfileOut = { ...owner, role: "caregiver", scopes: ["medicines"], standing: "holder", key_id: "k1" };
const SG = zoneOf("SG");
const at = new Date("2026-09-14T02:00:00Z"); // 10:00 in Singapore
const first = page([item("now", "now"), item("reading", "today")], null, "c1");
const model = { stateId: "s1", posture: "stable", stale: false, computedAt: null, slots: [], lines: [], feed: [], proud: 0, chief: null, boundary: [], fetchedAt: at.toISOString() } satisfies TodayModel;

beforeEach(async () => {
  await clearAllProfileData();
});

describe("the kept feed page", () => {
  it("is found only under the key and scope set that read it", async () => {
    await saveFeed("p1", first, bindingOf(owner), at, SG);
    expect((await loadFeed("p1", bindingOf(owner), at))?.page.items).toHaveLength(2);
    expect(await loadFeed("p1", bindingOf(narrowed), at)).toBeNull();
    // ...and a page found under the wrong binding is deleted, not kept for later.
    expect(await loadFeed("p1", bindingOf(owner), at)).toBeNull();
  });

  it("is good until the midnight after it was read on the region's clock, then deleted", async () => {
    const kept = await saveFeed("p1", first, bindingOf(owner), at, SG);
    expect(kept.expiresAt).toBe("2026-09-14T16:00:00.000Z");
    expect(await loadFeed("p1", bindingOf(owner), new Date("2026-09-14T15:59:00Z"))).not.toBeNull();
    expect(await loadFeed("p1", bindingOf(owner), new Date("2026-09-14T16:00:00Z"))).toBeNull();
    expect(await kvKeys("feed.")).toEqual([]);
  });

  it("is swept on launch once past its midnight, even if the pager is never opened", async () => {
    await saveFeed("p1", first, bindingOf(owner), at, SG);
    await dropStaleFeed("p1", bindingOf(owner), at);
    expect(await kvKeys("feed.")).toEqual(["feed.p1"]);
    await dropStaleFeed("p1", bindingOf(owner), new Date("2026-09-15T00:00:00Z"));
    expect(await kvKeys("feed.")).toEqual([]);
  });

  it("goes with Today's page on a refusal or a switch, and with everything on sign-out", async () => {
    await saveFeed("p1", first, bindingOf(owner), at, SG);
    await saveToday("p1", model, bindingOf(owner), at, SG);
    await saveFeed("p2", first, bindingOf(owner), at, SG);
    await clearProfileData("p1");
    expect(await kvKeys("feed.")).toEqual(["feed.p2"]);
    expect(await kvKeys("today.")).toEqual([]);
    await clearAllProfileData();
    expect(await kvKeys("feed.")).toEqual([]);
  });
});
