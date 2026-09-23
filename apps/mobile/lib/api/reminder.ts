import { http } from './httpClient';
import { apiConfig } from './config';

export interface MedicationReminder {
  lineId: string;
  name: string;
  instruction: string;
  anchor: string;
  time: string;
  taken: boolean;
}

interface MedicationReminderWire {
  line_id: string;
  name: string;
  instruction: string;
  anchor: string;
  time: string;
  taken: boolean;
}

/** `GET /profiles/{id}/medication-reminder` — Home's own reminder card (C4). `null` when nothing is due. */
export async function getMedicationReminder(profileId: string): Promise<MedicationReminder | null> {
  if (apiConfig.mode === 'demo') return null;
  try {
    const w = await http.get<MedicationReminderWire>(`/profiles/${profileId}/medication-reminder`);
    return { lineId: w.line_id, name: w.name, instruction: w.instruction, anchor: w.anchor, time: w.time, taken: w.taken };
  } catch {
    return null; // nothing due right now — a quiet card, not an error
  }
}
