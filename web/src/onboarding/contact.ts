/** The for-someone door's phone number from the phone's own contacts (E01-01, ADR 0001: the
 *  Contact Picker API where the browser has it; Safari on iOS has none, and the number is
 *  typed there). Only the number and the name come back, and only the one contact picked. */

interface ContactsManager {
  select(properties: ("name" | "tel")[], options?: { multiple?: boolean }): Promise<{ name?: string[]; tel?: string[] }[]>;
}

function manager(): ContactsManager | null {
  if (typeof navigator === "undefined") return null;
  const contacts = (navigator as Navigator & { contacts?: ContactsManager }).contacts;
  return contacts && typeof contacts.select === "function" ? contacts : null;
}

export function canPickContact(): boolean {
  return manager() !== null;
}

/** A number as a contact keeps it, as the door takes it: "+65 9123 4567" → "+6591234567";
 *  a local Malaysian number (0 first) → "+60…"; any other local number → "+65…". */
export function phoneFromContact(raw: string): string {
  const kept = raw.replace(/[^\d+]/g, "");
  if (kept.startsWith("+")) return kept;
  if (kept.startsWith("00")) return `+${kept.slice(2)}`;
  if (kept.startsWith("0")) return `+60${kept.slice(1)}`;
  if (/^(65|60)\d{8,10}$/.test(kept)) return `+${kept}`;
  return `+65${kept}`;
}

/** One contact, picked on the phone's own sheet: its first number and first name. Null when
 *  nothing was picked or the browser has no picker. */
export async function pickContact(): Promise<{ phone: string | null; name: string | null } | null> {
  const contacts = manager();
  if (!contacts) return null;
  try {
    const [picked] = await contacts.select(["name", "tel"], { multiple: false });
    if (!picked) return null;
    const tel = picked.tel?.find((each) => each.trim());
    return { phone: tel ? phoneFromContact(tel) : null, name: picked.name?.find((each) => each.trim()) ?? null };
  } catch {
    return null; // cancelled, or not allowed
  }
}
