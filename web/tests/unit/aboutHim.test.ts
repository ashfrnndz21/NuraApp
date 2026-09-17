import { afterEach, describe, expect, it } from "vitest";
import { aboutWhom, language, t } from "../../src/strings";

afterEach(() => {
  aboutWhom.value = null;
  language.value = "en";
});

describe("the chrome that speaks to him, on someone else's key", () => {
  it("is said about him by name, in every language", () => {
    aboutWhom.value = "Pa";
    expect(t().day.notWell).toBe("Pa is not feeling well");
    expect(t().today.stateStable).toBe("Pa's day is steady.");
    expect(t().day.symptomsOpen).toBe("Write down how Pa feels");
    expect(t().record.medicines).toBe("Pa's medicines");
    expect(t().record.back).toBe("Back to Pa's papers");
    expect(t().places.visitsOwn).toBe("Pa's visits");
    // "What Nura uses" (RE-05): the switches say whose they are too.
    expect(t().me.whatNuraUsesLead).toBe("Choose what Nura may use to suggest reads and videos for Pa.");
    expect(t().me.whatNuraUsesFamilies.food).toBe("What Pa eats");
    expect(t().me.whatNuraUsesFamilies.sleep).toBe("Pa's sleep");
    expect(t().me.whatNuraUsesFamilies.steps).toBe("Pa's steps");
    expect(t().me.whatNuraUsesFamilies.water).toBe("Pa's water");
    expect(t().me.whatNuraUsesFamilies.search_topics).toBe("What Pa asks about");
    language.value = "ms";
    expect(t().day.notWell).toBe("Pa rasa tidak sihat");
    language.value = "zh";
    expect(t().day.notWell).toBe("Pa不舒服");
  });
  it("is his own on his own key", () => {
    expect(t().day.notWell).toBe("I am not feeling well");
    expect(t().me.whatNuraUsesLead).toBe("Choose what Nura may use to suggest reads and videos for you.");
    expect(t().me.whatNuraUsesFamilies.food).toBe("What you eat");
    expect(t().me.whatNuraUsesFamilies.search_topics).toBe("What you ask about");
  });
});
