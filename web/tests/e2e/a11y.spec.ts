import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  API,
  apiToken,
  captureSpeech,
  codeFromLog,
  codesSoFar,
  cutKey,
  fixClock,
  freshPhone,
  keptKeys,
  nothingDrawnOverLines,
  openMe,
  proudCard,
  todayReady,
  paperPhoto,
  seedFeed,
  seedOwner,
  seedVisit,
  signInThroughTheApp,
  throughInsight,
  underTheTabBar,
  coveredByTheTabBar,
  pastWelcome,
} from "./helpers";

/** E15-04 on the web (ADR 0001: VoiceOver and Dynamic Type become the page's roles, names and
 *  live regions, and the browser's own text size): axe over every screen, in both densities,
 *  with no serious or critical finding; the writing at 200% with nothing lost, nothing
 *  sideways and nothing drawn over a line; Tab in the order the eye reads, each stop with a
 *  ring; a new screen starting at its heading; Reduce Motion; and his large-text setting taken
 *  from his State. Moderate and minor findings are written on the report. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
  await captureSpeech(page);
});

type Look = "patient" | "caregiver";
const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

/** The look this phone keeps (`device.density`, as Me sets it), written before the app reads it. */
async function lookOnThePhone(page: Page, look: Look): Promise<void> {
  await page.goto("./");
  await page.evaluate(
    (value) =>
      new Promise<void>((done, fail) => {
        const opened = indexedDB.open("nura", 1);
        opened.onupgradeneeded = () => opened.result.createObjectStore("kv");
        opened.onsuccess = () => {
          const tx = opened.result.transaction("kv", "readwrite");
          tx.objectStore("kv").put(value, "device.density");
          tx.oncomplete = () => {
            opened.result.close();
            done();
          };
          tx.onerror = () => fail(tx.error);
        };
        opened.onerror = () => fail(opened.error);
      }),
    look,
  );
  await page.reload();
}

/** No serious or critical axe finding on the page now; the rest go on the report. A demo
 *  deployment's banner (ADR 0008) — its pinned headline and its lines — is its own, and is left
 *  out; the page it sits above is not. */
async function audit(page: Page, where: string): Promise<void> {
  await expect(page.locator("main").first()).toBeVisible();
  const results = await new AxeBuilder({ page }).exclude(".demo-banner").exclude(".demo-lines").analyze();
  const serious = results.violations.filter((each) => each.impact === "serious" || each.impact === "critical");
  for (const each of results.violations) {
    if (!serious.includes(each)) test.info().annotations.push({ type: "axe (moderate or minor)", description: `${where}: ${each.id} (${each.impact})` });
  }
  expect
    .soft(
      serious.map((each) => `${each.id} (${each.impact}): ${each.nodes.map((node) => node.target.join(" ")).slice(0, 3).join(" | ")}`),
      where,
    )
    .toEqual([]);
  // Nothing stuck under the floating tab bar, on any screen that has one.
  expect.soft(await underTheTabBar(page.locator("main").first()), `${where}: under the tab bar`).toEqual([]);
}

/** Every visible element that reaches past the right edge of the screen: nothing sideways. */
async function sideways(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const over: string[] = [];
    for (const element of document.querySelectorAll<HTMLElement>("main *")) {
      if (element.closest(".sr-only") || element.offsetParent === null) continue;
      const box = element.getBoundingClientRect();
      if (box.width > 0 && box.right > width + 1) over.push(`${element.tagName.toLowerCase()}.${element.className}: ${(element.textContent ?? "").trim().slice(0, 40)}`);
    }
    return over;
  });
}

/** A demo deployment's banner (ADR 0008), first on every screen, as the web client shows it when
 *  the backend says it is a demo: the backend's `GET /deployment` answer, given to the page. The
 *  rest of the run is the dev run's, both clocks frozen. */
async function withDemoBanner(page: Page): Promise<void> {
  await page.route("**/api/deployment", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ region: "SG", demo: true }) }));
}

/** The feed at rest fits the phone under whatever sits above it: the page does not scroll, and
 *  no button of the card on screen is under the tab bar. */
