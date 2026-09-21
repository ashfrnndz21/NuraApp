import { useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut, ReviewFieldOut } from "../../api/types";
import { canCorrect, confidenceLine, decide, fieldLabel, kindLine, pillProposalLine, readingHeadline, reportRow, sharedProvenance, provenanceLine, type FieldEdit } from "../../onboarding/review";
import { fill, t, type Strings } from "../../strings";
import { Hear } from "../../ui/components";
import { ActionSheet, Flag, Glass, RangeBar, RevealGroup, SoftText } from "../../ui/kit";

/** The report table (E02-07): one glass panel of rows in place of the 25 stacked cards — a
 *  plain label with the paper's own printed label small under it, the value large with its
 *  unit, a range bar drawn only when the paper's own printed range has parsable bounds, and a
 *  flag comparing the reading with THAT range alone. A row asks for him only when the backend
 *  itself is unsure of it (`needs_confirm`) or could not read it (`unreadable`); every other
 *  row shows no sentence about itself at all — tapping its value still opens the same
 *  correction sheet. */

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
  patient: boolean;
  testId?: string;
}

export function ReportTable({ card, edits, onEdit, waiting, documentDateText, dateText, patient, testId }: ReportTableProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const [openField, setOpenField] = useState<string | null>(null);
  const fields = [...card.fields].sort((a, b) => a.position - b.position);
  const openIndex = fields.findIndex((field) => field.field_id === openField);
  const open = openIndex >= 0 ? fields[openIndex]! : null;
  const proposal = pillProposalLine(card, s);
  const provenance = sharedProvenance(card, dateText, s);

  return (
    <div data-testid={testId} data-card-id={card.card_id}>
      <p class="kick">{kindLine(card.document_kind, s)}</p>
      {documentDateText && <p class="caption">{fill(r.dated, { date: documentDateText })}</p>}
      {card.high_risk_class && <p class="caption" data-testid="high-risk">{r.highRisk}</p>}
      {proposal && <p class="caption">{proposal}</p>}
      <SoftText as="h1" text={readingHeadline(card, s)} testId="report-headline" />
      <Hear
        lines={[
          kindLine(card.document_kind, s),
          ...(documentDateText ? [fill(r.dated, { date: documentDateText })] : []),
          ...(card.high_risk_class ? [r.highRisk] : []),
          ...(proposal ? [proposal] : []),
          readingHeadline(card, s),
        ]}
      />
      <RevealGroup testId="report-rows">
        {fields.map((field) => (
          <ReportRow
            key={field.field_id}
            field={field}
            s={s}
            edit={edits[field.field_id]}
            leftOut={edits[field.field_id]?.leftOut ?? false}
            onOpen={() => setOpenField(field.field_id)}
            onKeepIn={() => onEdit(field.field_id, { leftOut: false })}
            patient={patient}
          />
        ))}
      </RevealGroup>
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
  patient,
}: {
  field: ReviewFieldOut;
  s: Strings;
  edit: FieldEdit | undefined;
  leftOut: boolean;
  onOpen: () => void;
  onKeepIn: () => void;
  patient: boolean;
}): JSX.Element {
  const r = s.onboarding.records;
  const row = reportRow(field, s);
  const label = fieldLabel(field, s);

  if (leftOut) {
    return (
      <Glass shape="row" className="report-row left-out" testId={`field-${field.attribute}`} attrs={{ "data-needs-confirm": field.needs_confirm }}>
        <div class="report-row-top">
          <div class="report-row-name">
            <b>{label}</b>
            <small>{r.leftOut}</small>
          </div>
          <button type="button" class="btn" onClick={onKeepIn} data-testid="keep-in">
            {r.keepIn}
          </button>
        </div>
      </Glass>
    );
  }

  return (
    <Glass shape="row" className="report-row" testId={`field-${field.attribute}`} attrs={{ "data-needs-confirm": field.needs_confirm }}>
      <div class="report-row-top">
        <div class="report-row-name">
          <b>{label}</b>
          {row.printedLabel && <small>{row.printedLabel}</small>}
        </div>
        {row.correctable ? (
          <button type="button" class="report-row-value" onClick={onOpen} aria-label={`${label}: ${r.changeLabel}`} data-testid="row-value">
            <span class="report-value-num">
              {row.valueText}
              {row.unit && <small>{row.unit}</small>}
            </span>
          </button>
        ) : (
          <span class="report-row-value">
            <span class="report-value-num">
              {row.valueText}
              {row.unit && <small>{row.unit}</small>}
            </span>
          </span>
        )}
        {!row.needsAttention && row.flagWord && <Flag state={row.tone === "ok" ? "ok" : "attention"} testId="flag">{row.flagWord}</Flag>}
        {row.needsAttention && (
          <button type="button" class="report-row-check" onClick={onOpen} data-testid="check-this-one">
            <span class="flag-chip question">{r.checkThisOne}</span>
          </button>
        )}
      </div>
      {row.geometry && (
        <div class="report-row-bar">
          <RangeBar
            bandStart={row.geometry.bandStart}
            bandWidth={row.geometry.bandWidth}
            markerAt={row.geometry.markerAt}
            tone={row.tone === "ok" ? "ok" : "attention"}
            label={`${label}, ${row.valueText}${row.unit ? ` ${row.unit}` : ""}, ${row.rangeText ?? ""}`}
          />
          {row.rangeText && <p class="report-row-range-text">{row.rangeText}</p>}
        </div>
      )}
      {!row.geometry && row.rangeText && <p class="report-row-range-text">{row.rangeText}</p>}
      {patient && <Hear lines={leftOut ? [label, r.leftOut] : [label, `${row.valueText}${row.unit ? ` ${row.unit}` : ""}`, confidenceLine(field, s)]} />}
    </Glass>
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
