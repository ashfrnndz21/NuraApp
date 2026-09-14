import { describe, expect, it } from "vitest";
import { en } from "../../src/strings/en";
import { ms } from "../../src/strings/ms";
import { zh } from "../../src/strings/zh";
import { refusalSentence } from "../../src/strings";

/** Every refusal class the backend can answer with over HTTP
 *  (`backend/app/channels/api/refusals.py` and the login, doors and consent services). */
const CLASSES = [
  "NoSession", "NoOpenChallenge", "WrongCode", "ChallengeExpired", "ChallengeLocked",
  "NoKey", "OutOfScope", "OutOfRegion", "NotTheirsToRead", "NotTheirKeyToCut", "NoSuchHolder",
  "NoConsent", "ConsentWithheld", "NotTheirConsentToGive", "NotTheirConsentToWithdraw",
  "NotTheClaimant", "NotTheirsToChange", "NoConsentToWithdraw", "NoKeyToClose",
  "NoStewardshipHere", "NoState", "NoSuchReviewCard", "NoSuchLine", "PhotoTooLarge",
  "ProfileAlreadyOwned", "AlreadyConfirmed", "AlreadyRecorded", "AlreadyRegistered",
  "AlreadySetUp", "WaitingToBeClaimed", "NotTheCurrentWording", "WordingNotOnFile",
  "NotWhatWasConfirmed", "NotAConfirmerHere", "HighRiskNeedsLabelPhoto", "NoProvenance",
  "NoWordsInThatLanguage", "NotAPhoto",
];

describe("the refusal map", () => {
  it("has one plain sentence for every class, in every language", () => {
    for (const catalogue of [en, ms, zh]) {
      for (const name of CLASSES) expect((catalogue.refusals as Record<string, string>)[name], name).toBeTruthy();
    }
  });

  it("never shows the class name, an id, or a status code", () => {
    for (const catalogue of [en, ms, zh]) {
      for (const [name, sentence] of Object.entries(catalogue.refusals)) {
        expect(sentence).not.toContain(name === "default" ? "default" : name);
        expect(sentence).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}/i);
        expect(sentence).not.toMatch(/\b(40[0-9]|41[0-9]|5[0-9]{2})\b/);
        expect(sentence).not.toMatch(/[A-Z][a-z]+[A-Z]/); // no CamelCase leaks through
      }
    }
  });

  it("is one sentence: one idea per line", () => {
    for (const sentence of Object.values(en.refusals)) {
      expect(sentence.trim()).toMatch(/^[A-Z].*[.?]$/);
      expect(sentence.split(/[.?!]\s/).filter(Boolean)).toHaveLength(1);
    }
  });

  it("falls back to one sentence for a class it does not know", () => {
    expect(refusalSentence("SomethingNew", "en")).toBe(en.refusals.default);
    expect(refusalSentence(undefined, "en")).toBe(en.refusals.default);
    expect(refusalSentence("OutOfScope", "en")).toBe(en.refusals.OutOfScope);
  });
});
