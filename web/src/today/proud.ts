import type { AuditOut } from "../api/types";

/** The proud number: how many days he has tapped Taken on. Not a streak — a day without a
 *  tap does not take anything away — and it never goes down: the count shown is the larger
 *  of what the trail says and what this phone has already shown him. */

export function proudNumber(days: Iterable<string>, floor = 0): number {
  const distinct = new Set<string>();
  for (const day of days) if (day) distinct.add(day);
  return Math.max(distinct.size, floor);
}

/** The days on which a Taken landed, from the medicines trail (`dose_taken` writes that
 *  were allowed), as local day keys. */
export function daysFromAudit(entries: readonly AuditOut[], toDay: (iso: string) => string): string[] {
  return entries
    .filter((entry) => entry.target === "dose_taken" && entry.action === "write" && entry.outcome === "allowed")
    .map((entry) => toDay(entry.at));
}
