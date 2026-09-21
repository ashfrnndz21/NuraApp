import { describe, expect, it } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { classifySignInError, shouldOfferResend, validCode, validPhone } from "../../src/signin";

describe("validPhone", () => {
  it("wants at least 8 digits, whatever else is typed beside them", () => {
    expect(validPhone("+65")).toBe(false);
    expect(validPhone("+65 1234")).toBe(false);
    expect(validPhone("+65 91234567")).toBe(true);
    expect(validPhone("+60 12 345 6789")).toBe(true);
  });
});

describe("validCode", () => {
  it("wants exactly 6 digits", () => {
    expect(validCode("")).toBe(false);
    expect(validCode("12345")).toBe(false);
    expect(validCode("1234567")).toBe(false);
    expect(validCode("abcdef")).toBe(false);
    expect(validCode("123456")).toBe(true);
    expect(validCode(" 123456 ")).toBe(true);
  });
});

describe("classifySignInError", () => {
  it("names each real state the backend can report, never inventing one it did not", () => {
    expect(classifySignInError(new Refused("WrongCode", 409))).toBe("wrongCode");
    expect(classifySignInError(new Refused("ChallengeExpired", 409))).toBe("expired");
    expect(classifySignInError(new Refused("ChallengeLocked", 429))).toBe("locked");
    expect(classifySignInError(new Refused("NoOpenChallenge", 404))).toBe("noChallenge");
    expect(classifySignInError(new Refused("SomethingElse", 400))).toBe("other");
    expect(classifySignInError(new Unreachable())).toBe("network");
    expect(classifySignInError(new Error("boom"))).toBe("other");
    expect(classifySignInError(null)).toBe("other");
  });
});

describe("shouldOfferResend", () => {
  it("points at Resend only when the code itself is gone, not for a mistype or a dead network", () => {
    expect(shouldOfferResend("expired")).toBe(true);
    expect(shouldOfferResend("locked")).toBe(true);
    expect(shouldOfferResend("noChallenge")).toBe(true);
    expect(shouldOfferResend("wrongCode")).toBe(false);
    expect(shouldOfferResend("network")).toBe(false);
    expect(shouldOfferResend("other")).toBe(false);
  });
});
