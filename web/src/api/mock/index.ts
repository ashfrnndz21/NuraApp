import type { Call, Passthrough } from "../client";
import { Refused } from "../client";
import type {
  BiographyOut,
  BiographyStep,
  ClosedOut,
  ConditionsOut,
  KeyOut,
  ReadBackLineOut,
  PaperAddedOut,
  PaperKind,
  PaperOut,
  PlanOut,
  PromptOut,
  QuestionOut,
  ReviewCardOut,
  SettingsIn,
  SettingsOut,
} from "../types";
import { conditionWords, TOP, VERSION, wordByCode } from "./graph";
import { AFTER_NO, GAP_ACTION, GAP_HEADLINE, GAP_LINE, MORE, PAPER_LINE, QUESTION, STEP_HEADLINE, STEP_LINES, SUMMARY, TOLD } from "./words";

/** The stand-in for #117 (E01) in dev and in tests, in #117's own shapes ("Client contract"):
 *
 *    GET  /onboarding/conditions?language=
 *    GET  /profiles/{id}/settings, PUT
 *    POST /profiles/{id}/biography (no body), GET
 *    POST /profiles/{id}/biography/papers         {card_id}
 *    POST /profiles/{id}/biography/read-back      {line_id, answer} or {answers}
 *    POST /profiles/{id}/biography/questions      {question_id, keep}
 *    POST /profiles/{id}/biography/close
 *    GET  /profiles/{id}/plan, POST /profiles/{id}/plan/later {gap_id}
 *
 *  Installed only under `VITE_API_MOCK=1` (`main.tsx`). Every other route goes to the real API,
 *  and so do the two things the mock cannot make up: a card's kind and whether it is confirmed
 *  (`GET /review-cards/{id}`), and whether anyone holds a key (`GET /keys`). Its state lives in
 *  this module's memory for the tab — not IndexedDB, not web storage. */

interface Paper {
  paper_id: string;
  position: number;
  paper: PaperKind;
  artifact_id: string;
  card_id: string;
  document_kind: string;
}

interface Sitting {
  id: string;
  opened_at: string;
  read_back_at: string | null;
  closed_at: string | null;
  papers: Paper[];
  answers: Record<string, "yes" | "no">;
  kept: Record<string, boolean>;
}

interface Week {
  plan_id: string;
  created_at: string;
  first_day: string;
  order: string[];
  deferred: Record<string, number>;
}

const store = {
  settings: new Map<string, SettingsOut>(),
  sitting: new Map<string, Sitting>(),
  week: new Map<string, Week>(),
};

/** Forget everything; the unit tests start each case clean. */
export function resetMock(): void {
  store.settings.clear();
  store.sitting.clear();
  store.week.clear();
}

let counter = 0;
const id = (prefix: string) => `${prefix}-${++counter}`;
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const bodyOf = <T>(call: Call): T => (call.body ?? {}) as T;
const now = () => new Date().toISOString();

/** A day on Singapore's calendar, `offset` days from today by the phone's clock. */
function sgDay(offset: number): string {
  return new Date(Date.now() + 8 * 3_600_000 + offset * 86_400_000).toISOString().slice(0, 10);
}

function addDays(day: string, count: number): string {
  const when = new Date(`${day}T00:00:00Z`);
  when.setUTCDate(when.getUTCDate() + count);
  return when.toISOString().slice(0, 10);
}

const KIND_TO_PAPER: Record<string, PaperKind> = {
  lab_report: "lab_result",
  medicine_label: "medicine",
  discharge_letter: "discharge_letter",
  clinic_slip: "clinic_card",
  insurance_letter: "insurance_card",
};

/** #117's gap catalogue (`backend/app/onboarding/gaps.py`): each gap, its tier, how it is
 *  filled and the words of the cloud it is about. */
