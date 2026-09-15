import { describe, expect, it } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import type { BriefOut, CloudOut, DayNudgesOut, FeedItemOut, NudgePlanOut, OfflineCardsOut, ProfileOut, VisitQuestionsOut, VisitSummaryOut, WhatToDoOut } from "../../src/api/types";
import { briefView, clipsOf, cloudView, decisionsFor, nudgeToShow, offlineLines, questionCard, waitingSummary, whatToDoLines } from "../../src/day/model";
import { keepCards, keptCards, wantsCards } from "../../src/day/offline";
import { whenNotReached } from "../../src/day/redPath";
import { bindingOf, clearProfileData } from "../../src/offline/todayCache";
import { kvKeys } from "../../src/store/kv";
import { LANGUAGES, stringsFor } from "../../src/strings";

/** The patient's day (W7): every line the backend's, in its order; the red-flag path never
 *  leaves him with nothing. */

const en = stringsFor("en");
const owner: ProfileOut = { profile_id: "p1", display_name: "Pa", language: "en", region: "SG", role: null, scopes: ["records", "emergency"], standing: "owner", key_id: null };

/** Checkpoint 14's urgent card, as the backend sends it. */
const URGENT: WhatToDoOut = {
  card_id: "c1", state_id: "s1", kind: "red_flag", posture: "act", language: "en",
  lines: [
    { id: "boundary.opening", text: "Mei knows now." },
    { id: "nfw.call_995", text: "Call the ambulance now on 995." },
    { id: "nfw.then_call_chief", text: "After that, call Mei." },
    { id: "boundary.urgent", text: "Nura does not decide what is wrong." },
  ],
  artifact_id: null, event_id: null, fact_id: null, heard: true, by_voice: true, transcript_confidence: 0.94,
  red_flags: ["chest_tightness"], suppressed: [], symptoms: [], flag_id: "f1", notified_person_ids: ["m1"], check_in_at: null, missed_medicine: null,
};

const KEPT: OfflineCardsOut = {
  language: "en",
  emergency_number: "995",
  red_flag: [
    { id: "boundary.opening", text: "You did right to say so." },
    { id: "nfw.offline_not_sent", text: "Nura could not send this to your family." },
    { id: "nfw.call_995", text: "Call the ambulance now on 995." },
    { id: "nfw.then_call_chief", text: "After that, call Mei." },
    { id: "boundary.urgent", text: "Nura does not decide what is wrong." },
  ],
  unknown: [
    { id: "boundary.opening", text: "You did right to say so." },
    { id: "nfw.offline_not_sent", text: "Nura could not send this to your family." },
    { id: "nfw.offline_call_chief", text: "Call Mei now." },
    { id: "nfw.offline_bad_995", text: "If you feel very bad, call the ambulance now on 995." },
    { id: "boundary.urgent", text: "Nura does not decide what is wrong." },
  ],
};

describe("what to do now", () => {
  it("is the backend's lines in its order, none dropped, none moved", () => {
    expect(whatToDoLines(URGENT)).toEqual(["Mei knows now.", "Call the ambulance now on 995.", "After that, call Mei.", "Nura does not decide what is wrong."]);
  });

  it("with no network is the card the phone kept, word for word", () => {
    expect(offlineLines("red_flag", KEPT, "SG", en, "en")).toEqual({ lines: KEPT.red_flag.map((line) => line.text), from: "kept" });
    expect(offlineLines("unknown", KEPT, "SG", en, "en").lines[2]).toBe("Call Mei now.");
  });

  it("kept in another language is not his card: the catalogue's, in the language he reads now", () => {
    const ms = stringsFor("ms");
    const shown = offlineLines("red_flag", KEPT, "SG", ms, "ms");
    expect(shown.from).toBe("catalogue");
    expect(shown.lines[0]).toBe(ms.day.fallback.youDidRight);
  });

  it("with nothing kept is the backend's offline card from the catalogue, for his region: never nothing", () => {
    expect(offlineLines("red_flag", null, "SG", en, "en")).toEqual({
      lines: ["You did right to say so.", "Nura could not send this to your family.", "Call the ambulance now on 995.", "Nura does not decide what is wrong."],
      from: "catalogue",
    });
    expect(offlineLines("red_flag", null, "MY", en, "en").lines[2]).toBe("Call the ambulance now on 999.");
    expect(offlineLines("unknown", null, "MY", en, "en").lines).toEqual([
      "You did right to say so.",
      "Nura could not send this to your family.",
      "Call your family now.",
      "If you feel very bad, call the ambulance now on 999.",
      "Nura does not decide what is wrong.",
    ]);
    const empty: OfflineCardsOut = { ...KEPT, red_flag: [], unknown: [] };
    for (const code of LANGUAGES) {
      for (const kind of ["red_flag", "unknown"] as const) {
        const shown = offlineLines(kind, empty, "SG", stringsFor(code), code);
        expect(shown.lines.length).toBeGreaterThanOrEqual(4);
        expect(shown.lines.every((line) => line.trim().length > 0)).toBe(true);
        // Never "Ask your doctor." after an emergency number: the one closing line is last.
        expect(shown.lines[shown.lines.length - 1]).toBe(stringsFor(code).day.fallback.closing);
      }
    }
  });

  it("says why it is the offline card: no network, a server that could not answer, or a no", () => {
    expect(whenNotReached("red_flag", new Unreachable(), KEPT, "SG", en, "en")).toEqual({ lines: KEPT.red_flag.map((l) => l.text), offline: "network", refusal: null });
    expect(whenNotReached("red_flag", new Refused("HttpError", 502), null, "SG", en, "en").offline).toBe("server");
    const refused = whenNotReached("unknown", new Refused("NoKey", 403), null, "SG", en, "en");
    expect(refused.offline).toBeNull();
    expect(refused.refusal).toBe("NoKey");
    expect(refused.lines[1]).toBe("Nura could not send this to your family.");
  });
});

