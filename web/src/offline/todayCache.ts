import { kvGet, kvSet } from "../store/kv";
import type { TodayModel } from "../today/model";

/** The last Today page per profile, kept on the phone so the app opens on it with no
 *  network and no spinner. The service worker keeps the shell; this keeps the data. */

const today = (profileId: string) => `today.${profileId}`;
const proud = (profileId: string) => `proud.${profileId}`;
const days = (profileId: string) => `takenDays.${profileId}`;

export const saveToday = (profileId: string, model: TodayModel) => kvSet(today(profileId), model);
export const loadToday = (profileId: string) => kvGet<TodayModel>(today(profileId));

/** The largest proud number this phone has shown for these papers: the floor it never drops below. */
export const loadProudFloor = async (profileId: string) => (await kvGet<number>(proud(profileId))) ?? 0;
export const saveProudFloor = (profileId: string, value: number) => kvSet(proud(profileId), value);

export const loadTakenDays = async (profileId: string) => (await kvGet<string[]>(days(profileId))) ?? [];
export async function rememberTakenDay(profileId: string, day: string): Promise<string[]> {
  const known = await loadTakenDays(profileId);
  if (!known.includes(day)) {
    known.push(day);
    await kvSet(days(profileId), known);
  }
  return known;
}
