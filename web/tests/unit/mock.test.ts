import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import type { Call, Passthrough } from "../../src/api/client";
import { Refused } from "../../src/api/client";
import type { BiographyOut, ClosedOut, ConditionsOut, KeyOut, PaperAddedOut, PlanOut, ReviewCardOut, SettingsIn, SettingsOut } from "../../src/api/types";
import { mockTransport, resetMock } from "../../src/api/mock";
import { isPdf } from "../../src/onboarding/actions";

/** The stand-in for #117 keeps #117's contract ("Client contract"): its shapes, its steps, its
 *  refusals. What it cannot make up — a card's kind and whether it is confirmed, whether
 *  anyone holds a key — it asks the live API, faked here. */

const live = { cards: new Map<string, ReviewCardOut>(), keys: [] as Partial<KeyOut>[] };
const asked: string[] = [];
const passthrough = (<T,>(path: string) => {
  asked.push(path);
  const found = /\/review-cards\/([^/]+)$/.exec(path);
  if (found) {
    const card = live.cards.get(found[1]!);
    return card ? Promise.resolve(card as unknown as T) : Promise.reject(new Refused("NoSuchReviewCard", 404));
  }
  if (path.endsWith("/keys")) return Promise.resolve(live.keys as unknown as T);
  return Promise.reject(new Error(`the mock asked the live API for ${path}`));
}) as Passthrough;

const card = (card_id: string, kind: ReviewCardOut["document_kind"], confirmed: boolean): ReviewCardOut => ({
  card_id,
  profile_id: "p1",
  artifact_id: `art-${card_id}`,
  document_kind: kind,
  document_date: null,
  asked_as: null,
  source: null,
  notice: null,
  high_risk_class: null,
  created_at: "2026-09-14T02:00:00Z",
  confirmed_at: confirmed ? "2026-09-14T02:05:00Z" : null,
  fields: [],
});

function call<T>(path: string, init: Call = {}): Promise<T> {
  const answer = mockTransport(path, { token: "t", ...init }, passthrough);
  if (!answer) throw new Error(`the mock does not answer ${path}`);
  return answer as Promise<T>;
}

const settings = (over: Partial<SettingsIn> = {}): SettingsIn => ({
  language: "en",
  conditions: ["high_blood_pressure", "cholesterol"],
  density: "detailed",
  large_text: false,
  high_contrast: false,
  voice_on: false,
  big_targets: false,
  one_thing_per_screen: false,
  read_back: false,
  repeat_prompts: false,
  preferred_name: "Pa",
  doctor_name: "Dr Tan",
  breakfast_time: "07:30",
  birth_decade: 1950,
  ...over,
});

async function refusal(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (failure) {
    if (failure instanceof Refused) return `${failure.refusal} ${failure.status}`;
    throw failure;
  }
  throw new Error("expected a refusal");
}