async function feedFits(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const page = document.scrollingElement!;
    if (page.scrollHeight > window.innerHeight + 1) problems.push(`the page scrolls: ${page.scrollHeight} > ${window.innerHeight}`);
    const bar = document.querySelector("nav.tabbar")!.getBoundingClientRect();
    const card = document.querySelector<HTMLElement>("article.feed-card")!;
    for (const button of card.querySelectorAll<HTMLElement>(".feed-controls button")) {
      if (button.getBoundingClientRect().bottom > bar.top + 0.5) problems.push(`under the tab bar: ${button.textContent}`);
    }
    return problems;
  });
}

const stageOf = (main: Locator) => main.getAttribute("data-stage");
/** The text of the element now, or null when it is gone: never waits for it to come back. */
const textNow = async (locator: Locator) => ((await locator.count()) > 0 ? await locator.first().textContent() : null);

for (const [look, banner] of [
  ["patient", false],
  ["caregiver", false],
  ["patient", true],
] as const) {
  test(`every screen in the ${look} density${banner ? ", under the demo banner" : ""}: no serious or critical axe finding`, async ({ page, request }) => {
    test.setTimeout(240_000);
    // A screen this walk reaches right after a tap, with nothing else to wait on (`who`'s own
    // reply, `before we start`, the first `about you` turn), can still be mid-`Reveal` (motion.ts
    // REVEAL_MS, 550ms) the instant `toBeVisible()` resolves — genuinely visible, opacity still
    // short of 1. Auditing under Reduce Motion (the same mode a real motion-sensitive person
    // gets, and the mode every transition already collapses to instantly, base.css) is the
    // faithful check: no screen may read worse with motion off, and it removes a false read of
    // a frame no one actually rests on.
    await page.emulateMedia({ reducedMotion: "reduce" });
    const where = (name: string) => `${look}${banner ? " + demo banner" : ""}: ${name}`;
    const patient = look === "patient";
    if (banner) await withDemoBanner(page);
    await lookOnThePhone(page, look);
    await expect(page.locator("html")).toHaveAttribute("data-density", look);
    if (banner) await expect(page.locator(".demo-banner")).toBeVisible();

    // The welcome, before this phone's first sign-in; then signing in.
    await expect(page.getByTestId("welcome-screen")).toBeVisible();
    await audit(page, where("welcome"));
    await page.getByTestId("welcome-start").click();
    await expect(page.getByLabel("Your phone number")).toBeVisible();
    await audit(page, where("sign in"));
    await page.getByRole("button", { name: "Sign in with an email instead" }).click();
    await audit(page, where("sign in with an email"));
    await page.getByRole("button", { name: "Sign in with a phone number instead" }).click();
    const phone = freshPhone("+659333");
    await page.getByLabel("Your phone number").fill(phone);
    await page.getByLabel("Your name").fill("Pa");
    const before = codesSoFar(phone);
    await page.getByTestId("send-code").click();
    await expect(page.getByLabel("The code")).toBeVisible();
    await audit(page, where("the code"));
    await page.getByLabel("The code").fill(await codeFromLog(phone, before));
    await page.getByTestId("verify-code").click();

    // The doors and the words.
    await expect(page.getByTestId("door-for-me")).toBeVisible();
    await audit(page, where("who is this for"));
    await page.getByTestId("door-for-me").click();
    await expect(page.getByTestId("who-continue")).toBeVisible();
    await audit(page, where("who is this for: his reply"));
    await page.getByTestId("who-continue").click();
    await expect(page.getByTestId("consent-words")).toBeVisible();
    await audit(page, where("before we start"));
    await page.getByTestId("agree").click();

    // Onboarding: about you (one question a screen, or one page), the cloud, the papers.
    const main = page.locator("main.onboarding");
    await expect(page.getByLabel("The name Nura uses")).toBeVisible();
    await audit(page, where("about you"));
    await page.getByLabel("The name Nura uses").fill("Pa");
    if (patient) {
      await page.getByTestId("about-next").click();
      await page.getByTestId("about-lang-en").click();
      await page.getByTestId("decade-1950").click();
      await page.getByLabel("The doctor's name").fill("Dr Tan");
      await page.getByTestId("about-next").click();
      await page.getByTestId("breakfast-07:30").click();
      await audit(page, where("about you: a yes or no"));
      for (const item of ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"]) await page.getByTestId(`${item}-no`).click();
      await page.getByTestId("density-simple").click();
    } else {
      await page.getByTestId("about-lang-en").click();
      await page.getByTestId("decade-1950").click();
      await page.getByLabel("The doctor's name").fill("Dr Tan");
      await page.getByTestId("breakfast-07:30").click();
      await page.getByTestId("about-next").click();
    }
    await expect(main).toHaveAttribute("data-stage", "cloud");
    await audit(page, where("the word cloud"));
    await page.getByTestId("word-high_blood_pressure").click();
    await audit(page, where("the word cloud, a word picked"));
    await page.getByTestId("cloud-done").click();
    await expect(main).toHaveAttribute("data-stage", "records");
    await audit(page, where("the papers"));

    // Papers from photos, in the sitting: the grid, what was found, a review card.
    await page.getByTestId("choose-many").click();
    await expect(main).toHaveAttribute("data-stage", "batch");
    await audit(page, where("papers from photos"));
    await page.getByTestId("photos-input").setInputFiles([paperPhoto("lipid-panel-2023-09-07"), paperPhoto("receipt-2026-09-01")]);
    await expect(page.getByTestId("paper-tile")).toHaveCount(2);
    await audit(page, where("papers from photos: the grid"));
    await page.getByTestId("send-papers").click();
    await expect(page.getByTestId("nothing-kept")).toBeVisible();
    await audit(page, where("papers from photos: what was found"));
    await page.getByTestId("paper-result").nth(0).getByTestId("check-paper").click();
    await expect(page.getByTestId("review-card")).toBeVisible();
    await audit(page, where("a review card"));
    await page.getByTestId("looks-right").click();
    await expect(page.getByTestId("insight-headline")).toBeVisible();
    await audit(page, where("what it means for you"));
    await page.getByTestId("insight-leave").click();
    await expect(page.getByTestId("paper-checked")).toBeVisible();
    await page.getByTestId("batch-done").click();
    await page.getByTestId("all-done").click();

    // The read-back, its answer said in a live region; the questions; the first week.
    await expect(main).toHaveAttribute("data-stage", "readBack");
    await audit(page, where("the read-back"));
    // The sitting as the backend holds it: the lines and the questions to answer, in its order.
    const token = await apiToken(request, phone);
    const me = (await (await request.get(`${API}/me`, auth(token))).json()) as { profile_id: string };
    const sittingNow = async () =>
      (await (await request.get(`${API}/profiles/${me.profile_id}/biography?language=en`, auth(token))).json()) as {
        read_back: { line: string }[];
        questions: { line: string }[];
      };
    // Every line on this one screen now, patient density or not (never a separate paged
    // step) — each answered once, the first answer said in a live region.
    {
      const lines = page.getByTestId("readback-line");
      const backendLines = (await sittingNow()).read_back;
      for (const [at, each] of backendLines.entries()) await expect(lines.nth(at)).toContainText(each.line);
      for (let n = 0; n < backendLines.length; n++) {
        await lines.nth(n).getByTestId("readback-yes").click();
        if (n === 0) await expect(page.getByRole("status").filter({ hasText: "Nura will keep that." })).toBeVisible();
      }
      await page.getByTestId("readback-next").click();
    }
    await expect(main).toHaveAttribute("data-stage", "questions");
    await audit(page, where("the questions"));
    if (patient) {
      const question = page.getByTestId("question");
      for (const each of (await sittingNow()).questions) {
        await expect(question).toContainText(each.line);
        await question.getByTestId("keep").click();
      }
    } else {
      await page.getByTestId("questions-next").click();
    }
    await expect(main).toHaveAttribute("data-stage", "plan");
    await audit(page, where("Nura is ready"));

    // Today, with a reading and a visit written down so every part of it shows.
    await request.post(`${API}/profiles/${me.profile_id}/readings`, { ...auth(token), data: { systolic: 138, diastolic: 84 } });
    await seedVisit(request, token, me.profile_id);
    await page.getByTestId("open-nura").click();
    await todayReady(page);
    await audit(page, where("today"));
    // His proud number is on the Me sheet (D1): Hear it where it lives, and audit the sheet
    // with the player open over it.
    await openMe(page);
    await proudCard(page).getByTestId("hear").click();
    await expect(page.getByTestId("player")).toBeVisible();
    await audit(page, where("the Me sheet, the player open"));
    await page.getByTestId("sheet-close").click();

    // His Today carries the blood pressure card; hers is under Visits, with getting ready for
    // the next visit (D1) — the design gives her Home the State, not the prompt.
    if ((await page.getByTestId("write-reading").count()) > 0) await page.getByTestId("write-reading").click();
    else {
      await page.getByTestId("tab-services").click();
      await page.getByTestId("plan-reading").click();
    }
    await audit(page, where("your blood pressure"));
    await page.getByRole("button", { name: "Not now" }).click();

    await page.getByTestId("open-feed").click();
    await expect(page.getByTestId("feed-card").first()).toBeVisible();
    await audit(page, where("more for you"));
    expect.soft(await feedFits(page), where("the feed fits the phone")).toEqual([]);
    await page.getByTestId("action-ask").first().click();
    await audit(page, where("ask"));
    await page.getByLabel("Your question").fill("what papers do I have");
    await page.getByTestId("ask-send").click();
    await expect(page.getByTestId("answer")).toBeVisible();
    await audit(page, where("ask: the answer"));
    await page.getByTestId("back-to-cards").click();
    await page.getByTestId("tab-home").click();

    await page.getByTestId("open-visit").click();
    await expect(page.getByTestId("logistics")).toBeVisible();
    await audit(page, where("your visit"));
    await page.getByRole("button", { name: "Go back" }).click();

    await page.getByTestId("open-emergency").click();
    await expect(page.getByTestId("emergency-card")).toBeVisible();
    await audit(page, where("the emergency card"));
    await page.getByRole("button", { name: "Go back" }).click();

    // The Record (W5, #140): its first screen and every screen it opens, each once its reads
    // are in (a Record screen is aria-busy while they are in flight).
    await page.getByTestId("tab-health").click();
    await page.getByTestId("health-record-hub").click();
    await expect(page.getByTestId("record-hub")).toBeVisible();
    await recordSettled(page);
    await audit(page, where("the Record"));
    for (const entry of await recordEntries(page)) {
      await page.getByTestId(entry).click();
      await recordSettled(page);
      await audit(page, where(`the Record: ${entry.replace("record-", "")}`));
      await page.getByTestId("record-back").click();
      await expect(page.getByTestId("record-hub")).toBeVisible();
    }

    await page.getByTestId("open-me").click();
    await audit(page, where("me"));
    await page.getByTestId("open-papers").click();
    await audit(page, where("papers from your photos"));
    await page.getByTestId("papers-finish").click();

    // For someone else, and the papers someone made for you.
    await page.getByTestId("open-me").click();
    await page.getByTestId("sign-out").click();
    await expect(page.getByLabel("Your phone number")).toBeVisible();
    await signInThroughTheApp(page, freshPhone("+659334"), "Ash");
    await page.getByTestId("door-for-someone").click();
    await audit(page, where("who are you setting this up for"));
    const his = freshPhone("+659335");
    await page.getByLabel("Their name").fill("Ah Kong");
    await page.getByLabel("Their phone number").fill(his);
    await page.getByTestId("relationship-daughter").click();
    await page.getByText("They asked you to do this.").click();
    await page.getByRole("button", { name: "Set it up" }).click();
    await expect(page.locator("main.onboarding")).toBeVisible();
    await audit(page, where("about him, for someone else"));
    await page.getByTestId("set-up-later").click();
    await page.getByTestId("open-me").click();
    await page.getByTestId("sign-out").click();
    await expect(page.getByLabel("Your phone number")).toBeVisible();
    await signInThroughTheApp(page, his, "Ah Kong");
    await page.getByTestId("door-claim").click();
    await audit(page, where("these papers are yours"));
  });
}

/** A Record screen (W5) says it is busy while its reads are in flight: checked once it is not. */
async function recordSettled(page: Page): Promise<void> {
  await page.waitForFunction(() => document.querySelector("main")?.getAttribute("aria-busy") !== "true");
}

/** The Record's entries as this key and this look show them, by test id. */
async function recordEntries(page: Page): Promise<string[]> {
  const entries = await page.getByTestId("record-entries").locator("button").evaluateAll((buttons) => buttons.map((each) => each.getAttribute("data-testid")!));
  expect(entries.length).toBeGreaterThan(0);
  return entries;
}

/** Each label of the tab bar on one line, never broken inside a word: the problems, or []. */
/** Every tab's word is one whole line. The word is what this is about, so the word is what is
 *  measured: the button also holds the icon above it, which is a line of its own by the design,
 *  and its span and text boxes sit a pixel or two apart — measuring the button counts those as
 *  wrapping when nothing has wrapped. A word that really wraps still shows here, because its
 *  own text boxes then sit a line apart. */
async function tabLabelsWhole(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("nav.tabbar button .tab-word")].flatMap((word) => {
      const range = document.createRange();
      range.selectNodeContents(word);
      const tops = [...range.getClientRects()].map((rect) => rect.top).sort((a, b) => a - b);
      const lines = tops.filter((top, at) => at === 0 || top - tops[at - 1]! > 4).length;
      return lines > 1 ? [`${(word.textContent ?? "").trim()}: ${lines} lines`] : [];
    }),
  );
}

