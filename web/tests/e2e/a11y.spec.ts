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
  nothingDrawnOverLines,
  paperPhoto,
  seedFeed,
  seedOwner,
  seedVisit,
  signInThroughTheApp,
  underTheTabBar,
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
    const where = (name: string) => `${look}${banner ? " + demo banner" : ""}: ${name}`;
    const patient = look === "patient";
    if (banner) await withDemoBanner(page);
    await lookOnThePhone(page, look);
    await expect(page.locator("html")).toHaveAttribute("data-density", look);
    if (banner) await expect(page.locator(".demo-banner")).toBeVisible();

    // Signing in.
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
    if (patient) {
      // One line a screen: each answered once, on its own screen, the answer said in a live region.
      const line = page.getByTestId("readback-line");
      for (const [at, each] of (await sittingNow()).read_back.entries()) {
        await expect(line).toContainText(each.line);
        await line.getByTestId("readback-yes").click();
        if (at === 0) await expect(page.getByRole("status").filter({ hasText: "Nura will keep that." })).toBeVisible();
      }
    } else {
      const lines = page.getByTestId("readback-line");
      for (let n = 0; n < (await lines.count()); n++) {
        await lines.nth(n).getByTestId("readback-yes").click();
        await expect(lines.nth(n).getByTestId("readback-yes")).toHaveAttribute("aria-pressed", "true");
      }
      await expect(page.getByRole("status").filter({ hasText: "Nura will keep that." })).toBeVisible();
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
    await expect(page.getByTestId("proud")).toBeVisible();
    await audit(page, where("today"));
    await page.getByTestId("proud").getByTestId("hear").click();
    await expect(page.getByTestId("player")).toBeVisible();
    await audit(page, where("today, the player open"));

    await page.getByTestId("write-reading").click();
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
    await page.getByRole("button", { name: "Today", exact: true }).click();

    await page.getByTestId("open-visit").click();
    await expect(page.getByTestId("logistics")).toBeVisible();
    await audit(page, where("your visit"));
    await page.getByRole("button", { name: "Go back" }).click();

    await page.getByTestId("open-emergency").click();
    await expect(page.getByTestId("emergency-card")).toBeVisible();
    await audit(page, where("the emergency card"));
    await page.getByRole("button", { name: "Go back" }).click();

    await page.getByRole("button", { name: "Me", exact: true }).click();
    await audit(page, where("me"));
    await page.getByTestId("open-papers").click();
    await audit(page, where("papers from your photos"));
    await page.getByTestId("papers-finish").click();

    // For someone else, and the papers someone made for you.
    await page.getByRole("button", { name: "Me", exact: true }).click();
    await page.getByTestId("sign-out").click();
    await expect(page.getByLabel("Your phone number")).toBeVisible();
    await signInThroughTheApp(page, freshPhone("+659334"), "Ash");
    await page.getByTestId("door-for-someone").click();
    await audit(page, where("who are you setting this up for"));
    const his = freshPhone("+659335");
    await page.getByLabel("Their name").fill("Ah Kong");
    await page.getByLabel("Their phone number").fill(his);
    await page.getByLabel("Who they are to you").fill("Father");
    await page.getByText("They asked you to do this.").click();
    await page.getByRole("button", { name: "Set it up" }).click();
    await expect(page.locator("main.onboarding")).toBeVisible();
    await audit(page, where("about him, for someone else"));
    await page.getByTestId("set-up-later").click();
    await page.getByRole("button", { name: "Me", exact: true }).click();
    await page.getByTestId("sign-out").click();
    await expect(page.getByLabel("Your phone number")).toBeVisible();
    await signInThroughTheApp(page, his, "Ah Kong");
    await page.getByTestId("door-claim").click();
    await audit(page, where("these papers are yours"));
  });
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
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  expect(await page.locator("main p").first().evaluate((el) => getComputedStyle(el).fontSize)).toBe("40px");
  const check = async (where: string, scope: Locator = page.locator("main")) => {
    // The screen as he sees it once it has come in: nothing still loading, nothing still moving.
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null)))));
    expect.soft(await sideways(page), `${where}: sideways`).toEqual([]);
    expect.soft(await nothingDrawnOverLines(scope, { minTarget: 56 }), `${where}: drawn over`).toEqual([]);
    expect.soft(await underTheTabBar(page.locator("main").first()), `${where}: under the tab bar`).toEqual([]);
  };
  await check("sign in");
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("proud")).toBeVisible();
  await check("today");
  await page.getByTestId("proud").getByTestId("hear").click();
  await check("today, the player open");
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
  await page.getByRole("button", { name: "Me", exact: true }).click();
  await expect(page.getByTestId("sign-out")).toBeVisible();
  await check("me");
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
  await expect(page.getByTestId("proud")).toBeVisible();
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
      return { top: Math.round(box.top + window.scrollY), name: (element.getAttribute("aria-label") || element.textContent || element.tagName).trim().slice(0, 40), ring, bar: Boolean(element.closest("nav.tabbar")) };
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
  await expect(page.getByTestId("proud")).toBeVisible();
  const moving = () =>
    page.evaluate(
      () =>
        [...document.querySelectorAll<HTMLElement>("*")].filter((element) => {
          const style = getComputedStyle(element);
          return style.transitionDuration.split(",").some((each) => parseFloat(each) > 0) || style.animationName !== "none";
        }).length,
    );
  expect(await moving()).toBe(0);
  await page.getByTestId("proud").getByTestId("hear").click();
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
  const body = () => page.getByTestId("proud").locator("p").first().evaluate((el) => getComputedStyle(el).fontSize);

  await put(true);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-text", "large");
  expect(await body()).toBe("25px"); // his 20px body, one step bigger
  expect(await sideways(page)).toEqual([]);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-text", "large"); // kept on the phone
  await put(false);
  await page.reload();
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-text", "large");
  expect(await body()).toBe("20px");

  // Mei's phone, reading his papers, keeps her own writing size.
  await put(true);
  await page.getByRole("button", { name: "Me", exact: true }).click();
  await page.getByTestId("sign-out").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  await signInThroughTheApp(page, mei.phone, "Mei");
  await page.getByTestId("door-key").click();
  await expect(page.getByTestId("proud")).toBeVisible();
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
  await expect(page.getByTestId("proud")).toBeVisible();
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
