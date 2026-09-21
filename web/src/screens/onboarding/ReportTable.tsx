import { useState } from "preact/hooks";
import type { JSX } from "preact";
import type { ReviewCardOut, ReviewFieldOut } from "../../api/types";
import {
  canCorrect,
  confidenceLine,
  decide,
  facilityField,
  fieldLabel,
  isResultRow,
  kindTitle,
  pillProposalLine,
  provenanceLine,
  readingHeadline,
  reportRow,
  reportSections,
  sharedProvenance,
  spokenLine,
  valueText,
  type FieldEdit,
  type ReportRowView,
} from "../../onboarding/review";
import { fill, language, LOCALE, t, type Strings } from "../../strings";
import { Hear } from "../../ui/components";
import { ActionSheet, Flag, Glass, Icon, RangeBar, Reveal, SoftText } from "../../ui/kit";

/** The report table (E02-07): ONE glass panel of compact rows, hairline-separated, in place of
 *  the 25 stacked cards — a plain label with the paper's own printed label small under it, the
 *  value large with its unit, a range bar drawn only when the paper's own printed range has
 *  parsable bounds, and a flag comparing the reading with THAT range alone. A row asks for him
 *  only when the backend itself is unsure of it (`needs_confirm`) or could not read it
 *  (`unreadable`); every other row shows no sentence about itself at all — tapping the row
 *  still opens the same correction sheet. ONE "Hear" reads the whole report, in order, rather
 *  than one per row.
 *
 *  Results — a row with a unit or a printed range — come first; the administrative rows (a
 *  name, a date, a number on the paper) sit behind a closed "About this paper" disclosure,
 *  except any of them that still needs him, which never hides (library part A #4). A non-result
 *  row's label sits small above its value rather than squeezed beside it (part A #2), and a
 *  value that is itself a date on the paper reads as one, in his language (part A #3). */

interface ReadOnlyProps {
  /** "You checked this on {date}." (or her twin, by his name), once, under the header. */
  checkedOnText: string;
  /** "See the paper itself" / "Ask about this paper" — the caller's own actions (library
   *  part B #3): this component only lays out the report, never the artifact viewer or Ask. */
  actions: JSX.Element;
}

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
  /** Reopening a paper he already checked (library part B #3): every row read-only — never a
   *  button, never the correction sheet — "left out" read from the field's own saved state
   *  rather than `edits` (which holds nothing for a card that was never opened this session),
   *  and the footer replaced with the checked-on line and the caller's own actions. */
  readOnly?: ReadOnlyProps;
}

export function ReportTable({ card, edits, onEdit, waiting, documentDateText, dateText, testId, readOnly }: ReportTableProps): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const locale = LOCALE[language.value];
  const [openField, setOpenField] = useState<string | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);
  const facility = facilityField(card);
  const fields = [...card.fields].filter((field) => field.field_id !== facility?.field_id).sort((a, b) => a.position - b.position);
  const { open: openRows, collapsed: collapsedRows } = reportSections(fields, s, locale);
  const openIndex = fields.findIndex((field) => field.field_id === openField);
  const open = openIndex >= 0 ? fields[openIndex]! : null;
  const proposal = pillProposalLine(card, s);
  const provenance = sharedProvenance(card, dateText, s);
  const headline = readingHeadline(card, s);
  const facilityText = facility ? valueText(facility.value) : null;
  const subtitle = documentDateText && facilityText ? fill(r.dateAndFacility, { date: documentDateText, facility: facilityText }) : (documentDateText ?? facilityText);

  const leftOutOf = (field: ReviewFieldOut): boolean => (readOnly ? field.state === "rejected" : (edits[field.field_id]?.leftOut ?? false));

  const spoken = [
    kindTitle(card.document_kind, s),
    ...(subtitle ? [subtitle] : []),
    ...(card.high_risk_class ? [r.highRisk] : []),
    ...(proposal ? [proposal] : []),
    headline,
    ...fields.flatMap((field) => (leftOutOf(field) ? [fieldLabel(field, s), r.leftOut] : spokenLine(field, s))),
  ];

  const row = (field: ReviewFieldOut): JSX.Element => (
    <ReportRow
      key={field.field_id}
      field={field}
      s={s}
      locale={locale}
      edit={edits[field.field_id]}
      leftOut={leftOutOf(field)}
      readOnly={Boolean(readOnly)}
      onOpen={readOnly ? undefined : () => setOpenField(field.field_id)}
      onKeepIn={readOnly ? undefined : () => onEdit(field.field_id, { leftOut: false })}
    />
  );

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
      {readOnly && (
        <p class="caption report-row-checked" data-testid="report-checked-on">
          {readOnly.checkedOnText}
        </p>
      )}
      <Hear lines={spoken} />
      <Reveal>
        <Glass shape="card" className="report-panel" testId="report-rows">
          {openRows.map(row)}
          {collapsedRows.length > 0 && (
            <button
              type="button"
              class="report-table-row report-about-toggle"
              aria-expanded={aboutOpen}
              onClick={() => setAboutOpen(!aboutOpen)}
              data-testid="about-paper-toggle"
            >
              <span>{r.aboutThisPaper}</span>
              <Icon name="chevron" />
            </button>
          )}
          {aboutOpen && (
            <div data-testid="about-paper-rows">
              {collapsedRows.map(row)}
            </div>
          )}
        </Glass>
      </Reveal>
      {provenance && (
        <p class="caption" data-testid="provenance-once">
          {provenance}
        </p>
      )}
      {open && !readOnly && (
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
      {readOnly && <div class="report-reopen-actions">{readOnly.actions}</div>}
    </div>
  );
}

