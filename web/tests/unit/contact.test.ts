import { describe, expect, it } from "vitest";
import { canPickContact, phoneFromContact } from "../../src/onboarding/contact";

describe("a number from the phone's contacts", () => {
  it("keeps an international number and strips the spaces", () => {
    expect(phoneFromContact("+65 9123 4567")).toBe("+6591234567");
    expect(phoneFromContact("0065 9123-4567")).toBe("+6591234567");
  });

  it("never guesses a country for a number kept without one", () => {
    expect(phoneFromContact("012-345 6789")).toBe("0123456789");
    expect(phoneFromContact("9123 4567")).toBe("91234567");
  });

  it("is not offered where the browser has no picker", () => {
    expect(canPickContact()).toBe(false);
  });
});
