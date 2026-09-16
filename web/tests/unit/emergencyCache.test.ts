import { describe, expect, it } from "vitest";
import type { EmergencyCardOut } from "../../src/api/types";
import { emergencyOnly, loadCard, saveCard as keep, wantsRead } from "../../src/offline/emergencyCache";
import { clearAllProfileData, clearProfileData } from "../../src/offline/todayCache";

/** The emergency card on the phone (E00-08): bound to the key that read it, opened with no
 *  network, kept past midnight (it is not today's doses), read again once a day. */

const OWNER = { keyId: "owner", scopes: ["emergency", "medicines", "records"] };
const SG = "Asia/Singapore";
const TEN_AM = new Date("2026-09-14T02:00:00Z");

function card(language = "en"): EmergencyCardOut {
  return {
    card_id: "c1",
    profile_id: "p1",
    state_id: "s1",
    rendered_at: TEN_AM.toISOString(),
    name: "Pa",
    language,
    spoken_language: language,
    age_band: "70-79",
    conditions: [],
    medicines: [],
    allergies: [],
    blood_type: null,
    high_risk: [],
    contacts: [],
    clinic: null,
    last_reading_at: null,
    emergency_number: "995",
    lines: [{ id: "ec.title", text: "This is Pa's emergency card." }],
  };
}

const saveCard = (profileId: string, read: EmergencyCardOut, binding: typeof OWNER, now: Date) => keep(profileId, { card: read, html: "<p>printable</p>" }, binding, now);

describe("a key to the emergency card alone", () => {
  it("is a neighbour's: the card and the face of the papers, nothing more — never the owner", () => {
    expect(emergencyOnly({ standing: "holder", scopes: ["emergency", "profile"] })).toBe(true);
    expect(emergencyOnly({ standing: "holder", scopes: ["emergency"] })).toBe(true);
    expect(emergencyOnly({ standing: "holder", scopes: ["emergency", "medicines"] })).toBe(false);
    expect(emergencyOnly({ standing: "holder", scopes: ["medicines"] })).toBe(false);
    expect(emergencyOnly({ standing: "owner", scopes: [] })).toBe(false);
  });
});

describe("the kept emergency card", () => {
  it("keeps the backend's printable page with the lines, so it prints with no network", async () => {
    await keep("e0", { card: card(), html: "<p>printable</p>" }, OWNER, TEN_AM);
    expect((await loadCard("e0", OWNER))?.html).toBe("<p>printable</p>");
  });

  it("opens under the key that read it, and a card kept under another key is deleted", async () => {
    await saveCard("e1", card(), OWNER, TEN_AM);
    expect((await loadCard("e1", OWNER))?.card.lines[0]?.text).toBe("This is Pa's emergency card.");
    expect(await loadCard("e1", { keyId: "k-mei", scopes: ["emergency"] })).toBeNull();
    expect(await loadCard("e1", OWNER)).toBeNull();
  });

  it("is still there past midnight — a fall at night is when it is needed — and is read again once a day", async () => {
    const kept = await saveCard("e2", card(), OWNER, TEN_AM);
    const laterToday = new Date("2026-09-14T15:59:00Z");
    const nextMorning = new Date("2026-09-14T16:00:01Z");
    expect(await loadCard("e2", OWNER)).not.toBeNull();
    expect(wantsRead(kept, "en", laterToday, SG)).toBe(false);
    expect(wantsRead(kept, "en", nextMorning, SG)).toBe(true);
    expect(wantsRead(kept, "ms", laterToday, SG)).toBe(true);
    expect(wantsRead(null, "en", laterToday, SG)).toBe(true);
  });

  it("keeps the printable page it already has when a read's own fetch of it fails — a hiccup on one request must not cost him the Print button", async () => {
    const kept = await saveCard("e5", card(), OWNER, TEN_AM);
    expect(kept.html).toBe("<p>printable</p>");
    const laterToday = new Date("2026-09-14T15:00:00Z");
    const missed = await keep("e5", { card: card(), html: null }, OWNER, laterToday, kept);
    expect(missed.html).toBe("<p>printable</p>");
    expect((await loadCard("e5", OWNER))?.html).toBe("<p>printable</p>");
  });

  it("still replaces the printable page with a fresh, successful read of it", async () => {
    const kept = await saveCard("e6", card(), OWNER, TEN_AM);
    const laterToday = new Date("2026-09-14T15:00:00Z");
    const reread = await keep("e6", { card: card(), html: "<p>newer</p>" }, OWNER, laterToday, kept);
    expect(reread.html).toBe("<p>newer</p>");
  });

  it("does not carry a printable page across a language switch — his old language's words under his new language's card", async () => {
    const kept = await saveCard("e7", card("en"), OWNER, TEN_AM);
    const laterToday = new Date("2026-09-14T15:00:00Z");
    const switched = await keep("e7", { card: card("ms"), html: null }, OWNER, laterToday, kept);
    expect(switched.html).toBeNull();
  });

  it("goes with the rest of the phone's copy on a refusal, a switch of papers and sign-out", async () => {
    await saveCard("e3", card(), OWNER, TEN_AM);
    await saveCard("e4", card(), OWNER, TEN_AM);
    await clearProfileData("e3");
    expect(await loadCard("e3", OWNER)).toBeNull();
    expect(await loadCard("e4", OWNER)).not.toBeNull();
    await clearAllProfileData();
    expect(await loadCard("e4", OWNER)).toBeNull();
  });
});
