import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { needsOnboarding, openProfile, screen } from "../../src/flow";
import { stage } from "../../src/onboarding/state";
import { profile } from "../../src/store/session";

/** The owner's report: he signed in on a fresh number and landed on Home, with nothing on
 *  it — his account had no name at all. Whatever door opens a profile (his own tile, a
 *  key, a claim), a bare profile — no name, meaning About you was never finished — must go
 *  to onboarding first, every time, until it says "Ready" (E01-01's gate). A profile that
 *  already has a name lands on Today exactly as it always did. */

const BARE: ProfileOut = {
  profile_id: "p-bare",
  display_name: "",
  language: "en",
  region: "SG",
  role: null,
  scopes: [],
  standing: "owner",
  key_id: null,
};

const NAMED: ProfileOut = { ...BARE, profile_id: "p-named", display_name: "Pa" };

describe("needsOnboarding (E01-01)", () => {
  it("is true for a profile with no name at all", () => {
    expect(needsOnboarding(BARE)).toBe(true);
  });

  it("is true for a name that is only whitespace", () => {
    expect(needsOnboarding({ ...BARE, display_name: "   " })).toBe(true);
  });

  it("is false once a name is on the profile", () => {
    expect(needsOnboarding(NAMED)).toBe(false);
  });
});

describe("opening a profile respects the gate", () => {
  beforeEach(() => {
    profile.value = null;
    screen.value = { name: "loading" };
    stage.value = { name: "about" };
  });

  it("sends a bare profile to onboarding instead of Today", async () => {
    await openProfile(BARE);

    expect(profile.value?.profile_id).toBe("p-bare");
    expect(screen.value).toEqual({ name: "onboarding" });
    // startOnboarding resets the stage to the first step, whatever it was mid-way through.
    expect(stage.value).toEqual({ name: "about" });
  });

  it("still lands a named profile on Today", async () => {
    await openProfile(NAMED);

    expect(profile.value?.profile_id).toBe("p-named");
    expect(screen.value).toEqual({ name: "today" });
  });
});
