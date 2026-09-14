import { describe, expect, it } from "vitest";
import { cardView, sourceOf } from "../../src/feed/model";
import { item, learning } from "./feedFixtures";

const CITED = { publisher: "HealthHub", url: "https://www.healthhub.sg/a-z/diseases-and-conditions/diabetes", passage: "Diabetes is a condition where there is too much sugar in the blood." };

describe("a learning card's cited page (E21-06)", () => {
  it("is the publisher and the https link the backend cited", () => {
    expect(cardView(learning({ cite: CITED })).source).toEqual({ publisher: "HealthHub", url: CITED.url });
  });

  it("is nothing without a publisher, or without an https link", () => {
    expect(cardView(learning()).source).toBeNull();
    expect(sourceOf({ type: "learning", cite: { ...CITED, url: "javascript:alert(1)" } })).toBeNull();
    expect(sourceOf({ type: "learning", cite: { ...CITED, publisher: " " } })).toBeNull();
    expect(sourceOf({ type: "learning", cite: null })).toBeNull();
  });

  it("is only ever on a learning card", () => {
    for (const type of ["notice", "story", "reading", "memo"]) {
      expect(cardView(item(type, "learning", { cite: CITED })).source).toBeNull();
    }
  });
});
