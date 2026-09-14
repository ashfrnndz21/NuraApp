import { describe, expect, it } from "vitest";
import type { ProfileOut, SettingsOut } from "../../src/api/types";
import { ABOUT_ITEMS, BREAKFAST_TIMES, DECADES, deviceEffects, startingSettings, tidy } from "../../src/onboarding/about";
import { en } from "../../src/strings/en";

const profile = (standing: ProfileOut["standing"]): ProfileOut => ({
  profile_id: "p1",
  display_name: "Pa",
  language: "ms",
  region: "SG",
  role: null,
  scopes: [],
  standing,
  key_id: null,
});

const saved: SettingsOut = {
  profile_id: "p1",
  preferred_name: "Papa",
  language: "zh",
  birth_decade: 1950,
  doctor: "Dr Tan",
  breakfast_time: "07:30",
  sight: true,
  hearing: false,
  hands: false,
  cognitive: false,
  updated_at: "2026-09-14T08:00:00Z",
};

describe("about you", () => {
  it("asks the nine questions in the order docs/onboarding.html and E01-03 give", () => {
    expect(ABOUT_ITEMS).toEqual(["name", "language", "born", "doctor", "breakfast", "sight", "hearing", "hands", "memory"]);
  });

  it("starts from what the backend holds, else the profile, else nothing", () => {
    expect(startingSettings(saved, profile("owner"), "en").preferred_name).toBe("Papa");
    const fresh = startingSettings(null, profile("owner"), "en");
    expect(fresh.preferred_name).toBe("Pa");
    expect(fresh.language).toBe("ms");
    expect(fresh.birth_decade).toBeNull();
    expect(fresh.sight).toBe(false);
    expect(startingSettings(null, null, "zh").language).toBe("zh");
  });

  it("trims what was typed and sends an empty box as not given", () => {
    const cleaned = tidy({ ...startingSettings(null, null, "en"), preferred_name: "  Pa ", doctor: "   " });
    expect(cleaned.preferred_name).toBe("Pa");
    expect(cleaned.doctor).toBeNull();
  });

  it("offers a whole line for every breakfast time and every decade", () => {
    for (const time of BREAKFAST_TIMES) expect(en.onboarding.about.times[time]).toBeTruthy();
    expect(DECADES[0]).toBe(1930);
  });
});

describe("what his answers change on the phone, at once", () => {
  it("makes his language the phone's, when the papers are his own", () => {
    expect(deviceEffects({ ...saved, sight: false }, "owner")).toEqual({ language: "zh", density: null });
  });

  it("chooses the big-and-simple look for small print, small buttons or memory", () => {
    for (const key of ["sight", "hands", "cognitive"] as const) {
      expect(deviceEffects({ ...saved, sight: false, [key]: true }, "owner").density).toBe("patient");
    }
  });

  it("never makes the screen smaller on a no", () => {
    expect(deviceEffects({ ...saved, sight: false, hands: false, cognitive: false }, "owner").density).toBeNull();
  });

  it("changes nothing on a chief's phone when she sets up for her father", () => {
    expect(deviceEffects(saved, "steward")).toEqual({ language: null, density: null });
    expect(deviceEffects(saved, "holder")).toEqual({ language: null, density: null });
  });

  it("ignores a language Nura does not speak", () => {
    expect(deviceEffects({ ...saved, language: "ta" }, "owner").language).toBeNull();
  });
});
