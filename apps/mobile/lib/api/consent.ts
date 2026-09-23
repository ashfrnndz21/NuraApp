import { http } from './httpClient';
import { apiConfig } from './config';

export interface ConsentWording {
  purpose: string;
  version: string;
  language: string;
  region: 'SG' | 'MY';
  lines: string[];
}

/**
 * `GET /consent/wording` — the current agreement text, by version. A
 * profile create refuses if the version it's given is not this one
 * (`ConsentIn`'s own doc: "words that are not today's words on file
 * refuse before a profile exists") — always read this first, never
 * hard-code a version.
 */
export async function getConsentWording(language = 'en'): Promise<ConsentWording> {
  if (apiConfig.mode === 'demo') {
    return {
      purpose: 'hold_health_record',
      version: '1',
      language,
      region: 'SG',
      lines: [
        'Nura keeps your papers, your medicines and your blood pressure book.',
        'They never leave the region.',
        'You can tell Nura to stop at any time.',
      ],
    };
  }
  return http.get<ConsentWording>(`/consent/wording?language=${encodeURIComponent(language)}`);
}