describe("the offline cards on the phone", () => {
  it("are bound to the key that read them and go with the rest of his papers", async () => {
    const binding = bindingOf(owner);
    await keepCards("p1", KEPT, binding, new Date("2026-09-14T02:00:00Z"), "Asia/Singapore");
    expect((await keptCards("p1", binding, new Date("2026-09-14T03:00:00Z")))?.cards).toEqual(KEPT);
    expect(await keptCards("p1", bindingOf({ ...owner, standing: "holder", key_id: "k9", scopes: ["emergency"] }))).toBeNull();
    expect(await kvKeys("nfw.")).toEqual([]);
    await keepCards("p1", KEPT, binding, new Date(), "Asia/Singapore");
    await clearProfileData("p1");
    expect(await kvKeys("nfw.")).toEqual([]);
  });

  it("are read again when there are none, in another language, or a day on", () => {
    const at = new Date("2026-09-14T02:00:00Z");
    const entry = { cards: KEPT, binding: bindingOf(owner), fetchedAt: at.toISOString(), expiresAt: "2026-09-14T16:00:00.000Z" };
    expect(wantsCards(null, "en", at)).toBe(true);
    expect(wantsCards(entry, "ms", at)).toBe(true);
    expect(wantsCards(entry, "en", new Date(at.getTime() + 60_000))).toBe(false);
    expect(wantsCards(entry, "en", new Date(at.getTime() + 24 * 3600_000))).toBe(true);
  });
});

describe("the visit", () => {
  it("shows the whole brief in its order, the boundary last", () => {
    const brief: BriefOut = {
      brief_id: "b1", appointment_id: "a1", language: "en", state_id: "s1", built_at: "2026-09-14T02:00:00Z",
      lines: [
        { section: "purpose", key: "brief.when", text: "You see Dr Tan on Wednesday 16 September.", spoken: "You see Dr Tan on Wednesday 16 September.", sources: [] },
        { section: "changed", key: "brief.changed", text: "Since Monday 7 September, there is 1 new number.", spoken: "Since Monday 7 September, there is 1 new number.", sources: [] },
        { section: "bring", key: "brief.bring", text: "Bring your blood pressure book.", spoken: "Bring your blood pressure book.", sources: [] },
        { section: "boundary", key: "boundary", text: "Ask Dr Tan.", spoken: "Ask Dr Tan.", sources: [] },
      ],
      boundary: "This is not a doctor's advice.\nAsk Dr Tan.",
    };
    const view = briefView(brief);
    expect(view.lines.map((line) => line.section)).toEqual(["purpose", "changed", "bring"]);
    expect(view.boundary).toEqual(["This is not a doctor's advice.", "Ask Dr Tan."]);
    expect(view.spoken.slice(-2)).toEqual(view.boundary);
  });

  it("marks each question line of his card, and nothing else, to be taken off on his yes", () => {
    const found: VisitQuestionsOut = {
      questions: [
        { question_id: "q1", appointment_id: "a1", text: "Is the water pill bad for my kidneys?", language: "en", source: "person", source_kind: null, source_ids: [], priority: 1, added_by_person_id: "p", supersedes_id: null, removed: false, state_id: "s", created_at: "" },
        { question_id: "q2", appointment_id: "a1", text: "Ask Dr Tan how often to take your blood pressure.", language: "en", source: "gap", source_kind: "reading_stale", source_ids: [], priority: 2, added_by_person_id: null, supersedes_id: null, removed: false, state_id: "s", created_at: "" },
      ],
      card: ["Is the water pill bad for my kidneys?", "Ask Dr Tan how often to take your blood pressure.", "Nura kept these questions for you.", "Ask Dr Tan."],
      spoken_card: [],
    };
    expect(questionCard(found).map((line) => line.questionId)).toEqual(["q1", "q2", null, null]);
  });

  it("keeps every item of the card unless he left it out, and opens the newest card still waiting", () => {
    const card = { summary_id: "v2", created_at: "2026-09-14T03:00:00Z", confirmed_at: null, items: [{ item_id: "i1" }, { item_id: "i2" }] } as unknown as VisitSummaryOut;
    expect(decisionsFor(card, new Set(["i2"]))).toEqual([
      { item_id: "i1", decision: "confirmed" },
      { item_id: "i2", decision: "rejected" },
    ]);
    const older = { ...card, summary_id: "v1", created_at: "2026-09-14T02:00:00Z" } as VisitSummaryOut;
    const done = { ...card, summary_id: "v3", created_at: "2026-09-14T04:00:00Z", confirmed_at: "2026-09-14T04:10:00Z" } as VisitSummaryOut;
    expect(waitingSummary([older, done, card])?.summary_id).toBe("v2");
    expect(waitingSummary([done])).toBeNull();
  });
});

