import { http } from './httpClient';
import { apiConfig } from './config';
import type { AskAnswer, AskIn } from '../../domain/askAnswer';

interface AskAnswerWire {
  question_artifact_id: string | null;
  mode: 'voice' | 'text';
  language: string;
  answered: boolean;
  lines: { text: string; cites: unknown[]; clip: Record<string, unknown> | null }[];
  honest: string[];
  boundary: string[];
  spoken: string[];
  withheld: string[];
  clarify: { question: string; options: { label: string; value: string }[]; allow_other: boolean } | null;
  conversation_id?: string | null;
  red_flag?: boolean;
  [key: string]: unknown;
}

function fromWire(w: AskAnswerWire): AskAnswer {
  return {
    questionArtifactId: w.question_artifact_id,
    mode: w.mode,
    language: w.language,
    answered: w.answered,
    lines: w.lines.map((l) => ({ text: l.text, cites: (l.cites ?? []) as AskAnswer['lines'][number]['cites'], clip: l.clip })),
    honest: w.honest,
    boundary: w.boundary,
    spoken: w.spoken,
    withheld: w.withheld,
    clarify: w.clarify ? { question: w.clarify.question, options: w.clarify.options, allowOther: w.clarify.allow_other } : null,
    conversationId: w.conversation_id ?? null,
    redFlag: w.red_flag ?? false,
    raw: w,
  };
}

/**
 * `POST /profiles/{id}/ask` — the non-streaming answer. C5's "Ask Nura"
 * screen streams instead, over `POST /profiles/{id}/runs` with
 * `intent: 'answer_question'` (`lib/ai/runClient.ts`), so the answer
 * arrives word by word from `TEXT_MESSAGE_CONTENT`; this one is for a
 * caller (a test, a non-streaming surface) that only needs the finished
 * answer.
 */
export async function askNura(profileId: string, body: AskIn): Promise<AskAnswer> {
  if (apiConfig.mode === 'demo') {
    throw new Error('askNura: demo mode has no fixture yet — use the C5 event stream fixture instead.');
  }
  const wire = await http.post<AskAnswerWire>(`/profiles/${profileId}/ask`, {
    question: body.question,
    mode: body.mode ?? 'text',
    language: body.language ?? null,
    value: body.value ?? null,
  });
  return fromWire(wire);
}
