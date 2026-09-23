/** `POST /profiles/{id}/ask` — confirmed against the running dev server's `/openapi.json`. */

export type AskMode = 'voice' | 'text';

export interface AskIn {
  question: string;
  mode?: AskMode;
  language?: string | null;
  /** A tap on a clarifying question's own chip — the chip's opaque `value`, never shown again. */
  value?: string | null;
}

export interface Cite {
  label?: string;
  paper?: string;
  [key: string]: unknown;
}

export interface AnswerLine {
  text: string;
  cites: Cite[];
  clip?: Record<string, unknown> | null;
}

export interface AskAnswer {
  questionArtifactId: string | null;
  mode: AskMode;
  language: string;
  answered: boolean;
  lines: AnswerLine[];
  /** Deterministic-owned honesty lines (§29) — read verbatim, never paraphrased. */
  honest: string[];
  /** What Nura will not say without withheld scopes lifted. */
  boundary: string[];
  spoken: string[];
  withheld: string[];
  /** A clarifying question instead of an answer (W2) — never together with `lines`. */
  clarify?: {
    question: string;
    options: { label: string; value: string }[];
    allowOther: boolean;
  } | null;
  conversationId?: string | null;
  redFlag?: boolean;
  /**
   * Not yet modelled field-by-field: `voice_script`, `looked_at`,
   * `proposals` (AnswerOut, backend/app/channels/api/schemas.py). Present
   * on the wire; screens that need one should give it a typed field here
   * rather than reaching into this bag.
   */
  raw?: Record<string, unknown>;
}