const GAPS: [gap: string, tier: number, capture: PromptOut["capture"], words: readonly string[]][] = [
  ["medicines", 1, "photo", []],
  ["bp_numbers", 1, "photo", ["high_blood_pressure", "bp_tablets", "bp_at_home"]],
  ["weight", 1, "photo", ["weak_heart", "weigh_myself", "water_pill"]],
  ["allergy_which", 1, "tap", ["medicine_allergy", "allergies"]],
  ["thinner_which", 1, "photo", ["blood_thinner"]],
  ["discharge_letter", 1, "photo", ["hospital_last_year", "have_hospital_letter"]],
  ["cholesterol_result", 2, "pdf", ["cholesterol", "cholesterol_tablet"]],
  ["sugar_result", 2, "pdf", ["diabetes", "sugar_tablets", "insulin", "sugar_at_home"]],
  ["kidney_result", 2, "pdf", ["kidneys", "kidney_watched", "dialysis"]],
  ["next_visit", 2, "photo", []],
  ["last_visit", 2, "photo", []],
  ["insurance", 2, "photo", []],
  ["meal_times", 2, "tap", []],
  ["someone_to_see", 3, "invite", []],
];

/** The gaps still open, in tier order: the mock's stand-in for #117's rules. */
function openGaps(conditions: readonly string[], kinds: ReadonlySet<string>, breakfast: boolean, someoneIn: boolean): string[] {
  const has = (...codes: string[]) => codes.some((code) => conditions.includes(code));
  const any = conditions.length > 0;
  const wanted: Record<string, boolean> = {
    medicines: !kinds.has("medicine_label"),
    bp_numbers: has("high_blood_pressure", "bp_tablets", "bp_at_home") && !kinds.has("device_screen"),
    weight: has("weak_heart", "weigh_myself", "water_pill") && !kinds.has("device_screen"),
    allergy_which: has("allergies") && !has("medicine_allergy"),
    thinner_which: has("blood_thinner") && !kinds.has("medicine_label"),
    discharge_letter: has("hospital_last_year", "have_hospital_letter") && !kinds.has("discharge_letter"),
    cholesterol_result: has("cholesterol", "cholesterol_tablet") && !kinds.has("lab_report"),
    sugar_result: has("diabetes", "sugar_tablets", "insulin", "sugar_at_home") && !kinds.has("lab_report"),
    kidney_result: has("kidneys", "kidney_watched", "dialysis") && !kinds.has("lab_report"),
    next_visit: any && !kinds.has("clinic_slip"),
    last_visit: any && !kinds.has("clinic_slip"),
    insurance: !kinds.has("insurance_letter"),
    meal_times: !breakfast,
    someone_to_see: !someoneIn,
  };
  return GAPS.map(([gap]) => gap).filter((gap) => wanted[gap]);
}

async function cardsOf(profileId: string, sitting: Sitting | undefined, call: Call, passthrough: Passthrough): Promise<(ReviewCardOut | null)[]> {
  return Promise.all(
    (sitting?.papers ?? []).map((paper) =>
      passthrough<ReviewCardOut>(`/profiles/${profileId}/review-cards/${paper.card_id}`, { token: call.token ?? null }).catch(() => null),
    ),
  );
}

async function someoneIn(profileId: string, call: Call, passthrough: Passthrough): Promise<boolean> {
  const keys = await passthrough<KeyOut[]>(`/profiles/${profileId}/keys`, { token: call.token ?? null }).catch(() => [] as KeyOut[]);
  return Array.isArray(keys) && keys.some((key) => key.revoked_at === null);
}

const doctorOf = (saved: SettingsOut | null) => (saved?.doctor_name ?? "Tan").replace(/^Dr\.?\s+/i, "");

function readBackLines(sitting: Sitting, saved: SettingsOut | null, papers: PaperOut[]): ReadBackLineOut[] {
  const out: ReadBackLineOut[] = [];
  const line = (fact_id: string, text: string) => {
    const answer = sitting.answers[fact_id] ?? null;
    out.push({ fact_id, line: text, answer, dispute_fact_id: answer === "no" ? `dispute-${fact_id}` : null });
  };
  for (const code of saved?.conditions ?? []) {
    const word = wordByCode(code);
    if (word) line(`fact-told-${code}`, TOLD.replace("{condition}", word.name));
  }
  for (const paper of papers) if (paper.confirmed) line(`fact-paper-${paper.card_id}`, PAPER_LINE[paper.document_kind] ?? PAPER_LINE.other!);
  return out;
}

