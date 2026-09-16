import { expect, test, type Request } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { API, backendClock, captureSpeech, fakeRecorder, fixClock, nothingDrawnOverLines, seedVisitDay, shotAs, signInThroughTheApp, stand } from "./helpers";

/** Checkpoint 22's web half: the Visit screen on a phone-sized screen, against `make dev`
 *  serving the build, both clocks at 10 in the morning in Singapore on Monday 14 September.
 *  Pa's visit to Dr Tan is at half past 10. The phone's recorder is a stand-in that hands back
 *  the consult recording the fixtures know, so what is heard, who spoke when and the post-visit
 *  card are the backend's own. */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)})`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
  await captureSpeech(page);
  await fakeRecorder(page);
});

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
/** The card layout rule on the Visit screen: no control drawn over a line, every button 56 by 56
 *  (the patient density), with #118's hit test (`nothingDrawnOverLines`). */
const nothingCovers = (page: import("@playwright/test").Page) =>
  nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label, blockquote, figcaption", controls: "button", minTarget: 56 });
const spoken = (page: import("@playwright/test").Page) => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
/** The recording's calls: its chunked upload (#129) — the open as the microphone opens, the
 *  chunks as it listens, the doctor's yes, a no, Stop, and "how far did you get" after a
 *  dropped connection — and the whole of it at once, #128's route, now only a fallback. Sent
 *  (`request`), and answered (`response`, below 400). */
function watchRecording(page: import("@playwright/test").Page) {
  const kinds = {
    whole: (method: string, path: string) => method === "POST" && /\/appointments\/[^/]+\/recording$/.test(path),
    open: (method: string, path: string) => method === "POST" && /\/recording\/uploads$/.test(path),
    chunk: (method: string, path: string) => method === "PUT" && /\/recording\/uploads\/[^/]+\/chunks\/\d+$/.test(path),
    yes: (method: string, path: string) => method === "POST" && /\/recording\/uploads\/[^/]+\/yes$/.test(path),
    finish: (method: string, path: string) => method === "POST" && /\/recording\/uploads\/[^/]+\/finish$/.test(path),
    status: (method: string, path: string) => method === "GET" && /\/recording\/uploads\/[^/]+$/.test(path),
    thrown: (method: string, path: string) => method === "DELETE" && /\/recording\/uploads\/[^/]+$/.test(path),
  };
  type Kind = keyof typeof kinds;
  const empty = () => Object.fromEntries(Object.keys(kinds).map((kind) => [kind, [] as Request[]])) as Record<Kind, Request[]>;
  const sent = empty();
  const answered = empty();
  const sort = (into: Record<Kind, Request[]>, request: Request) => {
    const path = new URL(request.url()).pathname;
    for (const [kind, is] of Object.entries(kinds) as [Kind, (method: string, path: string) => boolean][]) {
      if (is(request.method(), path)) into[kind].push(request);
    }
  };
  page.on("request", (request) => sort(sent, request));
  page.on("response", (response) => {
    if (response.status() < 400) sort(answered, response.request());
  });
  return { sent, answered };
}
const because = (request: Request) => new URL(request.url()).searchParams.get("because");
const durationOf = (request: Request) => Number(new URL(request.url()).searchParams.get("duration_s"));

test("the visit screen: logistics from the record, the yes to a driver, consent, the notice first, chunks as it listens, kept on Stop, the card with its clips", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  // The logistics card is on his feed on the day (T-0), in the backend's words: the visits'
  // part only — who drives him and Mei's note stay on the Visit screen, under their own scope.
  const feed = (await (await request.get(`${API}/profiles/${pa.profileId}/feed`, auth(pa.token))).json()) as { items: { type: string; headline: string; body: string[] }[] };
  const logistics = feed.items.find((item) => item.type === "visit_logistics");
  expect(logistics?.headline).toBe("Getting to Dr Tan today");
  expect(logistics?.body).toContain("You see Dr Tan on Monday 14 September at half past 10 in the morning.");
  expect(logistics?.body.some((line) => line.includes("Mei"))).toBe(false);

  const { sent, answered } = watchRecording(page);
  const clipsAsked: string[] = [];
  page.on("request", (one) => {
    if (/\/artifacts\/[^/]+\/clip/.test(one.url())) clipsAsked.push(one.url());
  });
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();

  const card = page.getByTestId("logistics");
  await expect(card).toContainText("You see Dr Tan on Monday 14 September at half past 10 in the morning.");
  await expect(card).toContainText("Dr Tan is at Gleneagles Hospital, 6A Napier Road.");
  await expect(card).toContainText("Mei wrote a note about getting to Dr Tan.");
  await expect(page.getByTestId("place-note")).toContainText("Mei's note");
  await expect(page.getByTestId("place-note")).toContainText("parking at B2");
  await expect(card).toContainText("Mei will tell you who is driving you to Dr Tan on Monday 14 September.");
  await expect(card).toContainText("Bring your blood pressure book on Monday 14 September.");
  await expect(page.getByTestId("drive-suggestion")).toContainText("It is Mei's turn that day.");
  await expect(page.getByTestId("keep-open")).toHaveText("Keep this page open while Nura listens.");
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp22-visit-logistics", true);

  // The owner's yes to the roster's suggestion: Mei drives.
  await page.getByTestId("drive-yes").click();
  await expect(card).toContainText("Mei will drive you to Dr Tan on Monday 14 September.");
  await expect(page.getByTestId("drive-suggestion")).toHaveCount(0);

  // Start: he has not agreed yet, so his words come first; nothing listens before his yes.
  await page.getByTestId("start-recording").click();
  await expect(page.getByTestId("recording-consent")).toContainText("When you see the doctor, Nura listens.");
  expect((await stand(page)).__recorder.starts).toBe(0);
  expect(await spoken(page)).toEqual([]);
  await page.getByTestId("agree-recording").click();

  // The notice, shown and said to Dr Tan by name; the microphone opens as it is said.
  const notice = page.getByTestId("notice");
  await expect(notice).toContainText("Nura will listen now.");
  await expect(notice).toContainText("Is that OK, Dr Tan?");
  await expect.poll(async () => (await stand(page)).__recorder.starts).toBe(1);
  expect(await spoken(page)).toEqual(["Nura will listen now.", "Nura keeps what you and Dr Tan say.", "Only you and the family you let in can hear it.", "Is that OK, Dr Tan?"]);
  expect((await stand(page)).__recorder.types).toEqual(["audio/webm;codecs=opus"]);
  // The upload opens as the microphone opens, in the recorder's own container (#129).
  await expect.poll(() => sent.open.length).toBe(1);
  expect(JSON.parse(sent.open[0]!.postData() ?? "{}").content_type).toBe("audio/webm;codecs=opus");
  await expect(page.getByTestId("red-dot")).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp22-visit-notice", true);

  expect(sent.chunk).toHaveLength(0); // no audio leaves the phone before the doctor's yes
  await page.getByTestId("doctor-yes").click();
  await expect.poll(() => sent.yes.length).toBe(1);
  // Answered before the clock jumps: a jump past the call's deadline with the yes still on its
  // way would end that call as a dropped connection, which is the dropped-connection test's.
  await expect.poll(() => answered.yes.length).toBe(1);
  // A second, and the recorder has handed over its first piece; then the rest of the visit,
  // with the upload's own thirty-second send in it.
  await page.clock.fastForward("00:01");
  await page.clock.fastForward("01:05");
  await expect(page.getByTestId("timer")).toHaveText("1:06");
  // The audio goes up in chunks while Nura listens; nothing is put together until Stop.
  await expect.poll(() => sent.chunk.length).toBeGreaterThanOrEqual(1);
  expect(sent.chunk[0]!.headers()["content-type"]).toBe("application/octet-stream");
  expect(sent.yes).toHaveLength(1);
  expect(sent.finish).toHaveLength(0);
  expect((await stand(page)).__locks.taken).toBe(1);

  await page.getByTestId("stop-recording").click();
  const summary = page.getByTestId("summary");
  await expect(summary).toContainText("Ask Dr Tan about the new amount of the water pill (frusemide).");
  await expect(page.getByTestId("saved")).toContainText("Nura kept the recording.");
  expect(sent.finish).toHaveLength(1);
  expect(sent.whole).toHaveLength(0);
  expect(durationOf(sent.finish[0]!)).toBeGreaterThanOrEqual(66);
  expect(durationOf(sent.finish[0]!)).toBeLessThan(67);
  const recorded = await stand(page);
  expect(recorded.__recorder.stops).toBe(1);
  expect(recorded.__locks.released).toBe(1);
  expect(await summary.getByTestId("hear-clip").count()).toBeGreaterThanOrEqual(5);
  await expect(summary.getByTestId("boundary")).toBeVisible();
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp22-visit-summary", true);

  // "Hear what Dr Tan said" under the water pill: only that stretch, on the tap.
  expect((await stand(page)).__clips).toEqual([]);
  const line = summary.getByTestId("summary-line").filter({ hasText: "water pill" });
  await line.getByTestId("hear-clip").click();
  await expect.poll(async () => (await stand(page)).__clips.length).toBe(1);
  expect((await stand(page)).__clips[0]).toMatch(/^blob:.*#t=19\.8,28\.9$/);
  expect(clipsAsked).toHaveLength(1);
  await expect(line.getByTestId("hear-clip")).toHaveText("Hear what Dr Tan said");

  // Ask: before his yes the card is waiting and nothing Dr Tan said is cited; after it, the
  // answer finds where he said it and plays the same stretch.
  type Answer = { lines: { text: string; clip: { start_s: number; end_s: number } | null }[] };
  const askIt = async () =>
    (await (
      await request.post(`${API}/profiles/${pa.profileId}/ask`, { ...auth(pa.token), data: { question: "what did Dr Tan say about the water pill", mode: "voice" } })
    ).json()) as Answer;
  const before = await askIt();
  expect(before.lines[0]?.text).toBe("What Dr Tan said on Monday 14 September is waiting for your yes.");
  expect(before.lines.every((each) => each.clip === null)).toBe(true);
  const cards = (await (await request.get(`${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}/summaries`, auth(pa.token))).json()) as {
    summary_id: string;
    items: { item_id: string }[];
  }[];
  const decisions = cards[0]!.items.map((item) => ({ item_id: item.item_id, decision: "confirmed" }));
  const yes = (await (
    await request.post(`${API}/profiles/${pa.profileId}/confirmations`, { ...auth(pa.token), data: { subject: "visit_summary", summary_id: cards[0]!.summary_id, decisions } })
  ).json()) as { confirmation_id: string };
  const closed = await request.post(`${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}/summary/${cards[0]!.summary_id}/confirm`, {
    ...auth(pa.token),
    data: { decisions, confirmation_id: yes.confirmation_id },
  });
  expect(closed.ok()).toBe(true);
  expect((await askIt()).lines[0]?.clip).toMatchObject({ start_s: 19.8, end_s: 28.9 });
});

test("a no keeps nothing: the recorder stops, what was sent is thrown away, and the notes are written by hand", async ({ page, request }) => {
  const pa = await seedVisitDay(request, { recording: true });
  const { sent } = watchRecording(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();
  await page.getByTestId("start-recording").click();
  await expect(page.getByTestId("notice")).toContainText("Is that OK, Dr Tan?");
  await expect.poll(async () => (await stand(page)).__recorder.starts).toBe(1);
  await page.getByTestId("doctor-no").click();

  const no = page.getByTestId("when-no");
  await expect(no).toContainText("Nura will not listen today.");
  await expect(no).toContainText("You will write the notes by hand.");
  const after = await stand(page);
  expect(after.__recorder).toMatchObject({ starts: 1, stops: 1 });
  expect(after.__locks.released).toBe(after.__locks.taken);
  // The upload opened with the microphone is thrown away on the server; no audio was sent.
  await expect.poll(() => sent.thrown.map(because)).toEqual(["no"]);
  expect(sent.chunk).toHaveLength(0);
  expect(sent.finish).toHaveLength(0);
  expect(sent.whole).toHaveLength(0);
  await expect(page.getByTestId("by-hand")).toContainText("Write what Dr Tan said");
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp22-visit-no", true);

  await page.getByTestId("notes").fill("Dr Tan said to weigh every morning.");
  await page.getByTestId("save-notes").click();
  await expect(page.getByTestId("summary")).toContainText("Dr Tan said this on Monday 14 September.");
  expect(sent.finish).toHaveLength(0);
  expect(sent.whole).toHaveLength(0);
  const recordings = (await (await request.get(`${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}/recordings`, auth(pa.token))).json()) as unknown[];
  expect(recordings).toEqual([]);
});

test("the page hidden while listening stops at once, and what was heard is kept on the phone for one tap", async ({ page, request }) => {
  const pa = await seedVisitDay(request, { recording: true });
  const { sent } = watchRecording(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();
  await page.getByTestId("start-recording").click();
  await page.getByTestId("doctor-yes").click();
  await page.clock.fastForward("00:30");
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const held = page.getByTestId("held");
  await expect(held).toContainText("Nura stopped listening when you left this page.");
  expect((await stand(page)).__recorder.stops).toBe(1);
  expect(sent.finish).toHaveLength(0);
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.getByTestId("keep-heard").click();
  await expect(page.getByTestId("saved")).toContainText("Nura kept the recording.");
  expect(sent.finish).toHaveLength(1);
  expect(sent.whole).toHaveLength(0);
  // Thirty seconds on the phone's clock, give or take the tick the timer lands on.
  expect(durationOf(sent.finish[0]!)).toBeGreaterThanOrEqual(30);
  expect(durationOf(sent.finish[0]!)).toBeLessThan(31);
});

test("a dropped connection while Nura listens: it says so, sends the rest when it is back, and Stop keeps it all", async ({ page, request }) => {
  const pa = await seedVisitDay(request, { recording: true });
  const { sent, answered } = watchRecording(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();
  await page.getByTestId("start-recording").click();
  await expect.poll(() => answered.open.length).toBe(1);
  await page.getByTestId("doctor-yes").click();
  await expect.poll(() => answered.yes.length).toBe(1);

  // The signal goes: every call the recording's upload makes fails as a lost connection does.
  // Nura keeps listening, and says the recording goes when the connection is back.
  const theUpload = /\/recording\/uploads/;
  await page.route(theUpload, (route) => route.abort("internetdisconnected"));
  await page.clock.fastForward("00:01");
  await page.clock.fastForward("00:29");
  const lost = page.getByTestId("no-connection");
  await expect(lost).toHaveText("The phone has no connection right now.");
  await expect(page.getByText("Nura sends the recording when the connection is back.")).toBeVisible();
  await expect(page.getByTestId("red-dot")).toBeVisible();
  expect(answered.chunk).toHaveLength(0);

  // Back: it asks the server how far it got, and sends from there.
  await page.unroute(theUpload);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(lost).toHaveCount(0);
  await expect.poll(() => answered.status.length).toBeGreaterThanOrEqual(1);
  await expect.poll(() => answered.chunk.length).toBeGreaterThanOrEqual(1);

  // It drops again as Stop is tapped: the recording stays on the phone, and goes by itself the
  // moment the connection is back.
  await page.route(theUpload, (route) => route.abort("internetdisconnected"));
  await page.getByTestId("stop-recording").click();
  const held = page.getByTestId("held");
  await expect(held.getByTestId("no-connection")).toHaveText("The phone has no connection right now.");
  await expect(held).toContainText("Nura sends the recording when the connection is back.");
  await expect(held).toContainText("Keep this page open until then.");
  await page.unroute(theUpload);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByTestId("saved")).toContainText("Nura kept the recording.");
  await expect(page.getByTestId("summary")).toContainText("Ask Dr Tan about the new amount of the water pill (frusemide).");
  expect(answered.finish).toHaveLength(1);
  expect(sent.whole).toHaveLength(0);
  // One recording, put together from the chunks, the fixture's own: the same card as a single upload.
  const recordings = (await (await request.get(`${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}/recordings`, auth(pa.token))).json()) as { segments: unknown[] }[];
  expect(recordings).toHaveLength(1);
  expect(recordings[0]!.segments).toHaveLength(11);
});
