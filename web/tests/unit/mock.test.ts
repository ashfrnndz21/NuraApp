import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import type { Call, Passthrough } from "../../src/api/client";
import { Refused } from "../../src/api/client";
import type { BiographyOut, KeyOut, PlanOut, ReviewCardOut, SettingsOut, SharingPreviewOut, WordingOut } from "../../src/api/types";
import { isPdf } from "../../src/onboarding/actions";
import { mockTransport, resetMock } from "../../src/api/mock";
import { READ_BACK } from "../../src/api/mock/words";

/** The stand-in for E01 keeps the contract the screens are built on: whole lines from the
 *  backend, a no that sticks, a paper learned only once its card is confirmed, and a Later
 *  that retires a gap on the second time. Everything else goes to the real API. */

const reviewed = (kind: ReviewCardOut["document_kind"], confirmed = true): ReviewCardOut => ({
  card_id: "card-1",
  profile_id: "p1",
  artifact_id: "art-1",
  document_kind: kind,
  document_date: "2023-09-07",
  asked_as: null,
  source: null,
  notice: null,
  high_risk_class: null,
  created_at: "2026-09-14T08:00:00Z",
  confirmed_at: confirmed ? "2026-09-14T08:01:00Z" : null,
  fields: [],
});

let asked: string[] = [];
const live = (card: ReviewCardOut): Passthrough =>
  (<T,>(path: string, _call: Call) => {
    asked.push(path);
    return Promise.resolve(card as unknown as T);
  }) as Passthrough;

function call<T>(path: string, init: Call = {}, passthrough: Passthrough = live(reviewed("lab_report"))): Promise<T> {
  const answer = mockTransport(path, { token: "t", ...init }, passthrough);
  if (!answer) throw new Error(`the mock does not answer ${path}`);
  return answer as Promise<T>;
}

beforeEach(() => {
  resetMock();
  asked = [];
});