for (const banner of [false, true]) test(`the writing at 200%, on a 360 px phone${banner ? ", under the demo banner" : ""}: nothing lost, nothing sideways, nothing drawn over a line`, async ({ page, request }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 360, height: 640 });
  if (banner) await withDemoBanner(page);
  // The browser's own text size at 200%: every size in the app is rem, so it all grows.
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const style = document.createElement("style");
      style.textContent = "html { font-size: 200% !important; }";
      document.head.appendChild(style);
    });
  });
  const pa = await seedOwner(request);
  await seedVisit(request, pa.token, pa.profileId);
  await page.goto("./");
  await pastWelcome(page);
  expect(await page.locator("main p").first().evaluate((el) => getComputedStyle(el).fontSize)).toBe("40px");
  // `bar` is false for a screen shown under a sheet: a sheet is modal, so the page beneath it
  // is covered on purpose and its tab bar is behind the scrim. The sheet's own lines are what
  // must be readable then, and `scope` says so.
  const check = async (where: string, scope: Locator = page.locator("main"), bar = true) => {
    // The screen as he sees it once it has come in: nothing still loading, nothing still moving.
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null)))));
    expect.soft(await sideways(page), `${where}: sideways`).toEqual([]);
    expect.soft(await nothingDrawnOverLines(scope, { minTarget: 56 }), `${where}: drawn over`).toEqual([]);
    if (bar) expect.soft(await underTheTabBar(page.locator("main").first()), `${where}: under the tab bar`).toEqual([]);
  };
  await check("sign in");
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await check("today");
  await openMe(page);
  await proudCard(page).getByTestId("hear").click();
  await check("the Me sheet, the player open", page.getByTestId("me-sheet"), false);
  await page.getByTestId("sheet-close").click();
  await page.getByTestId("open-emergency").click();
  await check("the emergency card");
  await page.getByRole("button", { name: "Go back" }).click();
  await page.getByTestId("open-visit").click();
  await check("your visit");
  await page.getByRole("button", { name: "Go back" }).click();
  await page.getByTestId("open-feed").click();
  await expect(page.getByTestId("feed-card").first()).toBeVisible();
  expect.soft(await feedFits(page), "the feed fits the phone").toEqual([]);
  await check("a feed card", page.locator("article.feed-card").first());
  // The Record (W5, #140) at twice the text: its first screen and every screen it opens.
  await page.getByTestId("tab-health").click();
  await page.getByTestId("health-record-hub").click();
  await expect(page.getByTestId("record-hub")).toBeVisible();
  await recordSettled(page);
  await check("the Record");
  expect.soft(await tabLabelsWhole(page), "the tab bar's labels: whole words, one line each").toEqual([]);
  for (const entry of await recordEntries(page)) {
    await page.getByTestId(entry).click();
    await recordSettled(page);
    await check(`the Record: ${entry.replace("record-", "")}`);
    await page.getByTestId("record-back").click();
    await expect(page.getByTestId("record-hub")).toBeVisible();
  }
  await page.getByTestId("open-me").click();
  await expect(page.getByTestId("sign-out")).toBeVisible();
  // Me is a sheet (D1): the page under it is covered on purpose and its tab bar is behind the
  // scrim, so the sheet's own lines are what must be readable here.
  await check("me", page.getByTestId("me-sheet"), false);
  await page.getByTestId("open-papers").click();
  await page.getByTestId("photos-input").setInputFiles([paperPhoto("lipid-panel-2023-09-07"), paperPhoto("receipt-2026-09-01")]);
  await check("papers from photos: the grid");
  await page.getByTestId("send-papers").click();
  await expect(page.getByTestId("nothing-kept")).toBeVisible();
  await check("papers from photos: what was found");
});

