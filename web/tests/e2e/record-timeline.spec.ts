import { expect, test, type APIRequestContext } from "@playwright/test";
import { API, fixClock, seedMedicine, setBackendClock } from "./helpers";
import { FROZEN_CLOCK } from "../../playwright.config";
import {
  addProvider,
  auth,
  book,
  confirmPhoto,
  daysFromNow,
  EVERY_PART,
  letIn,
  LOOKS,
  lookAs,
  openIllness,
  openOwn,
  placeholderPng,
  readable,
  signInAs,
} from "./record-helpers";

/** Checkpoint 25, his visits (W5): E03-01 the spine's three anchors and paging, E03-02 an
 *  illness and a paper put with it on the chief's yes, E03-03 the directory and the chief's
 *  note, E03-04 what changed. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

/** Checkpoint 16's record, and enough visits for a second page: Dr Tan, the chest infection,
 *  a check-up that happened, a visit to come inside the illness, nine older visits, the lab
 *  paper confirmed, and Mei his chief. */
async function seedTimeline(request: APIRequestContext) {
  const pa = await openOwn(request);
  const tan = await addProvider(request, pa, "Dr Tan");
  const illness = await openIllness(request, pa, "chest infection");
  await book(request, pa, tan, await daysFromNow(request, -10), "check-up", ["confirmed", "attended"]);
  await book(request, pa, tan, await daysFromNow(request, 7), "blood pressure review", [], illness);
  for (let n = 0; n < 9; n += 1) await book(request, pa, tan, await daysFromNow(request, -(20 + 7 * n)), "blood pressure review", ["confirmed", "attended"]);
  const lab = await confirmPhoto(request, pa.token, pa.profileId, placeholderPng("lipid-panel-2023-09-07"));
  const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
  return { pa, mei, illness, lab };
}