async function view(profileId: string, call: Call, passthrough: Passthrough): Promise<BiographyOut> {
  const sitting = store.sitting.get(profileId)!;
  const saved = store.settings.get(profileId) ?? null;
  const cards = await cardsOf(profileId, sitting, call, passthrough);
  const papers: PaperOut[] = sitting.papers.map((paper, index) => ({ ...paper, confirmed: Boolean(cards[index]?.confirmed_at) }));
  const open = papers.filter((paper) => !paper.confirmed).length;
  const step: BiographyStep = sitting.closed_at
    ? "closed"
    : sitting.read_back_at
      ? "questions"
      : !saved
        ? "about_you"
        : papers.length > 0 && open === 0
          ? "read_back"
          : "papers";
  const next = { about_you: "save_settings", papers: open ? "confirm_cards" : "add_paper", read_back: "read_back", questions: "close", closed: null }[step];
  const lines = step === "about_you" || open > 0 ? [] : readBackLines(sitting, saved, papers);
  let questions: QuestionOut[] = [];
  let more: string | null = null;
  if (step === "questions" || step === "closed") {
    const kinds = new Set(papers.filter((paper) => paper.confirmed).map((paper) => paper.document_kind));
    const gaps = openGaps(saved?.conditions ?? [], kinds, Boolean(saved?.breakfast_time), await someoneIn(profileId, call, passthrough));
    questions = gaps.slice(0, 4).map((gap) => ({ question_id: gap, line: QUESTION[gap]!.replace("{doctor}", doctorOf(saved)), kept: sitting.kept[gap] ?? null }));
    more = gaps.length > 4 ? MORE.replace("{count}", String(gaps.length - 4)) : null;
  }
  return {
    biography_id: sitting.id,
    profile_id: profileId,
    step,
    next,
    language: call.query?.language ?? saved?.language ?? "en",
    opened_at: sitting.opened_at,
    opened_by_person_id: "mock-person",
    read_back_at: sitting.read_back_at,
    closed_at: sitting.closed_at,
    prompt: { headline: STEP_HEADLINE[step]!, lines: STEP_LINES[step]! },
    papers,
    open_cards: open,
    read_back: lines,
    questions,
    after_no: Object.values(sitting.answers).includes("no") ? AFTER_NO.replace("{doctor}", doctorOf(saved)) : null,
    more,
  };
}

async function planOut(profileId: string, call: Call, passthrough: Passthrough): Promise<PlanOut> {
  const week = store.week.get(profileId);
  if (!week) throw new Refused("NoPlan", 404);
  const sitting = store.sitting.get(profileId);
  const saved = store.settings.get(profileId) ?? null;
  const cards = await cardsOf(profileId, sitting, call, passthrough);
  const kinds = new Set((sitting?.papers ?? []).filter((_, index) => cards[index]?.confirmed_at).map((paper) => paper.document_kind));
  const open = new Set(openGaps(saved?.conditions ?? [], kinds, Boolean(saved?.breakfast_time), await someoneIn(profileId, call, passthrough)));
  const breakfast = saved?.breakfast_time ?? "09:00";
  const order = [...week.order.filter((gap) => !week.deferred[gap]), ...week.order.filter((gap) => week.deferred[gap])];
  const byGap = new Map(GAPS.map((entry) => [entry[0], entry]));
  const prompts: PromptOut[] = order.map((gap, index) => {
    const [, tier, capture, words] = byGap.get(gap)!;
    const local = `${addDays(week.first_day, index)}T${breakfast}:00+08:00`;
    const retired = (week.deferred[gap] ?? 0) >= 2;
    const done = !open.has(gap);
    return {
      prompt: gap,
      day: index + 1,
      tier,
      capture,
      word: words[0] ? (wordByCode(words[0])?.name ?? null) : null,
      deferred: week.deferred[gap] ?? 0,
      due_at: new Date(local).toISOString(),
      due_local: local,
      status: retired ? "skipped" : done ? "done" : "pending",
      done_at: done && !retired ? now() : null,
      done_by_fact_id: null,
      skipped_at: retired ? now() : null,
      headline: GAP_HEADLINE[gap] ?? null,
      line: GAP_LINE[gap] ?? null,
      action: GAP_ACTION[gap] ?? null,
    };
  });
  const pendingOnes = prompts.filter((prompt) => prompt.status === "pending");
  return {
    plan_id: week.plan_id,
    profile_id: profileId,
    biography_id: sitting?.id ?? null,
    created_at: week.created_at,
    first_day: week.first_day,
    breakfast_time: breakfast,
    timezone: "Asia/Singapore",
    stopped: pendingOnes.length === 0,
    stopped_because: [],
    prompts,
    due: pendingOnes.slice(0, 1),
  };
}

