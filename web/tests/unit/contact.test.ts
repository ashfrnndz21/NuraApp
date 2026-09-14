import { describe, expect, it } from "vitest";
import { canPickContact, phoneFromContact } from "../../src/onboarding/contact";

describe("a number from the phone's contacts", () => {
  it("keeps an international number and strips the spaces", () => {
    expect(phoneFromContact("+65 9123 4567")).toBe("+6591234567");
    expect(phoneFromContact("0065 9123-4567")).toBe("+6591234567");
  });

  it("reads a local number as Malaysian when it starts with 0, else Singaporean", () => {
    expect(phoneFromContact("012-345 6789")).toBe("+60123456789");
    expect(phoneFromContact("9123 4567")).toBe("+6591234567");
    expect(phoneFromContact("6591234567")).toBe("+6591234567");
  });

  it("is not offered where the browser has no picker", () => {
    expect(canPickContact()).toBe(false);
  });
});