for (const look of LOOKS) {
  test(`his visits (${look}): the three anchors, a page and the next; an illness and a paper put with it on the chief's yes`, async ({ page, request }) => {
    const { pa, mei, illness, lab } = await seedTimeline(request);
    const first = (await (await request.get(`${API}/profiles/${pa.profileId}/timeline?language=en&limit=10`, auth(mei.token))).json()) as {
      header: { line: string }[];
      items: unknown[];
      next_cursor: string | null;
    };
    expect(first.header).toHaveLength(3);
    expect(first.items).toHaveLength(10);
    expect(first.next_cursor).not.toBeNull();

    await signInAs(page, mei, "Mei", true);
    await lookAs(page, look);
    await page.getByTestId("record-timeline").click();
    const anchors = page.getByTestId("anchors");
    for (const anchor of first.header) await expect(anchors).toContainText(anchor.line);
    await readable(page, look);

    if (look === "caregiver") {
      await expect(page.getByTestId("timeline-item")).toHaveCount(10);
      await page.getByTestId("older").click();
      await expect(page.getByTestId("timeline-item")).toHaveCount(12);
      await expect(page.getByTestId("end-of-list")).toBeVisible();
    } else {
      // One visit or illness a screen, and the next page read when he reaches the end of this one.
      await expect(page.getByTestId("timeline-item")).toHaveCount(1);
      await expect(page.getByTestId("line-of")).toHaveText("This is 1 of 10.");
      for (let n = 1; n < 10; n += 1) await page.getByTestId("next").click();
      await expect(page.getByTestId("line-of")).toHaveText("This is 10 of 10.");
      await page.getByTestId("next").click();
      await expect(page.getByTestId("line-of")).toHaveText("This is 11 of 12.");
      await readable(page, look);
      await page.getByTestId("record-back").click();
      await page.getByTestId("record-timeline").click();
      await page.getByTestId("next").click();
    }

    // The illness: what is filed with it, and the lab paper put with it on Mei's own yes.
    await page.getByTestId("see-illness").first().click();
    await expect(page.getByTestId("record-episode")).toBeVisible();
    await expect(page.locator("h1")).toHaveText("chest infection");
    const toPut = page.getByTestId("paper-to-put");
    await expect(toPut).toHaveCount(1);
    await expect(toPut).toContainText("This is a blood test.");
    await readable(page, look);
    await toPut.getByTestId("put-this").click();
    await expect(page.getByTestId("put-ask")).toContainText("Put this paper with this illness?");
    await readable(page, look);
    await page.getByTestId("put-yes").click();
    await expect(page.getByTestId("put-done")).toHaveText("The paper is with the illness now.");
    await expect(page.getByTestId("episode-papers")).toContainText("This is a photo from");
    await expect(page.getByTestId("nothing-to-put")).toBeVisible();
    await readable(page, look);
    const view = (await (await request.get(`${API}/profiles/${pa.profileId}/episodes/${illness}`, auth(pa.token))).json()) as { episode: { artifacts: { artifact_id: string }[] } };
    expect(view.episode.artifacts.map((each) => each.artifact_id)).toContain(lab.artifactId);
  });

  test(`his doctors (${look}): Dr Tan with his visits and the chief's note; a note naming a medicine is refused`, async ({ page, request }) => {
    const pa = await openOwn(request);
    const tan = await addProvider(request, pa, "Dr Tan", "Gleneagles Hospital, 6A Napier Road");
    await book(request, pa, tan, await daysFromNow(request, -10), "check-up", ["confirmed", "attended"]);
    await book(request, pa, tan, await daysFromNow(request, 7), "blood pressure review");
    const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
    const kit = await letIn(request, pa, "Kit", "caregiver", ["medicines", "visits"]);

    await signInAs(page, mei, "Mei", true);
    await lookAs(page, look);
    await page.getByTestId("record-providers").click();
    const doctor = page.getByTestId("provider");
    await expect(doctor.locator("h2")).toHaveText("Dr Tan");
    await expect(doctor).toContainText("Nura has 2 visits here.");
    await readable(page, look);
    await doctor.getByTestId("see-doctor").click();
    await expect(page.getByTestId("provider-place")).toContainText("Gleneagles Hospital, 6A Napier Road");
    await expect(page.getByTestId("provider-visits")).toContainText("check-up");

    await page.getByLabel("A note about this place").fill("parking at B2");
    await page.getByTestId("save-note").click();
    await expect(page.getByTestId("note-saved")).toHaveText("Nura kept your note.");
    await expect(page.getByTestId("place-note")).toContainText("parking at B2");
    await readable(page, look);

    await page.getByLabel("A note about this place").fill("bring the warfarin");
    await page.getByTestId("save-note").click();
    await expect(page.getByTestId("notice")).toHaveText("Nura cannot keep a note that names a medicine or an illness.");
    await expect(page.getByTestId("place-note")).toHaveCount(1);

    // The notes are the owner's and his chief's alone.
    const his = (await (await request.get(`${API}/profiles/${pa.profileId}/providers/${tan}`, auth(pa.token))).json()) as { notes: { text: string }[] };
    const kits = (await (await request.get(`${API}/profiles/${pa.profileId}/providers/${tan}`, auth(kit.token))).json()) as { notes: unknown[] };
    expect(his.notes.map((note) => note.text)).toEqual(["parking at B2"]);
    expect(kits.notes).toEqual([]);
  });

  test(`what changed (${look}): read twice with a write between`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
    const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
    await signInAs(page, mei, "Mei", true);
    await lookAs(page, look);
    await page.getByTestId("record-changes").click();
    const lines = page.getByTestId("changes-lines");
    await expect(lines).toContainText("This is your first look at what changed.");
    await expect(lines).toContainText("Mei was given a key on Monday 14 September.");
    await readable(page, look);

    // The backend's clock stands still for the run: step it past her first look, write, and
    // look again; then put it back for the tests after.
    await setBackendClock(request, "2026-09-14T10:05:00+08:00");
    try {
      const reading = await request.post(`${API}/profiles/${pa.profileId}/readings`, { ...auth(pa.token), data: { systolic: 132, diastolic: 80 } });
      expect(reading.status()).toBe(201);
      await setBackendClock(request, "2026-09-14T10:10:00+08:00");
      await page.getByTestId("record-back").click();
      await page.getByTestId("record-changes").click();
      await expect(lines).toContainText("A new blood pressure was written down on Monday 14 September.");
      await expect(lines).not.toContainText("This is your first look at what changed.");
      await expect(lines).not.toContainText("Mei was given a key");
      await readable(page, look);
    } finally {
      await setBackendClock(request, FROZEN_CLOCK);
    }
  });
}
