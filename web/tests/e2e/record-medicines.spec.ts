import { expect, test } from "@playwright/test";
import { API, captureSpeech, fixClock, seedFeed, seedMedicine } from "./helpers";
import { auth, EVERY_PART, letIn, LOOKS, lookAs, openOwn, readable, signInAs, unknownPng } from "./record-helpers";

/** Checkpoint 25, his medicines (W5): E04-01 the list with source and confidence, E04-05 the
 *  reorder card's two buttons, E04-06 the story, E04-03 a medicine added and screened. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

interface Line {
  line_id: string;
  source: string;
  generic: string;
}

for (const look of LOOKS) {
  test(`his medicines (${look}): each line with its source and how sure, Ask-to-order, I-have-more, the story`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 5 });
    const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
    const [line] = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as Line[];
    await captureSpeech(page);
    await signInAs(page, pa, "Pa");
    await lookAs(page, look);
    await readable(page, look);

    await page.getByTestId("record-medicines").click();
    const card = page.getByTestId("medicine-line");
    await expect(card.locator("h2")).toHaveText("Your blood pressure tablet");
    await expect(card.getByTestId("chemical")).toHaveText("amlodipine 5 mg");
    await expect(card.getByTestId("count")).toContainText("You have 5 tablets of your blood pressure tablet left.");
    await expect(card.getByTestId("confidence")).toHaveText("You said yes to this.");
    await expect(card.getByTestId("source")).toHaveText(line!.source);
    await readable(page, look);

    // Ask the family to order: a task on the family's list and his chief told, in the
    // backend's words.
    await card.getByTestId("ask-to-order").click();
    await expect(page.getByTestId("asked")).toHaveText("Nura asked Mei to order more of your blood pressure tablet.");
    await expect(card.getByTestId("ask-to-order")).toBeDisabled();
    const tasks = (await (await request.get(`${API}/profiles/${pa.profileId}/tasks`, auth(mei.token))).json()) as { what: string; assigned_person_id: string }[];
    expect(tasks.map((task) => [task.what, task.assigned_person_id])).toEqual([["order more of your blood pressure tablet", mei.personId]]);

    // I have more at home: how many, his yes for that number, the count as the backend says it.
    await card.getByTestId("i-have-more").click();
    await expect(page.getByTestId("record-more")).toBeVisible();
    await expect(page.getByTestId("more-medicine")).toHaveText("Your blood pressure tablet");
    await readable(page, look);
    await page.getByLabel("How many more").fill("20");
    await page.getByTestId("more-yes").click();
    await expect(page.getByTestId("more-done")).toContainText("You have 25 tablets of your blood pressure tablet left.");

    // The story, in his words, the boundary last; Hear reads the backend's own script.
    await page.getByTestId("record-back").click();
    await page.getByTestId("medicine-line").getByTestId("open-story").click();
    const story = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines/${line!.line_id}/story?language=en`, auth(pa.token))).json()) as {
      purpose: string[];
      boundary: string[];
      lines: string[];
    };
    const tile = page.getByTestId("story");
    await expect(tile.getByTestId("story-purpose")).toContainText(story.purpose[0]!);
    await expect(tile.locator(".lines").last()).toHaveAttribute("data-testid", "boundary");
    for (const said of story.boundary) await expect(tile.getByTestId("boundary")).toContainText(said);
    await readable(page, look);
    await tile.getByTestId("hear").click();
    const spoken = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.join(" "));
    for (const said of story.lines) expect(spoken).toContain(said);
  });

  test(`the reorder card on his feed carries Ask-to-order and I-have-more (${look})`, async ({ page, request }) => {
    const seeded = await seedFeed(request);
    await letIn(request, seeded, "Mei", "chief", EVERY_PART);
    await signInAs(page, seeded, "Pa");
    await lookAs(page, look);
    await page.getByTestId("tab-today").click();
    await page.getByTestId("open-feed").click();
    const card = page.locator('article.feed-card[data-variant="reorder"]').first();
    await expect(card.getByTestId("ask-to-order")).toHaveText("Ask the family to order.");
    await expect(card.getByTestId("i-have-more")).toHaveText("I have more at home.");
    await card.getByTestId("ask-to-order").click();
    await expect(card.getByTestId("asked")).toContainText("Nura asked Mei to order more of your blood pressure tablet.");
    await card.getByTestId("i-have-more").click();
    await expect(page.getByTestId("record-more")).toBeVisible();
  });

  test(`add a medicine (${look}): screened before it is saved, the severity and both medicines named; a high-risk one from a file is refused`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await seedMedicine(request, pa.token, pa.profileId, { generic: "warfarin", strength: "3 mg", dose_text: "1 tab OD", quantity: 30 });
    await signInAs(page, pa, "Pa");
    await lookAs(page, look);
    await page.getByTestId("record-medicines").click();
    await page.getByTestId("add-medicine").click();
    await expect(page.getByTestId("add-photo")).toBeVisible();
    await readable(page, look);

    // A label photo Nura cannot read: he types what the label says.
    await page.getByTestId("photo-input").setInputFiles({ name: "aspirin.png", mimeType: "image/png", buffer: unknownPng() });
    await expect(page.getByTestId("add-label")).toBeVisible();
    await page.getByLabel("The name on the label").fill("aspirin");
    await page.getByLabel("How strong it is").fill("100 mg");
    await page.getByLabel("How to take it").fill("1 tab OD");
    await page.getByLabel("How many are in the box").fill("30");
    await page.getByLabel("The doctor's name").fill("Dr Tan");
    await readable(page, look);

    // The backend's check, before anything is saved: the severity and both medicines named.
    await page.getByTestId("check-medicine").click();
    await expect(page.getByTestId("outcome")).toHaveText("This is a new medicine for your list.");
    const interaction = page.getByTestId("interaction");
    await expect(interaction).toHaveCount(1);
    await expect(interaction.getByTestId("pair")).toHaveText("aspirin and warfarin");
    await expect(interaction.getByTestId("severity")).toHaveText("This one matters a lot.");
    await expect(interaction).toContainText("Dr Tan");
    await readable(page, look);
    expect(((await (await request.get(`${API}/profiles/${pa.profileId}/medicines`, auth(pa.token))).json()) as Line[]).map((each) => each.generic)).toEqual(["warfarin"]);

    await page.getByTestId("add-it").click();
    await expect(page.getByTestId("record-note")).toHaveText("Nura added it to your list.");
    const listed = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines`, auth(pa.token))).json()) as Line[];
    expect(listed.map((each) => each.generic).sort()).toEqual(["aspirin", "warfarin"]);

    // A high-risk medicine from a file, not a label photo: the backend refuses it, and he
    // reads the refusal as one sentence.
    await page.getByTestId("add-medicine").click();
    await page.getByTestId("file-input").setInputFiles({
      name: "warfarin.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(`%PDF-1.4\nnura-paper-placeholder:unknown-${Math.random()}\n`),
    });
    await expect(page.getByTestId("add-label")).toBeVisible();
    await page.getByLabel("The name on the label").fill("warfarin");
    await page.getByLabel("How strong it is").fill("1 mg");
    await page.getByLabel("How to take it").fill("1 tab OD");
    await page.getByTestId("check-medicine").click();
    await page.getByTestId("add-it").click();
    await expect(page.getByTestId("notice")).toHaveText("Please take a photo of the label first.");
    await readable(page, look);
    expect(((await (await request.get(`${API}/profiles/${pa.profileId}/medicines`, auth(pa.token))).json()) as Line[]).length).toBe(2);
  });
}
