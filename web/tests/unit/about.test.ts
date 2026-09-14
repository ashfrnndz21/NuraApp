import { describe, expect, it } from "vitest";
import type { ProfileOut, SettingsOut } from "../../src/api/types";
import { ABOUT_ITEMS, BREAKFAST_TIMES, DECADES, deviceEffects, isSwitch, startingSettings, SWITCHES, tidy } from "../../src/onboarding/about";
import { en } from "../../src/strings/en";
import { ms } from "../../src/strings/ms";
import { zh } from "../../src/strings/zh";

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
  settings_id: "s1",
  profile_id: "p1",
  language: "zh",
  conditions: ["high_blood_pressure"],
  density: "detailed",
  large_text: false,
  high_contrast: false,
  voice_on: false,
  big_targets: false,
  one_thing_per_screen: false,
  read_back: false,
  repeat_prompts: false,
  preferred_name: "Papa",
  doctor_name: "Dr Tan",
  breakfast_time: "07:30",
  birth_decade: 1950,
  set_by_person_id: "someone",
  set_at: "2026-09-14T02:00:00Z",
  withheld: [],
};

describe("about you, as #117's settings hold it", () => {
  it("asks the name, language, decade, doctor and breakfast, then one question per switch, then the density", () => {
    expect(ABOUT_ITEMS).toEqual(["name", "language", "born", "doctor", "breakfast", ...SWITCHES, "density"]);
    expect(SWITCHES).toEqual(["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"]);
    expect(ABOUT_ITEMS.filter(isSwitch)).toEqual([...SWITCHES]);
  });

  it("has a whole question for every switch, for his own papers and in someone else's name, in every language", () => {
    for (const strings of [en, ms, zh]) {
      for (const item of SWITCHES) {
        expect(strings.onboarding.about.switchSelf[item], item).toBeTruthy();
        expect(strings.onboarding.about.switchSelf[item]).not.toContain("{name}");
        expect(strings.onboarding.about.switchOther[item]).toContain("{name}");
      }
    }
  });

  it("starts from what the backend holds, else the profile's name and language and #117's defaults", () => {
    const held = startingSettings(saved, profile("owner"), "en");
    expect([held.preferred_name, held.doctor_name, held.conditions, held.birth_decade]).toEqual(["Papa", "Dr Tan", ["high_blood_pressure"], 1950]);
    const fresh = startingSettings(null, profile("owner"), "en");
    expect(fresh.preferred_name).toBe("Pa");
    expect(fresh.language).toBe("ms");
    expect(fresh.density).toBe("detailed");
    expect(fresh.conditions).toEqual([]);
    for (const item of SWITCHES) expect(fresh[item]).toBe(false);
    expect(startingSettings(null, null, "zh").language).toBe("zh");
  });

  it("trims what was typed and sends an empty box as not given", () => {
    const cleaned = tidy({ ...startingSettings(null, null, "en"), preferred_name: "  Pa ", doctor_name: "   " });
    expect(cleaned.preferred_name).toBe("Pa");
    expect(cleaned.doctor_name).toBeNull();
  });

  it("offers a whole line for every breakfast time and every decade", () => {
    for (const time of BREAKFAST_TIMES) expect(en.onboarding.about.times[time]).toBeTruthy();
    expect(DECADES[0]).toBe(1930);
  });
});

const sent = startingSettings(saved, profile("owner"), "en");

describe("what his answers change on the phone, at once", () => {
  it("makes his language the phone's, when the papers are his own", () => {
    expect(deviceEffects(sent, "owner")).toEqual({ language: "zh", density: null });
  });

  it("chooses the big-and-simple look for bigger writing, bigger buttons, one thing at a time or the simple density", () => {
    for (const patch of [{ large_text: true }, { big_targets: true }, { one_thing_per_screen: true }, { density: "simple" as const }]) {
      expect(deviceEffects({ ...sent, ...patch }, "owner").density, JSON.stringify(patch)).toBe("patient");
    }
  });

  it("never makes the screen smaller", () => {
    expect(deviceEffects({ ...sent, high_contrast: true, voice_on: true, read_back: true }, "owner").density).toBeNull();
  });

  it("changes nothing on a chief's phone when she sets up for her father", () => {
    expect(deviceEffects({ ...sent, large_text: true }, "steward")).toEqual({ language: null, density: null });
    expect(deviceEffects(sent, "holder")).toEqual({ language: null, density: null });
  });

  it("ignores a language Nura does not speak", () => {
    expect(deviceEffects({ ...sent, language: "ta" }, "owner").language).toBeNull();
  });
});