function ReportRow({
  field,
  s,
  locale,
  edit,
  leftOut,
  readOnly,
  onOpen,
  onKeepIn,
}: {
  field: ReviewFieldOut;
  s: Strings;
  locale: string;
  edit: FieldEdit | undefined;
  leftOut: boolean;
  readOnly: boolean;
  onOpen: (() => void) | undefined;
  onKeepIn: (() => void) | undefined;
}): JSX.Element {
  const r = s.onboarding.records;
  const row = reportRow(field, s, locale);
  const label = fieldLabel(field, s);
  const isResult = isResultRow(row);

  if (leftOut) {
    return (
      <div class="report-table-row report-row left-out" data-testid={`field-${field.attribute}`} data-needs-confirm={field.needs_confirm}>
        <div class="report-row-top">
          <div class="report-row-name">
            <b>{label}</b>
            <small>{readOnly ? r.leftOutByYou : r.leftOut}</small>
          </div>
          {!readOnly && (
            <button type="button" class="btn" onClick={onKeepIn} data-testid="keep-in">
              {r.keepIn}
            </button>
          )}
        </div>
      </div>
    );
  }

  // Whether tapping the row opens the correction sheet at all: a sure, correctable row (tap
  // its value), or any row the backend itself is unsure of / could not read — even one that
  // cannot be retyped, since the sheet still offers "Leave this one out" for it. Never, once
  // the paper is reopened read-only: nothing here is tappable at all.
  const opensSheet = !readOnly && (row.correctable || row.needsAttention);
  const spokenRow = spokenLine(field, s).join(", ");
  const rowLabel = `${spokenRow}${!readOnly && row.correctable ? `. ${r.changeLabel}` : ""}`;

  // A reopened paper is one the person already checked: never ask them to check it again.
  const attentionChip: JSX.Element | false = row.needsAttention && !readOnly ? (
    <span class="flag-chip question" data-testid="check-this-one" aria-hidden="true">
      {r.checkThisOne}
    </span>
  ) : (
    false
  );
  const flagChip: JSX.Element | false =
    !row.needsAttention && row.flagWord ? (
      <Flag state={row.tone === "ok" ? "ok" : "attention"} testId="flag">
        {row.flagWord}
      </Flag>
    ) : (
      false
    );

  const inner = isResult ? (
    <ResultRowInner row={row} attentionChip={attentionChip} flagChip={flagChip} label={label} />
  ) : (
    <AdminRowInner row={row} attentionChip={attentionChip} flagChip={flagChip} label={label} />
  );

  const className = `report-table-row report-row${readOnly ? " read-only" : ""}`;
  if (opensSheet) {
    return (
      <button type="button" class={className} data-testid={`field-${field.attribute}`} data-needs-confirm={field.needs_confirm} onClick={onOpen} aria-label={rowLabel}>
        {inner}
      </button>
    );
  }
  return (
    <div class={className} data-testid={`field-${field.attribute}`} data-needs-confirm={field.needs_confirm} aria-label={spokenRow}>
      {inner}
    </div>
  );
}

/** A result row's inner markup (E02-07): the label and the paper's own printed label to its
 *  left, the value and its unit to the right, then the range bar underneath — unchanged from
 *  before the library split, since only the administrative rows were cramped. */
function ResultRowInner({ row, attentionChip, flagChip, label }: { row: ReportRowView; attentionChip: JSX.Element | false; flagChip: JSX.Element | false; label: string }): JSX.Element {
  return (
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
        {flagChip}
        {attentionChip}
      </div>
      {row.geometry && (
        <div class="report-row-bar" aria-hidden="true">
          <RangeBar bandStart={row.geometry.bandStart} bandWidth={row.geometry.bandWidth} markerAt={row.geometry.markerAt} tone={row.tone === "ok" ? "ok" : "attention"} label="" />
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
}

/** An administrative row's inner markup (library part A #2): the label small, on its own
 *  line, over the value — which wraps freely, at 16px/500 — with the "Check this one" pill
 *  right-aligned on the value's own line, never squeezed beside a long label. */
function AdminRowInner({ row, attentionChip, flagChip, label }: { row: ReportRowView; attentionChip: JSX.Element | false; flagChip: JSX.Element | false; label: string }): JSX.Element {
  return (
    <div class="report-row-admin">
      <span class="report-row-admin-label">{label}</span>
      {row.printedLabel && <span class="report-row-admin-printed">{row.printedLabel}</span>}
      <div class="report-row-admin-value-line">
        <span class="report-row-admin-value">
          {row.valueText}
          {row.unit && <small>{row.unit}</small>}
        </span>
        {flagChip}
        {attentionChip}
      </div>
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
