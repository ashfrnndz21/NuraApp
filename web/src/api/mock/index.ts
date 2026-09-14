import type { Call, Passthrough } from "../client";
import { Refused } from "../client";
import type {
  BiographyIn,
  BiographyOut,
  ConditionsOut,
  PaperOut,
  PlanCardOut,
  PlanOut,
  PromptOut,
  QuestionOut,
  ReadBackLineOut,
  ReviewCardOut,
  SettingsIn,
  SettingsOut,
} from "../types";
import { conditionWords, wordById } from "./graph";
import { ANSWERS, GAP_ACTION, GAP_MISSING, GAP_UNLOCK, LEARNED, PROMPTS, QUESTIONS, READ_BACK, SOURCES } from "./words";

/** The stand-in for E01's routes while that backend is built beside this client:
 *
 *    GET  /onboarding/conditions?language=         the word cloud's graph
 *    GET  /profiles/{id}/settings, PUT             about you
 *    POST /profiles/{id}/biography, GET            open it with the words he tapped
 *    POST /profiles/{id}/biography/read-back       yes or no to one line
 *    POST /profiles/{id}/biography/papers          a confirmed review card taken in
 *    POST /profiles/{id}/biography/questions       keep, or not, one question   (assumed)
 *    POST /profiles/{id}/biography/close           "That is all for today"
 *    GET  /profiles/{id}/plan?language=            the gap cards
 *    POST /profiles/{id}/plan/later                "Later" on one gap card      (assumed)
 *
 *  Installed only under `VITE_API_MOCK=1` (see `main.tsx`). Every other route — sign-in,
 *  doors, photos, review cards, confirmations — goes to the real API, and so does the one
 *  thing the mock needs to know that it cannot make up: what kind of paper a confirmed
 *  review card was (it asks `GET /review-cards/{id}` with the caller's own token).
 *
 *  Its pretend-server state lives in this module's memory for the tab and nowhere else:
 *  not IndexedDB, not sessionStorage, not localStorage. A reload starts it over. */

interface Store {
  settings: Map<string, SettingsOut>;
  biography: Map<string, BiographyOut>;
  deferred: Map<string, Record<string, number>>;
}

const store: Store = { settings: new Map(), biography: new Map(), deferred: new Map() };

/** Forget everything; the unit tests start each case clean. */
export function resetMock(): void {
  store.settings.clear();
  store.biography.clear();
  store.deferred.clear();
}

let counter = 0;
const id = (prefix: string) => `${prefix}-${++counter}`;
const STATE_ID = "state-mock-1";

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

function today(): string {
  return new Date().toLocaleDateString("en-SG", { weekday: "long", day: "numeric", month: "long" });
}

