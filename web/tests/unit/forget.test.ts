import { beforeEach, describe, expect, it } from "vitest";
import type { ProfileOut } from "../../src/api/types";
import { forgetEverything } from "../../src/flow";
import { known } from "../../src/store/profiles";
import { largeText, me, profile, setLargeText, setToken, token } from "../../src/store/session";
import { kvGet } from "../../src/store/kv";
import { todayPage } from "../../src/today/page";
import { aboutWhom } from "../../src/strings";

/** Whatever way the app lands on sign-in — he tapped Sign out, or his session expired while the
 *  phone sat in a drawer — nothing of the last person is left for the next one to find. The
 *  expired session is the door people actually walk through, and it used to clear nothing at
 *  all (app.tsx), which is how the switcher could show the last person's names. */

const HIS: ProfileOut = {
  profile_id: "p1",
  display_name: "Pa",
  language: "en",
  region: "SG",
  role: null,
  scopes: ["medicines"],
  standing: "owner",
  key_id: null,
};

const HERS: ProfileOut = { ...HIS, profile_id: "p2", display_name: "Mei", standing: "holder", role: "chief", key_id: "k1" };

describe("forgetting everything on the way back to sign-in", () => {
  beforeEach(async () => {
    await setToken("a-token");
    await import("../../src/store/session").then((store) => store.chooseProfile(HIS));
    me.value = { person_id: "me", display_name: "Pa", phone_e164: "+6591234567" } as never;
    known.value = [HIS, HERS];
    todayPage.value = { profileId: "p1" } as never;
    await setLargeText(true);
  });

  it("leaves no token, no papers, no name and no list of whose papers this person could open", async () => {
    await forgetEverything();

    expect(token.value, "the token").toBeNull();
    expect(profile.value, "whose papers were open").toBeNull();
    expect(me.value, "who was signed in").toBeNull();
    expect(todayPage.value, "the page the phone kept").toBeNull();
    // The one the sign-out path cleared and every other path did not: the switcher reads this,
    // so the next person on a shared phone would have seen the last person's names in it.
    expect(known.value, "whose papers this person could open").toBeNull();
    // Chrome said about him by name is driven by this: it must not outlive his papers.
    expect(aboutWhom.value, "whose name the chrome says").toBeNull();
    expect(largeText.value, "his large-text setting, which came from his State").toBe(false);
  });

  it("forgets them on the device too, not only in memory", async () => {
    await forgetEverything();

    expect(await kvGet("session.token"), "the token on the device").toBeUndefined();
    expect(await kvGet("session.profile"), "the papers on the device").toBeUndefined();
    expect(await kvGet("device.text"), "his large-text setting on the device").toBeUndefined();
  });
});
