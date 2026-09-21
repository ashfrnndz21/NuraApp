import { useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut, ReviewFieldOut } from "../../api/types";
import {
  canCorrect,
  confidenceLine,
  decide,
  facilityField,
  fieldLabel,
  kindTitle,
  pillProposalLine,
  provenanceLine,
  readingHeadline,
  reportRow,
  sharedProvenance,
  spokenLine,
  valueText,
  type FieldEdit,
} from "../../onboarding/review";
import { fill, t, type Strings } from "../../strings";
import { Hear } from "../../ui/components";
import { ActionSheet, Flag, Glass, RangeBar, Reveal, SoftText } from "../../ui/kit";

/** The report table (E02-07): ONE glass panel of compact rows, hairline-separated, in place of
 *  the 25 stacked cards — a plain label with the paper's own printed label small under it, the
 *  value large with its unit, a range bar drawn only when the paper's own printed range has
 *  parsable bounds, and a flag comparing the reading with THAT range alone. A row asks for him
 *  only when the backend itself is unsure of it (`needs_confirm`) or could not read it
 *  (`unreadable`); every other row shows no sentence about itself at all — tapping the row
 *  still opens the same correction sheet. ONE "Hear" reads the whole report, in order, rather
 *  than one per row. */

interface ReportTableProps {
  card: ReviewCardOut;
  edits: Record<string, FieldEdit>;
  onEdit: (fieldId: string, patch: Partial<FieldEdit>) => void;
  waiting: string[];
  /** `card.document_date`, already in his own language and day-month order (`paperDate`). */
  documentDateText: string | null;
  /** `card.created_at`, the same way — the photo/paper's own arrival date, for the once-only
   *  provenance line. */
  dateText: string;
  testId?: string;
}

export function ReportTable({ card, edits, onEdit, waiting, documentDateText, dateText, testId }: ReportTableProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const [openField, setOpenField] = useState<string | null>(null);
  const facility = facilityField(card);
  const fields = [...card.fields].filter((field) => field.field_id !== facility?.field_id).sort((a, b) => a.position - b.position);
  const openIndex = fields.findIndex((field) => field.field_id === openField);
  const open = openIndex >= 0 ? fields[openIndex]! : null;
  const proposal = pillProposalLine(card, s);
  const provenance = sharedProvenance(card, dateText, s);
  const headline = readingHeadline(card, s);
  const facilityText = facility ? valueText(facility.value) : null;
  const subtitle = documentDateText && facilityText ? fill(r.dateAndFacility, { date: documentDateText, facility: facilityText }) : (documentDateText ?? facilityText);

  const spoken = [
    kindTitle(card.document_kind, s),
    ...(subtitle ? [subtitle] : []),
    ...(card.high_risk_class ? [r.highRisk] : []),
    ...(proposal ? [proposal] : []),
    headline,
    ...fields.flatMap((field) => (edits[field.field_id]?.leftOut ? [fieldLabel(field, s), r.leftOut] : spokenLine(field, s))),
  ];

  return (
    <div data-testid={testId} data-card-id={card.card_id}>
      <p class="kick" data-testid="report-title">
        {kindTitle(card.document_kind, s)}
      </p>
      {subtitle && (
        <p class="caption" data-testid="report-subtitle">
          {subtitle}
        </p>
      )}
      {card.high_risk_class && <p class="caption" data-testid="high-risk">{r.highRisk}</p>}
      {proposal && <p class="caption">{proposal}</p>}
      <SoftText as="h1" className="conversation-head" text={headline} testId="report-headline" />
      <Hear lines={spoken} />
      <Reveal>
        <Glass shape="card" className="report-panel" testId="report-rows">
          {fields.map((field) => (
            <ReportRow
              key={field.field_id}
              field={field}
              s={s}
              edit={edits[field.field_id]}
              leftOut={edits[field.field_id]?.leftOut ?? false}
              onOpen={() => setOpenField(field.field_id)}
              onKeepIn={() => onEdit(field.field_id, { leftOut: false })}
            />
          ))}
        </Glass>
      </Reveal>
      {provenance && (
        <p class="caption" data-testid="provenance-once">
          {provenance}
        </p>
      )}
      {open && (
        <CorrectionSheet
          field={open}
          edit={edits[open.field_id] ?? { text: "", leftOut: false }}
          waiting={waiting.includes(open.field_id)}
          onEdit={(patch) => onEdit(open.field_id, patch)}
          onClose={() => setOpenField(null)}
          s={s}
          provenance={!provenance ? provenanceLine(open, s) : null}
        />
      )}
      <p class="caption" data-testid="safety-line">
        {r.safetyRanges} {r.safetyNotAdvice}
      </p>
    </div>
  );
}

