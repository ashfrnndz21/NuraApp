import { afterEach, describe, expect, it } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { densityChosen, densityFor, isSelf, profile } from "../../src/store/session";

/** Whose voice Home speaks in (cp3-home): `isSelf()` alone, never `density()`/`densityFor()`
 *  (store/session.ts). The bug the owner found — "Ask about Tan" on Tan's own phone — was
 *  `density()` doing double duty as both the "Look" (size/layout) preference and the decision
 *  of whose voice the app speaks in; a device preference for a bigger, simpler layout is
 *  legitimately available to an owner too (`Me.tsx`'s "patient"/"caregiver" pills are not
 *  gated by standing), and once chosen it must never also start speaking about him in the
 *  third person on his own phone. */

const owner = (extra: Partial<ProfileOut> = {}): ProfileOut => ({
  profile_id: "p1",
  display_name: "Tan",
  language: "en",
  region: "SG",
  role: null,
  scopes: ["records", "medicines"],
  standing: "owner",
  key_id: null,
  ...extra,
});

afterEach(() => {
  profile.value = null;
  densityChosen.value = null;
});

describe("isSelf(): whose papers these are, never a device preference", () => {
  it("is true for the profile's own owner, whatever look the device is set to", () => {
    profile.value = owner();
    expect(isSelf()).toBe(true);
    densityChosen.value = "caregiver";
    expect(isSelf()).toBe(true);
  });

  it("is false for anyone holding a key, whatever look the device is set to", () => {
    profile.value = owner({ standing: "holder", key_id: "k1" });
    expect(isSelf()).toBe(false);
    densityChosen.value = "patient";
    expect(isSelf()).toBe(false);
  });

  it("is false with no profile open at all", () => {
    profile.value = null;
    expect(isSelf()).toBe(false);
  });
});

describe("density()/densityFor(): the 'Look' preference, decoupled from isSelf()", () => {
  it("still follows standing when nothing has been chosen", () => {
    expect(densityFor("owner", null)).toBe("patient");
    expect(densityFor("holder", null)).toBe("caregiver");
  });

  it("an owner may choose the caregiver look without it changing who he is", () => {
    expect(densityFor("owner", "caregiver")).toBe("caregiver");
  });

  it("a caregiver may choose the patient look without it changing who he is", () => {
    expect(densityFor("holder", "patient")).toBe("patient");
  });
});
