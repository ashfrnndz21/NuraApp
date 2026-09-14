import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { bindingOf, clearAllProfileData, isFresh, loadToday, midnightAfter, saveToday, shownUntil, zoneOf } from "../../src/offline/todayCache";
import { kvGet, kvKeys } from "../../src/store/kv";
import type { TodayModel } from "../../src/today/model";

/** The cache is bound to the key and good for today only; sign-out leaves nothing. Runs on
 *  the store's in-memory fallback (no IndexedDB in node), which has the same interface. */

const owner: ProfileOut = { profile_id: "p1", display_name: "Pa", language: "en", region: "SG", role: null, scopes: ["medicines", "notes"], standing: "owner", key_id: null };
const helper: ProfileOut = { ...owner, role: "helper", scopes: ["medicines"], standing: "holder", key_id: "k1" };
const narrowed: ProfileOut = { ...helper, scopes: ["profile"], key_id: "k1" };
const model: TodayModel = { stateId: "s1", posture: "stable", stale: false, computedAt: "2026-09-14T00:00:00Z", slots: [], lines: [], feed: [], proud: 3, chief: null, boundary: [], fetchedAt: "2026-09-14T01:00:00Z" };
const SG = zoneOf("SG");
// 20:00 in Singapore on Monday 14 September, whatever zone this machine is in.
const at = new Date("2026-09-14T12:00:00Z");

beforeEach(async () => {
  await clearAllProfileData();
});

describe("the binding", () => {
  it("is the owner, or the key, with the scope set", () => {
    expect(bindingOf(owner)).toEqual({ keyId: "owner", scopes: ["medicines", "notes"] });
    expect(bindingOf(helper)).toEqual({ keyId: "k1", scopes: ["medicines"] });
  });

  it("finds the page only under the binding that read it, and drops it otherwise", async () => {
    await saveToday("p1", model, bindingOf(helper), at, SG);
    expect((await loadToday("p1", bindingOf(helper), at))?.model.proud).toBe(3);
    expect(await loadToday("p1", bindingOf(narrowed), at)).toBeNull();
    expect(await kvGet("today.p1")).toBeUndefined();
    await saveToday("p1", model, bindingOf(helper), at, SG);
    expect(await loadToday("p1", bindingOf(owner), at)).toBeNull();
  });
});

describe("the expiry", () => {
  it("is the midnight after the fetch on the region's clock, not the phone's", () => {
    expect(midnightAfter(at, SG).toISOString()).toBe("2026-09-14T16:00:00.000Z");
    // 00:30 in Singapore is already the 15th there, though it is still the 14th in UTC.
    expect(midnightAfter(new Date("2026-09-14T16:30:00Z"), SG).toISOString()).toBe("2026-09-15T16:00:00.000Z");
    expect(midnightAfter(new Date("2026-09-14T15:59:59Z"), zoneOf("MY")).toISOString()).toBe("2026-09-14T16:00:00.000Z");
    expect(zoneOf("MY")).toBe("Asia/Kuala_Lumpur");
    expect(zoneOf(undefined)).toBe("Asia/Singapore");
  });

  it("shows a page read at 23:59 in Singapore until 00:00 there, and a kept page until its own expiry", () => {
    expect(shownUntil("2026-09-14T15:59:00Z", null, SG).toISOString()).toBe("2026-09-14T16:00:00.000Z");
    expect(shownUntil("2026-09-14T15:59:00Z", "2026-09-14T16:00:00.000Z", SG).toISOString()).toBe("2026-09-14T16:00:00.000Z");
    expect(shownUntil("2026-09-14T16:00:30Z", null, SG).toISOString()).toBe("2026-09-15T16:00:00.000Z");
  });

  it("drops the page once midnight has passed: the phone keeps nothing it may not show", async () => {
    const entry = await saveToday("p1", model, bindingOf(owner), at, SG);
    expect(isFresh(entry, new Date("2026-09-14T15:59:00Z"))).toBe(true);
    expect(isFresh(entry, new Date("2026-09-14T16:01:00Z"))).toBe(false);
    expect(await loadToday("p1", bindingOf(owner), new Date("2026-09-14T15:00:00Z"))).not.toBeNull();
    expect(await loadToday("p1", bindingOf(owner), new Date("2026-09-14T22:00:00Z"))).toBeNull();
    expect(await kvGet("today.p1")).toBeUndefined();
  });
});

describe("sign-out", () => {
  it("leaves no cached page of any profile", async () => {
    await saveToday("p1", model, bindingOf(owner), at, SG);
    await saveToday("p2", model, bindingOf(helper), at, SG);
    expect((await kvKeys("today.")).sort()).toEqual(["today.p1", "today.p2"]);
    await clearAllProfileData();
    expect(await kvKeys("today.")).toEqual([]);
  });
});
