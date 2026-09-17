import { describe, expect, it } from "vitest";
import { cardView, sectionOf, shareAs, speechLanguage, statusLine, variantOf } from "../../src/feed/model";
import { BOUNDARY, item, learning } from "./feedFixtures";

describe("card variants", () => {
  it("follow the backend's type, one for each card the feed makes", () => {
    for (const type of ["flag", "now", "reading", "gate", "duty", "story", "learning", "memo", "reorder", "visit", "notice"]) {
      expect(variantOf({ type })).toBe(type);
    }
  });

  it("show a type this client does not know as its own lines, never dropped", () => {
    const odd = item("a_kind_not_made_yet", "today");
    expect(variantOf(odd)).toBe("text");
    const view = cardView(odd);
    expect(view.headline).toBe(odd.headline);
    expect(view.lines).toEqual(odd.body);
  });

  it("name the section a card came from, and none for a flag or the gate", () => {
    expect(sectionOf({ supply: "now" })).toBe("now");
    expect(sectionOf({ supply: "today" })).toBe("today");
    expect(sectionOf({ supply: "story" })).toBe("story");
    expect(sectionOf({ supply: "learning" })).toBe("learning");
    expect(sectionOf({ supply: "flag" })).toBeNull();
    expect(sectionOf({ supply: "gate" })).toBeNull();
  });
});

describe("a card's words", () => {
  it("are the backend's only: headline, body, why, voice, the State it was rendered from", () => {
    const reading = item("reading", "today", { rendered_from_state: "state-9", voice: ["Your blood pressure today was 138 over 84."] });
    const view = cardView(reading);
    const backend = new Set([reading.headline, ...reading.body, ...reading.voice, reading.why.plain]);
    for (const line of [view.headline, ...view.lines, ...view.boundary, view.why, ...view.spoken]) expect(backend.has(line), line).toBe(true);
    expect(view.spoken).toEqual(reading.voice);
    expect(view.stateId).toBe("state-9");
  });

  it("keep a learning card's boundary apart, the lines it ends on, shown once", () => {
    const view = cardView(learning());
    expect(view.lines).toEqual(["Sit down and rest for 5 minutes first.", "This comes from HealthHub."]);
    expect(view.boundary).toEqual(BOUNDARY.split("\n"));
    expect(view.boundary.at(-1)).toBe("Ask your doctor.");
    expect(view.why).toBe("This is about your blood pressure, which is on your papers.");
    // The spoken twin is the backend's voice, boundary and all.
    expect(view.spoken.at(-1)).toBe("Ask your doctor.");
  });

  it("mark a card the did_you_know rule proposed, and no other learning card", () => {
    const picked = cardView(learning({ why: { kind: "learning", rule: "did_you_know", topic: "medicine.blood_pressure_tablet", plain: "This is about your blood pressure tablet, which is on your papers." } }));
    expect(picked.didYouKnow).toBe(true);
    expect(cardView(learning()).didYouKnow).toBe(false);
  });

  it("read the shown lines out when the backend wrote no voice script", () => {
    const duty = item("duty", "gate", { voice: [], body: ["Mei is on duty today."] });
    expect(cardView(duty).spoken).toEqual(["duty headline", "Mei is on duty today."]);
  });
});

describe("a card's buttons", () => {
  it("are the four side actions on every content card", () => {
    for (const type of ["flag", "now", "reading", "story", "learning", "memo", "reorder", "visit", "notice", "clip", "recap", "local", "seasonal", "food"]) {
      expect(cardView(item(type, "today")).actions).toEqual(["hear", "ask", "family", "notForMe"]);
    }
  });

  it("are Hear and Keep going on the gate, which is a pause and not content", () => {
    const gate = cardView(item("gate", "gate"));
    expect(gate.actions).toEqual(["hear"]);
    expect(gate.action).toBe("keepGoing");
    // The caregiver's list has no gate: the duty card is a card, with every side action.
    expect(cardView(item("duty", "today")).actions).toEqual(["hear", "ask", "family", "notForMe"]);
  });

  it("send the now card to Today, where Taken is; no other card has an action", () => {
    expect(cardView(item("now", "now")).action).toBe("toTablets");
    for (const type of ["reading", "story", "learning", "flag", "reorder"]) expect(cardView(item(type, "today")).action).toBeNull();
  });

  it("share a card only as a kind the family thread can carry, by reference", () => {
    expect(shareAs({ type: "reading" })).toBe("reading");
    expect(shareAs({ type: "visit" })).toBe("visit");
    for (const type of ["now", "story", "learning", "flag", "reorder", "memo", "notice", "gate"]) expect(shareAs({ type })).toBeNull();
  });
});

describe("the caregiver's list", () => {
  it("says what became of each card, from the backend's status; the patient's never does", () => {
    expect(statusLine({ status: "held", type: "notice" }, "caregiver")).toBe("statusHeld");
    expect(statusLine({ status: "sent", type: "reading" }, "caregiver")).toBe("statusSent");
    expect(statusLine({ status: "opened", type: "reading" }, "caregiver")).toBe("statusOpened");
    expect(statusLine({ status: "dismissed", type: "reading" }, "caregiver")).toBe("statusDismissed");
    expect(statusLine({ status: "generated", type: "reading" }, "caregiver")).toBeNull();
    expect(statusLine({ status: "held", type: "duty" }, "caregiver")).toBeNull();
    expect(statusLine({ status: "held", type: "notice" }, "patient")).toBeNull();
  });
});

describe("the voice's language", () => {
  it("is the card's own when Nura speaks it, else the app's", () => {
    expect(speechLanguage("ms", "en")).toBe("ms");
    expect(speechLanguage("zh-Hans", "en")).toBe("zh");
    expect(speechLanguage("ta", "ms")).toBe("ms");
  });
});