function defaults(profileId: string, language: string): SettingsOut {
  return {
    settings_id: null,
    profile_id: profileId,
    language,
    conditions: [],
    density: "detailed",
    large_text: false,
    high_contrast: false,
    voice_on: false,
    big_targets: false,
    one_thing_per_screen: false,
    read_back: false,
    repeat_prompts: false,
    preferred_name: null,
    doctor_name: null,
    breakfast_time: null,
    birth_decade: null,
    set_by_person_id: null,
    set_at: null,
    withheld: [],
  };
}

const PROFILE_ROUTE = /^\/profiles\/([^/]+)\/(settings|biography|plan)(\/[a-z-]+)?$/;
const SITTING_TAILS = [undefined, "/papers", "/read-back", "/questions", "/close"];

async function sittingRoute(profileId: string, method: string, tail: string | undefined, call: Call, passthrough: Passthrough): Promise<unknown> {
  const current = store.sitting.get(profileId);
  if (!tail && method === "GET") {
    if (!current) throw new Refused("NoBiography", 404);
    return view(profileId, call, passthrough);
  }
  if (!tail && method === "POST") {
    if (current && !current.closed_at) throw new Refused("BiographyAlreadyOpen", 409);
    store.sitting.set(profileId, { id: id("biography"), opened_at: now(), read_back_at: null, closed_at: null, papers: [], answers: {}, kept: {} });
    return view(profileId, call, passthrough);
  }
  if (!current) throw new Refused("NoBiography", 404);
  if (tail === "/papers") {
    if (current.closed_at) throw new Refused("BiographyClosed", 409);
    const { card_id, paper } = bodyOf<{ card_id: string; paper?: PaperKind }>(call);
    if (current.papers.some((each) => each.card_id === card_id)) throw new Refused("PaperAlreadyAdded", 409);
    const card = await passthrough<ReviewCardOut>(`/profiles/${profileId}/review-cards/${card_id}`, { token: call.token ?? null });
    const joined: Paper = {
      paper_id: id("paper"),
      position: current.papers.length + 1,
      paper: paper ?? KIND_TO_PAPER[card.document_kind] ?? "other",
      artifact_id: card.artifact_id,
      card_id,
      document_kind: card.document_kind,
    };
    current.papers.push(joined);
    const added: PaperAddedOut = { paper: { ...joined, confirmed: card.confirmed_at !== null }, card };
    return added;
  }
  if (tail === "/read-back") {
    const before = await view(profileId, call, passthrough);
    if (before.step === "about_you") throw new Refused("NotAtThisStep", 409);
    if (before.open_cards > 0) throw new Refused("CardsStillOpen", 409);
    if (before.step === "questions" || before.step === "closed") throw new Refused("AlreadyReadBack", 409);
    if (before.step !== "read_back") throw new Refused("NotAtThisStep", 409);
    const said = bodyOf<{ answers?: { fact_id: string; answer: "yes" | "no" }[]; line_id?: string; answer?: "yes" | "no" }>(call);
    const given = said.answers ?? (said.line_id && said.answer ? [{ fact_id: said.line_id, answer: said.answer }] : []);
    for (const each of given) {
      const line = before.read_back.find((candidate) => candidate.fact_id === each.fact_id);
      if (!line || line.answer !== null) throw new Refused("NoSuchReadBackLine", 404);
      current.answers[each.fact_id] = each.answer;
    }
    if (before.read_back.every((line) => current.answers[line.fact_id])) current.read_back_at = now();
    return view(profileId, call, passthrough);
  }
  if (tail === "/questions") {
    const before = await view(profileId, call, passthrough);
    if (before.step !== "questions") throw new Refused("NotAtThisStep", 409);
    const { question_id, keep } = bodyOf<{ question_id: string; keep: boolean }>(call);
    if (!before.questions.some((question) => question.question_id === question_id)) throw new Refused("NoSuchQuestion", 404);
    current.kept[question_id] = keep;
    return view(profileId, call, passthrough);
  }
  // tail === "/close"
  const saved = store.settings.get(profileId) ?? null;
  if (!saved) throw new Refused("NotAtThisStep", 409);
  if (current.closed_at) throw new Refused("BiographyClosed", 409);
  const cards = await cardsOf(profileId, current, call, passthrough);
  if (cards.some((card) => !card?.confirmed_at)) throw new Refused("CardsStillOpen", 409);
  current.closed_at = now();
  const kinds = new Set(current.papers.map((paper) => paper.document_kind));
  store.week.set(profileId, {
    plan_id: id("plan"),
    created_at: now(),
    first_day: sgDay(1),
    order: openGaps(saved.conditions ?? [], kinds, Boolean(saved.breakfast_time), await someoneIn(profileId, call, passthrough)),
    deferred: {},
  });
  const confirmedFacts = cards.reduce((sum, card) => sum + (card?.fields.filter((field) => field.state === "confirmed" || field.state === "corrected").length ?? 0), 0);
  const papersLine = current.papers.length === 0 ? SUMMARY.papers_none : current.papers.length === 1 ? SUMMARY.papers_one : SUMMARY.papers_many.replace("{count}", String(current.papers.length));
  const lines = [papersLine];
  if (confirmedFacts > 0) lines.push(confirmedFacts === 1 ? SUMMARY.facts_one : SUMMARY.facts_many.replace("{count}", String(confirmedFacts)));
  const biography = await view(profileId, call, passthrough);
  const plan = await planOut(profileId, call, passthrough);
  const closed: ClosedOut = {
    biography,
    summary: {
      papers: current.papers.length,
      facts: confirmedFacts,
      conditions: saved.conditions?.length ?? 0,
      medicines: kinds.has("medicine_label") ? 1 : 0,
      disputes: Object.values(current.answers).filter((answer) => answer === "no").length,
      questions: Object.values(current.kept).filter(Boolean).length,
      prompts: plan.prompts.length,
      first_prompt_at: plan.prompts[0]?.due_at ?? null,
      lines,
    },
    plan,
  };
  return closed;
}