test("Tab goes through what can be pressed in the order the eye reads, each with a ring; a new screen starts at its heading", async ({ page, request }) => {
  const pa = await seedOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await expect(page.locator("main h1")).toBeFocused();
  const stops: { top: number; name: string; ring: boolean; bar: boolean }[] = [];
  for (let n = 0; n < 40; n++) {
    await page.keyboard.press("Tab");
    const stop = await page.evaluate(() => {
      const element = document.activeElement as HTMLElement | null;
      if (!element || element === document.body) return null;
      const holder = (element.closest("label.pill") as HTMLElement | null) ?? element;
      const style = getComputedStyle(holder);
      const ring = (style.outlineStyle !== "none" && style.outlineWidth !== "0px") || style.boxShadow !== "none";
      const box = holder.getBoundingClientRect();
      // The page scrolls inside its own region now (D1: the shell docks the tab bar under it),
      // so where a control sits on the page is its box plus that region's scroll, not the
      // window's — the window does not scroll at all.
      const scroller = holder.closest("[data-testid=shell-scroll]") as HTMLElement | null;
      // The docked ask bar (Shell's `bottomBar`, cp3-home) is chrome of the same kind as the
      // tab bar under it: fixed in the flow below the scrolling region, never itself scrolled,
      // so it is excluded from the top-to-bottom check the same way — reached after every
      // control the page's own content has, never compared against their (scroll-corrected) top.
      const bar = Boolean(element.closest("nav.tabbar") || element.closest(".shell-bottom-bar"));
      return { top: Math.round(box.top + window.scrollY + (scroller?.scrollTop ?? 0)), name: (element.getAttribute("aria-label") || element.textContent || element.tagName).trim().slice(0, 40), ring, bar };
    });
    if (!stop || stops.some((each) => each.name === stop.name && each.top === stop.top)) break;
    stops.push(stop);
  }
  expect(stops.length).toBeGreaterThan(3);
  const onPage = stops.filter((each) => !each.bar);
  for (let at = 1; at < onPage.length; at++) {
    expect(onPage[at]!.top, `${onPage[at - 1]!.name} → ${onPage[at]!.name}`).toBeGreaterThanOrEqual(onPage[at - 1]!.top - 1);
  }
  expect(stops.filter((each) => !each.ring).map((each) => each.name)).toEqual([]);
  expect(stops.findIndex((each) => each.bar)).toBeGreaterThanOrEqual(onPage.length);

  await page.getByTestId("open-emergency").click();
  await expect(page.locator("main h1")).toHaveText("Emergency card");
  await expect(page.locator("main h1")).toBeFocused();
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(page.locator("main h1")).toBeFocused();
});

