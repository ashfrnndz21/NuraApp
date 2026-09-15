import { signal } from "@preact/signals";
import type { TodayModel } from "./model";

/** The Today page on screen (fresh or kept), for the Me sheet's proud number: the sheet shows
 *  the number Today read, never one it counted. Null until Today has a page. */
export const todayPage = signal<TodayModel | null>(null);