describe("a card's clips", () => {
  const item = (cite: unknown) => ({ item_id: "f1", cite, body: [], voice: [] }) as unknown as FeedItemOut;
  it("are the card's own lines with the stretch each was said in", () => {
    const clips = clipsOf(item({ clips: [{ line: "Every morning, weigh yourself before breakfast.", artifact_id: "r1", start_s: 28.9, end_s: 36.2, doctor: "Dr Tan" }] }));
    expect(clips.get("Every morning, weigh yourself before breakfast.")?.start_s).toBe(28.9);
  });
  it("are none when the card cites none, or cites something that is not a stretch", () => {
    expect(clipsOf(item(null)).size).toBe(0);
    expect(clipsOf(item({ clips: [{ line: "x", artifact_id: "r1", start_s: 5, end_s: 5, doctor: "Dr Tan" }, { line: 3 }] })).size).toBe(0);
  });
});

describe("the feeling cloud", () => {
  const cloud: CloudOut = {
    state_id: "s1", language: "en", show: true, because: "state_changed", prompt: ["How do you feel today?"],
    words: [
      { word: "dizzy", label: "Dizzy", weight: 3, red: false, reasons: [{ code: "new_medicine" }] },
      { word: "chest_tightness", label: "Chest pain", weight: 1, red: true, reasons: [{ code: "base" }] },
      { word: "fine", label: "Fine today", weight: 1, red: false, reasons: [{ code: "base" }] },
    ],
  };
  it("shows the backend's words in its order, sized by weight, and never their reasons", () => {
    const view = cloudView(cloud)!;
    expect(view.words.map((one) => [one.label, one.size, one.red])).toEqual([["Dizzy", 3, false], ["Chest pain", 1, true], ["Fine today", 1, false]]);
    expect(JSON.stringify(view)).not.toContain("new_medicine");
  });
  it("is not on Today when the backend says it does not show", () => {
    expect(cloudView({ ...cloud, show: false })).toBeNull();
    expect(cloudView(null)).toBeNull();
  });
});

describe("the day's nudge", () => {
  const now = new Date("2026-09-14T02:30:00Z");
  const handed = {
    nudge_id: "n1", kind: "presence", day: "2026-09-14", lines: ["Mei wrote to you today."], why: "You see this because Mei wrote today.", cap_class: "one",
    send_after: "2026-09-14T02:00:00Z", expires_at: "2026-09-14T13:00:00Z", rendered_from_state: "s", handed_over_at: "2026-09-14T01:00:00Z", voice: [], responses: [] as string[],
  };
  const plan: NudgePlanOut = {
    day: "2026-09-14", held: [], none_because: null,
    drafts: [{ kind: "anticipation", lines: ["You see Dr Tan tomorrow."], voice: [], language: "en", why: "You see this because of your visit tomorrow.", cap_class: "one", day: "2026-09-14", send_after: "2026-09-14T02:00:00Z", expires_at: "2026-09-14T13:00:00Z", state_id: "s", priority: 3, dedupe_key: "k" }],
  };
  const day = (nudges: (typeof handed)[]): DayNudgesOut => ({ day: "2026-09-14", nudges, withheld: 0 });

  it("is the one handed over, from its time until it expires, until he answers it", () => {
    expect(nudgeToShow(day([handed]), plan, now)).toMatchObject({ from: "handed", nudgeId: "n1", why: handed.why });
    expect(nudgeToShow(day([{ ...handed, responses: ["accepted"] }]), plan, now)).toBeNull();
    expect(nudgeToShow(day([handed]), plan, new Date("2026-09-14T01:59:00Z"))).toBeNull();
    expect(nudgeToShow(day([handed]), plan, new Date("2026-09-14T13:00:00Z"))).toBeNull();
  });
  it("is the plan's draft once its time has come, when none was handed over", () => {
    expect(nudgeToShow(day([]), plan, now)).toMatchObject({ from: "planned", kind: "anticipation", lines: ["You see Dr Tan tomorrow."] });
    expect(nudgeToShow(day([]), { ...plan, drafts: [] }, now)).toBeNull();
  });
});
