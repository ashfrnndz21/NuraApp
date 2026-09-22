import type { JSX } from "preact";
import { useState } from "preact/hooks";
import * as nura from "../../api/nura";
import type { ReviewCardOut } from "../../api/types";
import {
  duplicateAddedOnLine,
  duplicateChips,
  duplicateQuestionLead,
  isResultRow,
  readingChips,
  readingHeadline,
  reportRow,
  whoseChips,
  whoseQuestionAsk,
  whoseQuestionLead,
  whoseSetAsideLine,
} from "../../onboarding/review";
import { profile, token } from "../../store/session";
import { language, LOCALE, t } from "../../strings";
import { Notice } from "../../ui/components";
import { Chip, ChipRow, Flag, Glass, Icon, Orb, RevealGroup, SoftText, StatusLine } from "../../ui/kit";

/** The reading screen (E02, docs/design/experience-blueprint.html `firstpaper`/`reading`): the
 *  one component every single-paper upload shows while Nura is really reading it, and what she
 *  found the moment she is done — before he ever sees the full report table. Nothing here is
 *  invented: the status line is only ever the backend's own next real step, and the headline,
 *  chips and rows below are read straight off the card the extractor actually returned. */

/** His paper, as a bubble he "sent" (blueprint `.me`): the file's name, and a small thumbnail
 *  for a photo. Never the bytes themselves — only what he already sees on his own phone. */
export function PaperBubble({ name, thumb, testId }: { name: string; thumb?: string | null; testId?: string }): JSX.Element {
  // A picture the browser cannot draw (a HEIC photo on some browsers, a damaged file) must never
  // show as a broken image: it falls back to the document icon, the same as a PDF (found by the
  // owner on 2026-09-21 in a capture made from a placeholder fixture).
  const [broken, setBroken] = useState(false);
  return (
    <div class="paper-bubble" data-testid={testId}>
      {thumb && !broken ? <img src={thumb} alt="" onError={() => setBroken(true)} data-testid="paper-thumb" /> : <Icon name="records" />}
      <span>{name}</span>
    </div>
  );
}

/** While Nura is really reading: the small living orb beside ONE status line holding the
 *  newest real step the backend reported, replaced in place — never a checklist, never a delay
 *  invented here. If the backend fires two steps 10ms apart, this line simply changes twice. */
export function ReadingProgress({ status, testId }: { status: string; testId?: string }): JSX.Element {
  return (
    <div class="report-row-top" data-testid={testId}>
      <Orb thinking testId="reading-orb" />
      <StatusLine text={status} testId="reading-status" />
    </div>
  );
}

interface ReadingResultProps {
  card: ReviewCardOut;
  /** "See the full table" (or the same action worded for a non-lab kind) — the one way on from
   *  this preview into the full report. */
  onContinue: () => void;
  /** D-2: where "I'm not sure" leaves to — the card stays open, unanswered, exactly as it
   *  is; nothing here resolves it. Defaults to `onContinue` for a caller with no better way
   *  back of its own (a whose-paper mismatch is not expected on every path this component is
   *  used from — an insurance policy's own header has no `patient_name`/`person` fields at
   *  all, so `card.clarify` is simply never set there). */
  onLeaveUnanswered?: () => void;
  testId?: string;
}

/** D-2/D-4b's own conversational turn: the small orb, a lead line naming what the paper (or
 *  the record on file) actually says, one question, and the chips — never more than one
 *  question on screen, and nothing below it: the ordinary reading result (headline, rows,
 *  "See the full table") is not shown while a question is pending, because nothing is filed
 *  from this card until it is answered. */
export function ClarifyTurn({
  lead,
  question,
  chips,
  onPick,
  busy,
  error,
  testId,
}: {
  lead: string;
  question: string;
  chips: { value: string; label: string }[];
  onPick: (value: string) => void;
  busy: boolean;
  error: unknown;
  testId: string;
}): JSX.Element {
  return (
    <div data-testid={testId}>
      <div class="report-row-top">
        <Orb testId="reading-orb" />
      </div>
      <SoftText as="h2" className="conversation-head" text={lead} pace="headline" testId="clarify-lead" />
      <SoftText as="p" text={question} pace="body" testId="clarify-question" />
      <Notice error={error} />
      <ChipRow testId="clarify-chips">
        {chips.map((chip) => (
          <button
            key={chip.value}
            type="button"
            class="glass-chip chip-tap"
            disabled={busy}
            onClick={() => onPick(chip.value)}
            data-testid={`clarify-${chip.value}`}
          >
            {chip.label}
          </button>
        ))}
      </ChipRow>
    </div>
  );
}

/** What Nura found, the instant the card arrives: the headline chosen from the card itself
 *  (never a fixed sentence), the filter chips that have anything in them, each row as a quick
 *  preview (a flag, never a bar — the bar is the full table's own), then one action on into the
 *  report (blueprint `reading`).
 *
 *  D-2/D-4b: a card asking a question (`card.clarify`) shows only that question — the
 *  headline, rows and "See the full table" wait until it is answered (`ClarifyTurn`).
 *  D-4a: the same bytes re-uploaded show the existing card with one calm line naming when it
 *  was first added (`card.duplicate_of_added_on`), the rest of this view unchanged. */
