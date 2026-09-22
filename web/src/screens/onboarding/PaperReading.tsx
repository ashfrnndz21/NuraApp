import type { JSX } from "preact";
import { useState } from "preact/hooks";
import type { ReviewCardOut } from "../../api/types";
import { isResultRow, readingChips, readingHeadline, reportRow } from "../../onboarding/review";
import { language, LOCALE, t } from "../../strings";
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
  testId?: string;
}

/** What Nura found, the instant the card arrives: the headline chosen from the card itself
 *  (never a fixed sentence), the filter chips that have anything in them, each row as a quick
 *  preview (a flag, never a bar — the bar is the full table's own), then one action on into the
 *  report (blueprint `reading`). */
export function ReadingResult({ card, onContinue, testId }: ReadingResultProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const locale = LOCALE[language.value];
  const headline = readingHeadline(card, s);
  const chips = readingChips(card, s);
  const rows = [...card.fields].sort((a, b) => a.position - b.position).map((field) => reportRow(field, s, locale));
  return (
    <div data-testid={testId}>
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