test("Reduce Motion: nothing moves that he did not ask for, and what answers a tap does so at once", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const pa = await seedOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  const moving = () =>
    page.evaluate(
      () =>
        [...document.querySelectorAll<HTMLElement>("*")].filter((element) => {
          const style = getComputedStyle(element);
          return style.transitionDuration.split(",").some((each) => parseFloat(each) > 0) || style.animationName !== "none";
        }).length,
    );
  expect(await moving()).toBe(0);
  await openMe(page);
  expect(await moving()).toBe(0);
  await proudCard(page).getByTestId("hear").click();
  await expect(page.getByTestId("player")).toBeVisible();
  expect(await moving()).toBe(0);
});

test("his large-text setting, from his State, makes the writing one step bigger on his own phone and on nobody else's", async ({ page, request }) => {
  const pa = await seedOwner(request);
  const mei = await cutKey(request, pa, { name: "Mei", prefix: "+659557" }, "caregiver", ["medicines", "records", "emergency"]);
  const put = async (large: boolean) => {
    const current = (await (await request.get(`${API}/profiles/${pa.profileId}/settings`, auth(pa.token))).json()) as Record<string, unknown>;
    const saved = await request.put(`${API}/profiles/${pa.profileId}/settings`, {
      ...auth(pa.token),
      data: {
        language: "en",
        conditions: (current.conditions as string[] | null) ?? [],
        density: "simple",
        large_text: large,
        high_contrast: false,
        voice_on: false,
        big_targets: false,
        one_thing_per_screen: false,
        read_back: false,
        repeat_prompts: false,
        preferred_name: "Pa",
        doctor_name: null,
        breakfast_time: null,
        birth_decade: null,
      },
    });
    expect(saved.ok(), await saved.text()).toBe(true);
  };
  // The proud card is on the Me sheet (D1): open it to measure a line of his body text, then
  // shut it again so the next step is back on Today.
  const body = async () => {
    await openMe(page);
    const size = await proudCard(page).locator("p").first().evaluate((el) => getComputedStyle(el).fontSize);
    await page.getByTestId("sheet-close").click();
    return size;
  };

  await put(true);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await expect(page.locator("html")).toHaveAttribute("data-text", "large");
  expect(await body()).toBe("25px"); // his 20px body, one step bigger
  expect(await sideways(page)).toEqual([]);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-text", "large"); // kept on the phone
  await put(false);
  await page.reload();
  await todayReady(page);
  await expect(page.locator("html")).not.toHaveAttribute("data-text", "large");
  expect(await body()).toBe("20px");

  // Signing out takes his setting with everything else of his papers: the next person on this
  // phone keeps her own writing size — Mei, reading his papers, on her own phone too.
  await put(true);
  await page.reload();
  await todayReady(page);
  await expect(page.locator("html")).toHaveAttribute("data-text", "large");
  await page.getByTestId("open-me").click();
  await page.getByTestId("sign-out").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-text", "large");
  expect(await keptKeys(page)).not.toContain("device.text");
  await signInThroughTheApp(page, mei.phone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.locator("html")).not.toHaveAttribute("data-text", "large");
});