export function ReadingResult({ card: initial, onContinue, onLeaveUnanswered, testId }: ReadingResultProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const locale = LOCALE[language.value];
  const [card, setCard] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const papers = profile.value;
  const isSelf = papers?.standing === "owner";
  const patientName = isSelf ? "" : (papers?.display_name ?? "");
  // The question's own kind, kept beside the card: once answered, `clarify` itself goes back
  // to null (B1, independent safety review — before this, a set-aside card fell straight
  // through to the ordinary headline/rows/"See the full table" below, showing a stranger's
  // own values as "your paper"), so this is the only way left to know which calm line a
  // set-aside answer earns.
  const [askedKind, setAskedKind] = useState(card.clarify?.kind ?? null);

  const answer = async (value: string) => {
    const bearer = token.value;
    if (!bearer) return;
    setBusy(true);
    setError(null);
    try {
      setAskedKind(card.clarify?.kind ?? askedKind);
      setCard(await nura.answerReviewCardQuestion(bearer, card.profile_id, card.card_id, value));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  if (card.clarify?.kind === "whose_paper") {
    const clarify = card.clarify;
    return (
      <ClarifyTurn
        lead={whoseQuestionLead(clarify, s, patientName)}
        question={whoseQuestionAsk(s, patientName)}
        chips={whoseChips(s, patientName)}
        onPick={(value) => (value === "not_sure" ? (onLeaveUnanswered ?? onContinue)() : void answer(value))}
        busy={busy}
        error={error}
        testId={testId ? `${testId}-whose` : "whose-paper-question"}
      />
    );
  }

  if (card.clarify?.kind === "duplicate_paper") {
    const clarify = card.clarify;
    return (
      <ClarifyTurn
        lead={duplicateQuestionLead(clarify, s, locale, patientName)}
        question={r.duplicateQuestion}
        chips={duplicateChips(s)}
        onPick={(value) => void answer(value)}
        busy={busy}
        error={error}
        testId={testId ? `${testId}-duplicate` : "duplicate-paper-question"}
      />
    );
  }

  if (card.discarded) {
    const setAsideLine =
      askedKind === "duplicate_paper" ? r.duplicateSetAside : whoseSetAsideLine(s, patientName);
    return (
      <div data-testid={testId}>
        <p class="note" data-testid="set-aside-line">
          {setAsideLine}
        </p>
        <button type="button" class="btn light" onClick={onLeaveUnanswered ?? onContinue} data-testid="set-aside-back">
          {s.onboarding.back}
        </button>
      </div>
    );
  }

  const headline = readingHeadline(card, s);
  const chips = readingChips(card, s);
  const rows = [...card.fields].sort((a, b) => a.position - b.position).map((field) => reportRow(field, s, locale));
  return (
    <div data-testid={testId}>
      {card.duplicate_of_added_on && (
        <p class="note" data-testid="duplicate-added-on">
          {duplicateAddedOnLine(card.duplicate_of_added_on, s, locale, patientName)}
        </p>
      )}
      <SoftText as="h2" className="conversation-head" text={headline} pace="headline" testId="reading-headline" />
      {chips.length > 0 && (
        <ChipRow testId="reading-chips">
          {chips.map((chip) => (
            <Chip key={chip.key}>{chip.label}</Chip>
          ))}
        </ChipRow>
      )}
      <RevealGroup testId="reading-rows">
        {rows.map((row) => (
          <Glass key={row.fieldId} shape="row" testId={`reading-row-${row.fieldId}`}>
            {isResultRow(row) ? (
              <div class="report-row-top">
                <div class="report-row-name">
                  <b>{row.label}</b>
                </div>
                <span class="report-value-num">
                  {row.valueText}
                  {row.unit && <small>{row.unit}</small>}
                </span>
                {row.flagWord && <Flag state={row.tone === "ok" ? "ok" : "attention"}>{row.flagWord}</Flag>}
              </div>
            ) : (
              /* A line of words (a policy's benefit, a claim step, a name): the label small
                 above the value, which wraps — beside a value that never shrinks, "A benefit
                 or a limit" wrapped letter by letter and the value ran off the screen (the
                 owner's own policy schedule, 22 Sep 2026). The same split the full table makes. */
              <div class="report-row-admin">
                <span class="report-row-admin-label">{row.label}</span>
                <div class="report-row-admin-value-line">
                  <span class="report-row-admin-value">{row.valueText}</span>
                </div>
              </div>
            )}
          </Glass>
        ))}
      </RevealGroup>
      <button type="button" class="btn light" onClick={onContinue} data-testid="see-report">
        {r.seeFullTable}
      </button>
    </div>
  );
}
