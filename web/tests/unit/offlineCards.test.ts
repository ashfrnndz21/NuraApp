import { describe, expect, it } from "vitest";
import type { OfflineCardsOut } from "../../src/api/types";
import { keepCards, keptCards } from "../../src/day/offline";
import { clearAllProfileData, clearProfileData } from "../../src/offline/todayCache";
import { kvGet, kvSet } from "../../src/store/kv";

/** The not-feeling-well cards for no network (ADR 0012) under the phone's rules for anything it
 *  keeps (E00-08): bound to the key that read them, good until the midnight after the read on
 *  the region's clock, and gone with the rest on a refusal, a switch of papers and sign-out. */

const OWNER = { keyId: "owner", scopes: ["emergency", "medicines", "records"] };
const SG = "Asia/Singapore";
const TEN_AM = new Date("2026-09-14T02:00:00Z"); // 10:00 in Singapore
const CARDS: OfflineCardsOut = {
  language: "en",
  emergency_number: "995",
  red_flag: [{ id: "nfw.offline_red", text: "Call the ambulance now on 995." }],
  unknown: [{ id: "nfw.offline_unknown", text: "Call your family now." }],
} as OfflineCardsOut;

describe("the kept not-feeling-well cards", () => {
  it("are there with no network the same day, under the key that read them", async () => {
    await keepCards("c1", CARDS, OWNER, TEN_AM, SG);
    expect((await keptCards("c1", OWNER, new Date("2026-09-14T15:59:00Z")))?.cards).toEqual(CARDS);
    expect(await keptCards("c1", { keyId: "k-mei", scopes: ["emergency"] }, TEN_AM)).toBeNull();
    expect(await keptCards("c1", OWNER, TEN_AM)).toBeNull(); // the other key's look deleted them
  });

  it("are gone past the region's midnight, like the Today page: the catalogue's words stand in", async () => {
    await keepCards("c2", CARDS, OWNER, TEN_AM, SG);
    expect(await keptCards("c2", OWNER, new Date("2026-09-14T16:00:01Z"))).toBeNull();
    expect(await kvGet("nfw.c2")).toBeUndefined();
  });

  it("kept before they had a midnight, are read again rather than trusted", async () => {
    await kvSet("nfw.c3", { cards: CARDS, binding: OWNER, fetchedAt: TEN_AM.toISOString() });
    expect(await keptCards("c3", OWNER, TEN_AM)).toBeNull();
  });

  it("go with the rest of the phone's copy on a refusal, a switch of papers and sign-out", async () => {
    await keepCards("c4", CARDS, OWNER, TEN_AM, SG);
    await keepCards("c5", CARDS, OWNER, TEN_AM, SG);
    await clearProfileData("c4");
    expect(await keptCards("c4", OWNER, TEN_AM)).toBeNull();
    expect(await keptCards("c5", OWNER, TEN_AM)).not.toBeNull();
    await clearAllProfileData();
    expect(await keptCards("c5", OWNER, TEN_AM)).toBeNull();
  });
});
