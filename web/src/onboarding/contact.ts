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

/** A number as a contact keeps it, as the door takes it: "+65 9123 4567" → "+6591234567",
 *  "0065 …" → "+65…". A number kept without its country code is left as its digits, never
 *  guessed at: the field then asks for the country code before anything is sent, so an
 *  invitation with his name in it never goes to a stranger's number. */
export function phoneFromContact(raw: string): string {
  const kept = raw.replace(/[^\d+]/g, "");
  if (kept.startsWith("+")) return kept;
  if (kept.startsWith("00")) return `+${kept.slice(2)}`;
  return kept;
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
