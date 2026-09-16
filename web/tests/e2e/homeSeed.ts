import { expect, type APIRequestContext } from "@playwright/test";
import { API, backendClock, seedMedicine, seedVisitDay } from "./helpers";

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

/** Pa's family as the design shows it (D1): his visit with Dr Tan at half past ten this morning
 *  and Mei his chief (`seedVisitDay`), four blood pressures over the week, two tablets with
 *  breakfast — the blood pressure tablet nearly out — and a note from Mei in the family thread. */
export async function seedHome(request: APIRequestContext): Promise<Awaited<ReturnType<typeof seedVisitDay>>> {
  const seeded = await seedVisitDay(request);
  const now = Date.parse((await backendClock(request)).now);
  for (const [daysAgo, systolic, diastolic] of [
    [6, 146, 90],
    [4, 142, 88],
    [2, 139, 86],
  ] as const) {
    const added = await request.post(`${API}/profiles/${seeded.profileId}/readings`, {
      ...auth(seeded.token),
      data: { systolic, diastolic, taken_at: new Date(now - daysAgo * 86_400_000).toISOString() },
    });
    expect(added.status(), await added.text()).toBe(201);
  }
  await request.post(`${API}/profiles/${seeded.profileId}/readings`, { ...auth(seeded.token), data: { systolic: 138, diastolic: 84 } });
  await seedMedicine(request, seeded.token, seeded.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 5 });
  await seedMedicine(request, seeded.token, seeded.profileId, { generic: "aspirin", strength: "100 mg", dose_text: "1 tab OD", quantity: 30 });
  const note = await request.post(`${API}/profiles/${seeded.profileId}/thread`, {
    ...auth(seeded.meiToken),
    data: { text: "The grandchildren were at the park this morning." },
  });
  expect(note.status(), await note.text()).toBe(201);
  return seeded;
}