/** A sitting with settings saved and the lipid report joined and confirmed: at the read-back. */
async function atReadBack(): Promise<BiographyOut> {
  await call("/profiles/p1/biography", { method: "POST" });
  await call("/profiles/p1/settings", { method: "PUT", body: settings() });
  live.cards.set("c1", card("c1", "lab_report", true));
  await call("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "c1" } });
  return call<BiographyOut>("/profiles/p1/biography");
}

async function answerAll(bio: BiographyOut): Promise<BiographyOut> {
  let current = bio;
  for (const line of bio.read_back) current = await call<BiographyOut>("/profiles/p1/biography/read-back", { method: "POST", body: { line_id: line.fact_id, answer: "yes" } });
  return current;
}

beforeEach(() => {
  resetMock();
  live.cards.clear();
  live.keys = [];
  asked.length = 0;
});

describe("the #117 stand-in", () => {
  it("leaves every route it does not own to the real API", () => {
    for (const [path, method] of [
      ["/auth/phone/start", "POST"],
      ["/profiles/p1/photos", "POST"],
      ["/profiles/p1/confirmations", "POST"],
      ["/profiles/p1/medicines", "GET"],
      ["/profiles/p1/consents/sharing/preview", "POST"],
      ["/profiles/p1/settings/anything", "POST"],
      ["/profiles/p1/plan/medicines/skip", "POST"],
    ] as const) {
      expect(mockTransport(path, { method }, passthrough), path).toBeUndefined();
    }
  });

  it("answers the word cloud with E01's own graph, in #117's shape", async () => {
    const cloud = await call<ConditionsOut>("/onboarding/conditions", { query: { language: "en" } });
    expect(cloud.version).toBe(1);
    expect(cloud.top).toHaveLength(20);
    expect(cloud.conditions.find((each) => each.code === "high_blood_pressure")).toMatchObject({ name: "High blood pressure", weight: 3, top: true });
  });

  it("keeps the settings it was given, with the words he tapped, and refuses a year that is not a decade", async () => {
    const blank = await call<SettingsOut>("/profiles/p1/settings");
    expect(blank.settings_id).toBeNull();
    await call("/profiles/p1/settings", { method: "PUT", body: settings({ large_text: true }) });
    const held = await call<SettingsOut>("/profiles/p1/settings");
    expect([held.conditions, held.large_text, held.doctor_name]).toEqual([["high_blood_pressure", "cholesterol"], true, "Dr Tan"]);
    expect(await refusal(call("/profiles/p1/settings", { method: "PUT", body: settings({ birth_decade: 1955 }) }))).toBe("NotADecade 400");
  });

  it("walks the sitting's steps as #117 does", async () => {
    expect(await refusal(call("/profiles/p1/biography"))).toBe("NoBiography 404");
    const opened = await call<BiographyOut>("/profiles/p1/biography", { method: "POST" });
    expect([opened.step, opened.next, opened.prompt.headline]).toEqual(["about_you", "save_settings", "A few things about you"]);
    expect(await refusal(call("/profiles/p1/biography", { method: "POST" }))).toBe("BiographyAlreadyOpen 409");

    await call("/profiles/p1/settings", { method: "PUT", body: settings() });
    const papers = await call<BiographyOut>("/profiles/p1/biography");
    expect([papers.step, papers.next]).toEqual(["papers", "add_paper"]);
    expect(await refusal(call("/profiles/p1/biography/read-back", { method: "POST", body: { line_id: "x", answer: "yes" } }))).toBe("NotAtThisStep 409");

    live.cards.set("c1", card("c1", "lab_report", false));
    const added = await call<PaperAddedOut>("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "c1" } });
    expect([added.paper.paper, added.paper.confirmed, added.card.card_id]).toEqual(["lab_result", false, "c1"]);
    expect(asked).toContain("/profiles/p1/review-cards/c1");
    const waiting = await call<BiographyOut>("/profiles/p1/biography");
    expect([waiting.step, waiting.next, waiting.open_cards]).toEqual(["papers", "confirm_cards", 1]);
    expect(await refusal(call("/profiles/p1/biography/read-back", { method: "POST", body: { line_id: "x", answer: "yes" } }))).toBe("CardsStillOpen 409");
    expect(await refusal(call("/profiles/p1/biography/papers", { method: "POST", body: { card_id: "c1" } }))).toBe("PaperAlreadyAdded 409");

    live.cards.set("c1", card("c1", "lab_report", true));
    const ready = await call<BiographyOut>("/profiles/p1/biography");
    expect(ready.step).toBe("read_back");
    expect(ready.read_back.map((line) => line.line)).toEqual([
      "You told us: High blood pressure.",
      "You told us: High cholesterol.",
      "Your blood test is in your papers now.",
    ]);
  });

  it("reads back one line at a time, and after a no says who looks at the paper again", async () => {
    const bio = await atReadBack();
    const first = bio.read_back[0]!;
    const second = bio.read_back[1]!;
    const yes = await call<BiographyOut>("/profiles/p1/biography/read-back", { method: "POST", body: { line_id: first.fact_id, answer: "yes" } });
    expect(yes.read_back[0]!.answer).toBe("yes");
    expect(yes.after_no).toBeNull();
    const no = await call<BiographyOut>("/profiles/p1/biography/read-back", { method: "POST", body: { line_id: second.fact_id, answer: "no" } });
    expect(no.read_back[1]!.dispute_fact_id).toBeTruthy();
    expect(no.after_no).toContain("Dr Tan");
    expect(await refusal(call("/profiles/p1/biography/read-back", { method: "POST", body: { line_id: first.fact_id, answer: "no" } }))).toBe("NoSuchReadBackLine 404");
    const done = await answerAll(no);
    expect(done.step).toBe("questions");
    expect(done.read_back_at).not.toBeNull();
  });

  it("asks four questions at most from the gaps still open, and says how many more wait", async () => {
    expect(await refusal(call("/profiles/p1/biography/questions", { method: "POST", body: { question_id: "medicines", keep: true } }))).toMatch(/NoBiography|NotAtThisStep/);
    const bio = await answerAll(await atReadBack());
    expect(bio.questions).toHaveLength(4);
    expect(bio.questions[0]).toMatchObject({ question_id: "medicines", kept: null });
    expect(bio.questions[0]!.line).toContain("Dr Tan");
    expect(bio.more).toBe("2 more can wait for later.");
    const kept = await call<BiographyOut>("/profiles/p1/biography/questions", { method: "POST", body: { question_id: "medicines", keep: true } });
    expect(kept.questions[0]!.kept).toBe(true);
    expect(await refusal(call("/profiles/p1/biography/questions", { method: "POST", body: { question_id: "nope", keep: true } }))).toBe("NoSuchQuestion 404");
  });

  it("closes with the summary in his words and the first week, due at his breakfast", async () => {
    expect(await refusal(call("/profiles/p1/plan"))).toBe("NoPlan 404");
    await answerAll(await atReadBack());
    const closed = await call<ClosedOut>("/profiles/p1/biography/close", { method: "POST" });
    expect([closed.biography.step, closed.biography.prompt.headline]).toEqual(["closed", "Your app is ready"]);
    expect(closed.summary.lines[0]).toBe("Nura saved one of your papers.");
    const first = closed.plan.prompts[0]!;
    expect(first).toMatchObject({ prompt: "medicines", capture: "photo", status: "pending", day: 1 });
    expect(first.due_local).toMatch(/T07:30:00\+08:00$/);
    expect(first.headline && first.line && first.action).toBeTruthy();
    expect(closed.plan.prompts.map((each) => each.prompt)).not.toContain("cholesterol_result");
    const again = await call<PlanOut>("/profiles/p1/plan");
    expect(again.prompts.map((each) => each.prompt)).toEqual(closed.plan.prompts.map((each) => each.prompt));
  });

  it("closes with no papers at all, straight after the settings", async () => {
    await call("/profiles/p1/biography", { method: "POST" });
    await call("/profiles/p1/settings", { method: "PUT", body: settings() });
    const closed = await call<ClosedOut>("/profiles/p1/biography/close", { method: "POST" });
    expect(closed.summary.lines).toEqual(["No papers were added this time."]);
  });

  it("sends a prompt to the back of the week on the first Later and retires it on the second", async () => {
    await answerAll(await atReadBack());
    await call("/profiles/p1/biography/close", { method: "POST" });
    const once = await call<PlanOut>("/profiles/p1/plan/later", { method: "POST", body: { gap_id: "medicines" } });
    expect(once.prompts.at(-1)).toMatchObject({ prompt: "medicines", deferred: 1, status: "pending" });
    const twice = await call<PlanOut>("/profiles/p1/plan/later", { method: "POST", body: { gap_id: "medicines" } });
    expect(twice.prompts.find((each) => each.prompt === "medicines")?.status).toBe("skipped");
    expect(await refusal(call("/profiles/p1/plan/later", { method: "POST", body: { gap_id: "nope" } }))).toBe("NoSuchPrompt 404");
  });

  it("marks the invite done once anyone holds a live key, asking the real API", async () => {
    await answerAll(await atReadBack());
    const closed = await call<ClosedOut>("/profiles/p1/biography/close", { method: "POST" });
    expect(closed.plan.prompts.find((each) => each.prompt === "someone_to_see")).toMatchObject({ capture: "invite", status: "pending" });
    live.keys = [{ key_id: "k", revoked_at: "2026-09-14T00:00:00Z" }];
    expect((await call<PlanOut>("/profiles/p1/plan")).prompts.find((each) => each.prompt === "someone_to_see")?.status).toBe("pending");
    live.keys = [{ key_id: "k", revoked_at: null }];
    expect((await call<PlanOut>("/profiles/p1/plan")).prompts.find((each) => each.prompt === "someone_to_see")?.status).toBe("done");
  });
});

describe("papers", () => {
  it("sends a PDF to /imports and anything else to /photos", () => {
    expect(isPdf({ type: "application/pdf", name: "letter" })).toBe(true);
    expect(isPdf({ type: "", name: "LETTER.PDF" })).toBe(true);
    expect(isPdf({ type: "image/jpeg", name: "label.jpg" })).toBe(false);
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