function ReportRow({
  field,
  s,
  edit,
  leftOut,
  onOpen,
  onKeepIn,
}: {
  field: ReviewFieldOut;
  s: Strings;
  edit: FieldEdit | undefined;
  leftOut: boolean;
  onOpen: () => void;
  onKeepIn: () => void;
}): JSX.Element {
  const r = s.onboarding.records;
  const row = reportRow(field, s);
  const label = fieldLabel(field, s);

  if (leftOut) {
    return (
      <div class="report-table-row report-row left-out" data-testid={`field-${field.attribute}`} data-needs-confirm={field.needs_confirm}>
        <div class="report-row-top">
          <div class="report-row-name">
            <b>{label}</b>
            <small>{r.leftOut}</small>
          </div>
          <button type="button" class="btn" onClick={onKeepIn} data-testid="keep-in">
            {r.keepIn}
          </button>
        </div>
      </div>
    );
  }

  // Whether tapping the row opens the correction sheet at all: a sure, correctable row (tap
  // its value), or any row the backend itself is unsure of / could not read — even one that
  // cannot be retyped, since the sheet still offers "Leave this one out" for it.
  const opensSheet = row.correctable || row.needsAttention;
  const spokenRow = spokenLine(field, s).join(", ");
  const rowLabel = `${spokenRow}${row.correctable ? `. ${r.changeLabel}` : ""}`;

  const inner = (
    <>
      <div class="report-row-top">
        <div class="report-row-name">
          <b>{label}</b>
          {row.printedLabel && <small>{row.printedLabel}</small>}
        </div>
        <span class="report-value-num">
          {row.valueText}
          {row.unit && <small>{row.unit}</small>}
        </span>
        {!row.needsAttention && row.flagWord && (
          <Flag state={row.tone === "ok" ? "ok" : "attention"} testId="flag">
            {row.flagWord}
          </Flag>
        )}
        {row.needsAttention && (
          <span class="flag-chip question" data-testid="check-this-one" aria-hidden="true">
            {r.checkThisOne}
          </span>
        )}
      </div>
      {row.geometry && (
        <div class="report-row-bar" aria-hidden="true">
          <RangeBar
            bandStart={row.geometry.bandStart}
            bandWidth={row.geometry.bandWidth}
            markerAt={row.geometry.markerAt}
            tone={row.tone === "ok" ? "ok" : "attention"}
            label=""
          />
          {row.rangeText && <p class="report-row-range-text">{row.rangeText}</p>}
        </div>
      )}
      {!row.geometry && row.rangeText && (
        <p class="report-row-range-text" aria-hidden="true">
          {row.rangeText}
        </p>
      )}
    </>
  );

  if (opensSheet) {
    return (
      <button
        type="button"
        class="report-table-row report-row"
        data-testid={`field-${field.attribute}`}
        data-needs-confirm={field.needs_confirm}
        onClick={onOpen}
        aria-label={rowLabel}
      >
        {inner}
      </button>
    );
  }
  return (
    <div class="report-table-row report-row" data-testid={`field-${field.attribute}`} data-needs-confirm={field.needs_confirm} aria-label={spokenRow}>
      {inner}
    </div>
  );
}

function CorrectionSheet({
  field,
  edit,
  waiting,
  onEdit,
  onClose,
  s,
  provenance,
}: {
  field: ReviewFieldOut;
  edit: FieldEdit;
  waiting: boolean;
  onEdit: (patch: Partial<FieldEdit>) => void;
  onClose: () => void;
  s: Strings;
  provenance: string | null;
}): JSX.Element {
  const r = s.onboarding.records;
  const label = fieldLabel(field, s);
  const correctable = canCorrect(field);
  const readLine = field.unreadable ? null : fill(r.nuraRead, { value: `${reportRow(field, s).valueText}${field.unit ? ` ${field.unit}` : ""}` });
  const [invalid, setInvalid] = useState(false);

  return (
    <ActionSheet
      open
      title={label}
      sub={confidenceLine(field, s)}
      notNowLabel={s.onboarding.back}
      onClose={onClose}
      cta={{
        label: r.checkSheetConfirm,
        busyLabel: r.checkSheetConfirming,
        doneLabel: r.checkSheetConfirmed,
        onAct: async () => {
          const decided = decide(field, edit);
          if (!decided.ok) {
            setInvalid(true);
            throw new Error("waiting");
          }
          setInvalid(false);
          onClose();
        },
      }}
      testId="check-sheet"
    >
      {field.unreadable && (field.prompt ?? [r.typeIt]).map((line, index) => <p key={index}>{line}</p>)}
      {readLine && <p>{readLine}</p>}
      {correctable && (
        <label class="field-edit">
          <span class="sr-only">{`${label}: ${r.changeLabel}`}</span>
          <input
            class="field"
            name={`field-${field.attribute}`}
            aria-label={`${label}: ${r.changeLabel}`}
            inputMode={typeof field.value === "number" ? "decimal" : "text"}
            data-unreadable={field.unreadable || undefined}
            value={edit.text}
            onInput={(event) => {
              setInvalid(false);
              onEdit({ text: (event.target as HTMLInputElement).value });
            }}
          />
        </label>
      )}
      {(waiting || invalid) && (
        <p role="alert" data-testid="sheet-not-a-number">
          {field.unreadable ? r.typeIt : r.notANumber}
        </p>
      )}
      {provenance && <p class="caption">{provenance}</p>}
      <button type="button" class="btn" onClick={() => onEdit({ leftOut: !edit.leftOut })} data-testid="leave-out">
        {edit.leftOut ? r.keepIn : r.leaveOut}
      </button>
    </ActionSheet>
  );
}