describe("the E01 stand-in", () => {
  it("leaves every route it does not own to the real API", () => {
    expect(mockTransport("/auth/phone/start", { method: "POST" }, live(reviewed("lab_report")))).toBeUndefined();
    expect(mockTransport("/profiles/p1/photos", { method: "POST" }, live(reviewed("lab_report")))).toBeUndefined();
    expect(mockTransport("/profiles/p1/confirmations", { method: "POST" }, live(reviewed("lab_report")))).toBeUndefined();
    expect(mockTransport("/profiles/p1/medicines", {}, live(reviewed("lab_report")))).toBeUndefined();
    // A path under a mocked resource that the mock does not know is not the biography's.
    expect(mockTransport("/profiles/p1/settings/anything", { method: "POST" }, live(reviewed("lab_report")))).toBeUndefined();
  });

  it("keeps the settings it was given", async () => {
    const blank = await call<SettingsOut>("/profiles/p1/settings");
    expect(blank.updated_at).toBeNull();
    const put = { ...blank, preferred_name: "Pa", doctor: "Dr Tan", sight: true };
    await call("/profiles/p1/settings", { method: "PUT", body: put });
    expect((await call<SettingsOut>("/profiles/p1/settings")).doctor).toBe("Dr Tan");
  });

  it("answers the words he tapped with whole lines, and a no stays a no", async () => {
    const bio = await call<BiographyOut>("/profiles/p1/biography", {
      method: "POST",
      body: { language: "en", words: ["bp", "bp_meds", "nonsense"], answers: { bp_meds: "gt5" } },
    });
    expect(bio.words).toEqual(["bp", "bp_meds"]);
    expect(bio.read_back.map((line) => line.text)).toEqual([
      READ_BACK.bp,
      READ_BACK.bp_meds,
      "You have taken them for more than 5 years.",
    ]);
    for (const line of bio.read_back) {
      expect(line.state_id).toBeTruthy();
      expect(line.source).toMatch(/^From what you told Nura on /);
    }
    const said = await call<BiographyOut>("/profiles/p1/biography/read-back", {
      method: "POST",
      body: { line_id: bio.read_back[0]!.line_id, answer: "no" },
    });
    expect(said.read_back[0]!.answer).toBe("no");
    const again = await call<BiographyOut>("/profiles/p1/biography", { method: "POST", body: { language: "en", words: ["bp"], answers: {} } });
    expect(again.read_back[0]!.answer).toBe("no");
  });

  it("learns from a paper only once its card is confirmed, asking the live API which kind it was", async () => {
    await call("/profiles/p1/biography", { method: "POST", body: { language: "en", words: ["chol", "statin"], answers: {} } });
    await expect(
      call("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "card-1", language: "en" } }, live(reviewed("lab_report", false))),
    ).rejects.toBeInstanceOf(Refused);
    const bio = await call<BiographyOut>("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "card-1", language: "en" } });
    expect(asked.at(-1)).toBe("/profiles/p1/review-cards/card-1");
    expect(bio.papers).toHaveLength(1);
    expect(bio.papers[0]!.learned[0]).toBe("Your blood test is in your papers now.");
    expect(bio.questions.map((each) => each.question_id)).toEqual(["q-lab-old", "q-lab-statin"]);
    const twice = await call<BiographyOut>("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "card-1", language: "en" } });
    expect(twice.papers).toHaveLength(1);
  });

  it("closes the session with the closing prompt", async () => {
    await call("/profiles/p1/biography", { method: "POST", body: { language: "en", words: [], answers: {} } });
    const closed = await call<BiographyOut>("/profiles/p1/biography/close", { method: "POST" });
    expect(closed.closed_at).not.toBeNull();
    expect(closed.next_prompt?.kind).toBe("done");
  });

  it("sends a gap to the back on the first Later and retires it on the second", async () => {
    await call("/profiles/p1/biography", { method: "POST", body: { language: "en", words: ["bp", "bp_meds"], answers: {} } });
    const first = await call<PlanOut>("/profiles/p1/plan", { query: { language: "en" } });
    expect(first.cards[0]!.gap_id).toBe("meds");
    const once = await call<PlanOut>("/profiles/p1/plan/later", { method: "POST", body: { gap_id: "meds", language: "en" } });
    expect(once.cards[0]!.gap_id).not.toBe("meds");
    expect(once.cards.at(-1)!.gap_id).toBe("meds");
    const twice = await call<PlanOut>("/profiles/p1/plan/later", { method: "POST", body: { gap_id: "meds", language: "en" } });
    expect(twice.cards.map((each) => each.gap_id)).not.toContain("meds");
  });

  it("closes a gap as soon as a paper fills it", async () => {
    await call("/profiles/p1/biography", { method: "POST", body: { language: "en", words: ["bp_meds"], answers: {} } });
    await call("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "card-1" } }, live(reviewed("medicine_label")));
    const plan = await call<PlanOut>("/profiles/p1/plan", { query: { language: "en" } });
    expect(plan.cards.map((each) => each.gap_id)).not.toContain("meds");
  });
});

describe("nothing of onboarding is kept on the phone", () => {
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? files(path) : [path];
    });
  const root = new URL("../../src/", import.meta.url).pathname;
  const onboarding = [...files(join(root, "onboarding")), ...files(join(root, "api/mock")), ...files(join(root, "screens/onboarding"))];

  it("has no browser storage and no key-value store anywhere in the onboarding code", () => {
    expect(onboarding.length).toBeGreaterThan(10);
    for (const path of onboarding) {
      const code = readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
      expect(code, path).not.toMatch(/localStorage|sessionStorage|indexedDB|kvSet|kvGet|caches\./);
    }
  });
});

describe("the stand-in for the Ready screen's other actions", () => {
  const liveKeys = (keys: Partial<KeyOut>[]): Passthrough =>
    (<T,>(path: string) => Promise.resolve((path.endsWith("/keys") ? keys : reviewed("lab_report")) as unknown as T)) as Passthrough;

  it("names the word a tap gap reopens", async () => {
    await call("/profiles/p1/biography", { method: "POST", body: { language: "en", words: ["allergy", "drug_all", "thinner"], answers: {} } });
    const plan = await call<PlanOut>("/profiles/p1/plan", { query: { language: "en" } }, liveKeys([]));
    const byGap = new Map(plan.cards.map((each) => [each.gap_id, each]));
    expect(byGap.get("all")).toMatchObject({ capture: "tap", word: "drug_all" });
    expect(byGap.get("thin")).toMatchObject({ capture: "tap", word: "thinner" });
  });

  it("keeps the invite gap until someone holds a live key, asking the real API", async () => {
    await call("/profiles/p1/biography", { method: "POST", body: { language: "en", words: [], answers: {} } });
    const none = await call<PlanOut>("/profiles/p1/plan", {}, liveKeys([]));
    expect(none.cards.find((each) => each.gap_id === "fam")?.capture).toBe("invite");
    const revoked = await call<PlanOut>("/profiles/p1/plan", {}, liveKeys([{ key_id: "k", revoked_at: "2026-09-14T00:00:00Z" }]));
    expect(revoked.cards.map((each) => each.gap_id)).toContain("fam");
    const held = await call<PlanOut>("/profiles/p1/plan", {}, liveKeys([{ key_id: "k", revoked_at: null }]));
    expect(held.cards.map((each) => each.gap_id)).not.toContain("fam");
  });

  it("previews the sharing words from the live template and version, one line per part", async () => {
    const template: WordingOut = {
      purpose: "share_with_family",
      version: "2",
      language: "en",
      region: "SG",
      lines: ["You are letting {named} see some of your record.", "{name} can see these parts:", "{parts}", "You can stop this at any time."],
    };
    let asked = "";
    const wording = (<T,>(path: string, c: Call) => {
      asked = `${path}?${new URLSearchParams(c.query as Record<string, string>).toString()}`;
      return Promise.resolve(template as unknown as T);
    }) as Passthrough;
    const out = await call<SharingPreviewOut>(
      "/profiles/p1/consents/sharing/preview",
      { method: "POST", body: { holder_phone_e164: "+6591234567", scopes: ["medicines", "visits"], relationship: "daughter", language: "en" } },
      wording,
    );
    expect(asked).toBe("/consent/wording?purpose=share_with_family&language=en");
    expect(out.wording_version).toBe("2");
    expect(out.lines).toEqual([
      "You are letting +6591234567, your daughter, see some of your record.",
      "+6591234567 can see these parts:",
      "- your medicines",
      "- your visits to the doctor",
      "You can stop this at any time.",
    ]);
  });
});

describe("papers", () => {
  it("sends a PDF to /imports and anything else to /photos", () => {
    expect(isPdf({ type: "application/pdf", name: "letter" })).toBe(true);
    expect(isPdf({ type: "", name: "LETTER.PDF" })).toBe(true);
    expect(isPdf({ type: "image/jpeg", name: "label.jpg" })).toBe(false);
  });
});