function dayAfter(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`;
}

const dated = (line: string) => line.replace("{date}", today());
const withDoctor = (lines: string[], doctor: string | null) =>
  lines.map((line) => line.replace("{doctor}", (doctor ?? "Tan").replace(/^Dr\.?\s+/i, "")));

function readBackFor(words: string[], answers: Record<string, string>, before: ReadBackLineOut[]): ReadBackLineOut[] {
  const known = new Map(before.map((line) => [line.line_id, line.answer]));
  const lines: ReadBackLineOut[] = [];
  const add = (line_id: string, text: string) =>
    lines.push({ line_id, text, answer: known.get(line_id) ?? null, state_id: STATE_ID, source: dated(SOURCES.told) });
  for (const word of words) {
    const text = READ_BACK[word];
    if (!text) continue;
    add(`rb-${word}`, text);
    const answer = answers[word];
    const line = answer ? ANSWERS[word]?.[answer] : undefined;
    if (answer && line) add(`rb-${word}-${answer}`, line);
  }
  return lines;
}

const prompt = (kind: PromptOut["kind"], lines: string[]): PromptOut => ({
  prompt_id: id("prompt"),
  kind,
  lines,
  state_id: STATE_ID,
  source: dated(SOURCES.told),
});

function questionsFor(bio: BiographyOut, doctor: string | null): QuestionOut[] {
  const kept = new Map(bio.questions.map((each) => [each.question_id, each.kept]));
  const out: QuestionOut[] = [];
  const add = (question_id: string, lines: string[], source: string) =>
    out.push({ question_id, lines: withDoctor(lines, doctor), kept: kept.get(question_id) ?? null, state_id: STATE_ID, source });
  const kinds = bio.papers.map((paper) => paper.document_kind);
  if (kinds.includes("lab_report")) add("q-lab-old", QUESTIONS.labOld, dated(SOURCES.paper));
  if (kinds.includes("lab_report") && bio.words.includes("statin")) add("q-lab-statin", QUESTIONS.labStatin, dated(SOURCES.paper));
  if (kinds.includes("medicine_label")) add("q-thinner", QUESTIONS.thinnerLabel, dated(SOURCES.paper));
  if (bio.words.includes("bp") && !bio.words.includes("bp_home")) add("q-bp-home", QUESTIONS.bpHome, dated(SOURCES.told));
  if (out.length === 0) add("q-no-papers", QUESTIONS.noPapers, dated(SOURCES.told));
  return out;
}

function gapsFor(bio: BiographyOut | undefined, deferred: Record<string, number>): PlanCardOut[] {
  const words = new Set(bio?.words ?? []);
  const answers = bio?.answers ?? {};
  const kinds = new Set((bio?.papers ?? []).map((paper) => paper.document_kind));
  const has = (...ids: string[]) => ids.some((each) => words.has(each));
  const wanted: [gap: string, tier: 1 | 2 | 3, when: boolean, capture: PlanCardOut["capture"]][] = [
    ["meds", 1, has("bp_meds", "statin", "sugar_tabs", "meds5", "thinner", "insulin") && !kinds.has("medicine_label"), "photo"],
    ["bpv", 1, has("bp") && (!has("bp_home") || answers.bp_home === "unsure"), "photo"],
    ["hfw", 1, has("hf") && !has("weigh"), "photo"],
    ["all", 1, has("drug_all") && !answers.drug_all, "tap"],
    ["thin", 1, has("thinner") && !answers.thinner, "tap"],
    ["dl", 1, has("hosp") && !kinds.has("discharge_letter"), "photo"],
    ["chol", 2, has("chol") && !kinds.has("lab_report"), "photo"],
    ["sug", 2, has("sugar") && !kinds.has("lab_report"), "photo"],
    ["kid", 2, has("kidney", "kidney_chk") && !kinds.has("lab_report"), "photo"],
    ["doc", 2, has("heart_doc", "heart", "bp") && !kinds.has("clinic_slip"), "photo"],
    ["ins", 2, true, "photo"],
    ["fam", 3, true, "none"],
  ];
  // docs/gaps-and-unlocks.md §4: a Later sends a gap to the back once; a second retires it.
  const open = wanted.filter(([gap, , when]) => when && (deferred[gap] ?? 0) < 2);
  const ranked = [
    ...open.filter(([gap]) => !deferred[gap]).sort((a, b) => a[1] - b[1]),
    ...open.filter(([gap]) => deferred[gap]),
  ];
  return ranked.map(([gap, tier, , capture], position) => ({
    gap_id: gap,
    day: dayAfter(position + 1),
    tier,
    missing: GAP_MISSING[gap]!,
    unlock: GAP_UNLOCK[gap]!,
    action: GAP_ACTION[gap]!,
    capture,
    state_id: STATE_ID,
    source: dated(SOURCES.plan),
    deferred: deferred[gap] ?? 0,
  }));
}

const PROFILE_ROUTE = /^\/profiles\/([^/]+)\/(settings|biography|plan)(\/[a-z-]+)?$/;

const bodyOf = <T>(call: Call): T => (call.body ?? {}) as T;
const answer = <T>(value: T): Promise<T> => Promise.resolve(clone(value));

async function takePaper(bio: BiographyOut, profileId: string, call: Call, passthrough: Passthrough, doctor: string | null) {
  const { card_id } = bodyOf<{ card_id: string }>(call);
  const card = await passthrough<ReviewCardOut>(`/profiles/${profileId}/review-cards/${card_id}`, { token: call.token ?? null });
  if (card.confirmed_at === null) throw new Refused("NotConfirmedYet", 409);
  const lines = LEARNED[card.document_kind];
  if (!lines) {
    bio.next_prompt = prompt("paper", PROMPTS.unread);
  } else if (!bio.papers.some((paper) => paper.card_id === card.card_id)) {
    const paper: PaperOut = {
      paper_id: id("paper"),
      card_id: card.card_id,
      artifact_id: card.artifact_id,
      document_kind: card.document_kind,
      learned: lines,
      source: dated(SOURCES.paper),
    };
    bio.papers.push(paper);
    bio.next_prompt = prompt("paper", PROMPTS.next);
  }
  bio.questions = questionsFor(bio, doctor);
}

/** The transport: a Promise for the paths the mock knows, `undefined` for everything else. */
export function mockTransport(path: string, call: Call, passthrough: Passthrough): Promise<unknown> | undefined {
  const method = call.method ?? "GET";
  if (path === "/onboarding/conditions" && method === "GET") {
    const conditions: ConditionsOut = { language: call.query?.language ?? "en", version: "mock-1", words: conditionWords() };
    return answer(conditions);
  }
  const match = PROFILE_ROUTE.exec(path);
  if (!match) return undefined;
  const profileId = match[1]!;
  const resource = match[2]!;
  const tail = match[3];
  const doctor = store.settings.get(profileId)?.doctor ?? null;

  if (resource === "settings" && !tail) {
    if (method === "GET") {
      const saved = store.settings.get(profileId);
      if (saved) return answer(saved);
      const blank: SettingsOut = {
        profile_id: profileId,
        preferred_name: null,
        language: call.query?.language ?? "en",
        birth_decade: null,
        doctor: null,
        breakfast_time: null,
        sight: false,
        hearing: false,
        hands: false,
        cognitive: false,
        updated_at: null,
      };
      return answer(blank);
    }
    if (method !== "PUT") return undefined;
    const saved: SettingsOut = { ...bodyOf<SettingsIn>(call), profile_id: profileId, updated_at: new Date().toISOString() };
    store.settings.set(profileId, saved);
    return answer(saved);
  }

  if (resource === "plan") {
    const deferred = store.deferred.get(profileId) ?? {};
    if (tail === "/later" && method === "POST") {
      const { gap_id } = bodyOf<{ gap_id: string }>(call);
      deferred[gap_id] = (deferred[gap_id] ?? 0) + 1;
      store.deferred.set(profileId, deferred);
    } else if (tail || method !== "GET") {
      return undefined;
    }
    const plan: PlanOut = { profile_id: profileId, state_id: STATE_ID, cards: gapsFor(store.biography.get(profileId), deferred) };
    return answer(plan);
  }

  // The biography; any other tail on settings is not the mock's, and goes to the real API.
  if (resource !== "biography") return undefined;
  const current = store.biography.get(profileId);
  if (!tail && method === "GET") return current ? answer(current) : Promise.reject(new Refused("NoBiographyYet", 404));
  if (!tail && method === "POST") {
    const told = bodyOf<BiographyIn>(call);
    const words = told.words.filter((each) => wordById(each));
    const bio: BiographyOut = {
      biography_id: current?.biography_id ?? id("biography"),
      profile_id: profileId,
      language: told.language,
      opened_at: current?.opened_at ?? new Date().toISOString(),
      closed_at: null,
      words,
      answers: told.answers,
      read_back: readBackFor(words, told.answers, current?.read_back ?? []),
      next_prompt: current?.next_prompt ?? prompt("paper", PROMPTS.first),
      papers: current?.papers ?? [],
      questions: [],
    };
    bio.questions = questionsFor(bio, doctor);
    store.biography.set(profileId, bio);
    return answer(bio);
  }
  if (method !== "POST" || !tail) return undefined;
  if (!current) return Promise.reject(new Refused("NoBiographyYet", 404));
  const settle = async (): Promise<BiographyOut> => {
    if (tail === "/read-back") {
      const { line_id, answer: said } = bodyOf<{ line_id: string; answer: "yes" | "no" }>(call);
      const line = current.read_back.find((each) => each.line_id === line_id);
      if (!line) throw new Refused("NoSuchLine", 404);
      line.answer = said;
    } else if (tail === "/papers") {
      await takePaper(current, profileId, call, passthrough, doctor);
    } else if (tail === "/questions") {
      const { question_id, keep } = bodyOf<{ question_id: string; keep: boolean }>(call);
      const question = current.questions.find((each) => each.question_id === question_id);
      if (!question) throw new Refused("NoSuchQuestion", 404);
      question.kept = keep;
    } else if (tail === "/close") {
      current.closed_at = new Date().toISOString();
      current.next_prompt = prompt("done", PROMPTS.done);
    } else {
      throw new Refused("HttpError", 404);
    }
    store.biography.set(profileId, current);
    return clone(current);
  };
  return settle();
}