/** #146's cards, and every other kind the feed pages through — his story (the numbers that
 *  changed, his tablet days, the doctor's words), learning with "From" its publisher, the gate,
 *  the now and today cards: each passes axe with no serious or critical finding, and nothing is
 *  drawn over any of its lines. */
test("every card the feed pages through — his story, learning with its source, the gate — passes axe, and nothing covers a line", async ({ page, request }) => {
  test.setTimeout(120_000);
  const pa = await seedFeed(request);
  await seedVisit(request, pa.token, pa.profileId);
  // A tablet taken today, so his story has tablet days.
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as { line_id: string }[];
  await request.post(`${API}/profiles/${pa.profileId}/medicines/${lines[0]!.line_id}/taken`, { ...auth(pa.token), data: { anchor: "breakfast" } });
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await page.getByTestId("open-feed").click();
  await expect(page.getByTestId("feed-card").first()).toBeVisible();

  const seen: string[] = [];
  for (let at = 0; at < 14; at++) {
    const card = page.locator(`article.feed-card[data-index="${at}"]`);
    if ((await card.count()) === 0) break;
    await card.scrollIntoViewIfNeeded();
    const kind = `${await card.getAttribute("data-supply")}:${await card.getAttribute("data-type")}`;
    seen.push(kind);
    const results = await new AxeBuilder({ page }).include(`article.feed-card[data-index="${at}"]`).analyze();
    const serious = results.violations.filter((each) => each.impact === "serious" || each.impact === "critical");
    expect.soft(serious.map((each) => `${each.id}: ${each.nodes.map((node) => node.target.join(" ")).join(" | ")}`), `card ${at} (${kind})`).toEqual([]);
    expect.soft(await nothingDrawnOverLines(card, { lines: "h2, p", controls: "button", minTarget: 56 }), `card ${at} (${kind})`).toEqual([]);
  }
  test.info().annotations.push({ type: "feed cards audited", description: seen.join(", ") });
  expect(seen.some((kind) => kind.startsWith("story:"))).toBe(true);
  expect(seen.some((kind) => kind.startsWith("learning:"))).toBe(true);
});

/** The tab bar at rest, on Today. The shell (D1) docks the bar under the page, which scrolls in
 *  its own region above it: with Today at rest — opened and not yet scrolled — the bar is drawn
 *  over no card's lines, no Hear, no feeling word. The rule the patient mode asks, nothing drawn
 *  over a line or a control, holds at rest as it does at the page's end (`underTheTabBar`). */
for (const [label, viewport, look] of [
  ["Pixel 5", null, "patient"],
  ["a small phone, 360 by 640", { width: 360, height: 640 }, "patient"],
  ["Pixel 5", null, "caregiver"],
] as const) {
  test(`at rest on Today, the tab bar is drawn over no line and no control — ${label}, ${look} density`, async ({ page, request }) => {
    if (viewport) await page.setViewportSize(viewport);
    const pa = await seedOwner(request);
    await lookOnThePhone(page, look);
    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    await page.waitForLoadState("networkidle");
    const covered = await coveredByTheTabBar(page, 0);
    test.info().annotations.push({ type: "covered by the tab bar at rest", description: covered.join(" | ") || "nothing" });
    expect(covered).toEqual([]);
  });
}
