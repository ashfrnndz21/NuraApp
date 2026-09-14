import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { bindingOf, clearAllProfileData, isFresh, loadToday, localMidnightAfter, saveToday } from "../../src/offline/todayCache";
import { kvGet, kvKeys } from "../../src/store/kv";
import type { TodayModel } from "../../src/today/model";

/** The cache is bound to the key and good for today only; sign-out leaves nothing. Runs on
 *  the store's in-memory fallback (no IndexedDB in node), which has the same interface. */

const owner: ProfileOut = { profile_id: "p1", display_name: "Pa", language: "en", region: "SG", role: null, scopes: ["medicines", "notes"], standing: "owner", key_id: null };
const helper: ProfileOut = { ...owner, role: "helper", scopes: ["medicines"], standing: "holder", key_id: "k1" };
const narrowed: ProfileOut = { ...helper, scopes: ["profile"], key_id: "k1" };
const model: TodayModel = { stateId: "s1", posture: "stable", stale: false, computedAt: "2026-09-14T00:00:00Z", slots: [], lines: [], feed: [], proud: 3, chief: null, boundary: [], fetchedAt: "2026-09-14T01:00:00Z" };
const at = new Date(2026, 8, 14, 20, 0);

beforeEach(async () => {
  await clearAllProfileData();
});

describe("the binding", () => {
  it("is the owner, or the key, with the scope set", () => {
    expect(bindingOf(owner)).toEqual({ keyId: "owner", scopes: ["medicines", "notes"] });
    expect(bindingOf(helper)).toEqual({ keyId: "k1", scopes: ["medicines"] });
  });

  it("finds the page only under the binding that read it, and drops it otherwise", async () => {
    await saveToday("p1", model, bindingOf(helper), at);
    expect((await loadToday("p1", bindingOf(helper), at))?.model.proud).toBe(3);
    expect(await loadToday("p1", bindingOf(narrowed), at)).toBeNull();
    expect(await kvGet("today.p1")).toBeUndefined();
    await saveToday("p1", model, bindingOf(helper), at);
    expect(await loadToday("p1", bindingOf(owner), at)).toBeNull();
  });
});

describe("the expiry", () => {
  it("is the local midnight after the fetch", () => {
    expect(localMidnightAfter(at)).toEqual(new Date(2026, 8, 15, 0, 0, 0, 0));
    expect(localMidnightAfter(new Date(2026, 8, 14, 0, 0))).toEqual(new Date(2026, 8, 15, 0, 0, 0, 0));
  });

  it("drops the page once midnight has passed: the phone keeps nothing it may not show", async () => {
    const entry = await saveToday("p1", model, bindingOf(owner), at);
    expect(isFresh(entry, new Date(2026, 8, 14, 23, 59))).toBe(true);
    expect(isFresh(entry, new Date(2026, 8, 15, 0, 1))).toBe(false);
    expect(await loadToday("p1", bindingOf(owner), new Date(2026, 8, 14, 23, 0))).not.toBeNull();
    expect(await loadToday("p1", bindingOf(owner), new Date(2026, 8, 15, 6, 0))).toBeNull();
    expect(await kvGet("today.p1")).toBeUndefined();
  });
});

describe("sign-out", () => {
  it("leaves no cached page of any profile", async () => {
    await saveToday("p1", model, bindingOf(owner), at);
    await saveToday("p2", model, bindingOf(helper), at);
    expect((await kvKeys("today.")).sort()).toEqual(["today.p1", "today.p2"]);
    await clearAllProfileData();
    expect(await kvKeys("today.")).toEqual([]);
  });
});