/** The transport: a Promise for the paths the mock knows, `undefined` for everything else. */
export function mockTransport(path: string, call: Call, passthrough: Passthrough): Promise<unknown> | undefined {
  const method = call.method ?? "GET";
  if (path === "/onboarding/conditions" && method === "GET") {
    const conditions: ConditionsOut = { language: call.query?.language ?? "en", version: VERSION, top: [...TOP], conditions: conditionWords() };
    return Promise.resolve(clone(conditions));
  }
  const match = PROFILE_ROUTE.exec(path);
  if (!match) return undefined;
  const profileId = match[1]!;
  const resource = match[2]!;
  const tail = match[3];

  if (resource === "settings") {
    if (tail) return undefined;
    if (method === "GET") return Promise.resolve(clone(store.settings.get(profileId) ?? defaults(profileId, call.query?.language ?? "en")));
    if (method !== "PUT") return undefined;
    const put = bodyOf<SettingsIn>(call);
    if (put.birth_decade !== null && put.birth_decade !== undefined && put.birth_decade % 10 !== 0) return Promise.reject(new Refused("NotADecade", 400));
    const saved: SettingsOut = {
      ...defaults(profileId, put.language),
      ...put,
      settings_id: store.settings.get(profileId)?.settings_id ?? id("settings"),
      profile_id: profileId,
      set_by_person_id: "mock-person",
      set_at: now(),
      withheld: [],
    };
    store.settings.set(profileId, saved);
    return Promise.resolve(clone(saved));
  }

  if (resource === "plan") {
    if (!tail && method === "GET") return planOut(profileId, call, passthrough).then(clone);
    if (tail === "/later" && method === "POST") {
      const week = store.week.get(profileId);
      if (!week) return Promise.reject(new Refused("NoPlan", 404));
      const { gap_id } = bodyOf<{ gap_id: string }>(call);
      if (!week.order.includes(gap_id)) return Promise.reject(new Refused("NoSuchPrompt", 404));
      week.deferred[gap_id] = (week.deferred[gap_id] ?? 0) + 1;
      return planOut(profileId, call, passthrough).then(clone);
    }
    return undefined;
  }

  if (!SITTING_TAILS.includes(tail)) return undefined;
  return sittingRoute(profileId, method, tail, call, passthrough).then(clone);
}
