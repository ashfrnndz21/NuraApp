import { signal } from "@preact/signals";
import type { TodayModel } from "./model";

/** The Today page on screen (fresh or kept) and whose papers it was read from, for the Me
 *  sheet's proud number: the sheet shows the number Today read, never one it counted, and only
 *  under the profile it was read for. Null until Today has a page, and again after sign-out. */
export const todayPage = signal<{ profileId: string; model: TodayModel } | null>(null);
