import type { JSX } from "preact";
import type { CostExpectationOut } from "../api/types";
import type { Strings } from "../strings";
import { fill } from "../strings";
import { dateLine } from "../today/model";
import { Sheet } from "../ui/kit";

/** "What it may cost" (T3, `GET /profiles/{id}/visits/{appointmentId}/cost`): a typical fee
 *  range from a public fee benchmark, always cited and dated, and what his cover on file
 *  would likely pay for a key that holds it — every line here but the two static labels
 *  (the sheet's title and "your cover may pay") is the backend's own rendered word, in his
 *  language: the range and covered amounts are already said in his currency (`*_said`), and
 *  `note` is already the plain-words lines that say "typical, not a quote", when to ask, and
 *  whether cover is on file — never composed on the phone. */
export function CostSheet({
  cost,
  open,
  onClose,
  owner,
  patientName,
  locale,
  s,
}: {
  cost: CostExpectationOut | null;
  open: boolean;
  onClose: () => void;
  owner: boolean;
  patientName: string;
  locale: string;
  s: Strings;
}): JSX.Element {
  return (
    <Sheet title={s.day.costTitle} open={open} onClose={onClose} closeLabel={s.shell.close} testId="cost-sheet">
      {cost?.found && (
        <p class="title" data-testid="cost-range">
          {cost.low_said} – {cost.high_said}
        </p>
      )}
      {cost?.covered_shown && (
        <p data-testid="cost-covered">
          {owner ? s.day.costCoveredLabel : fill(s.day.costCoveredLabelOther, { patient: patientName })}
          {": "}
          {cost.covered_low_said} – {cost.covered_high_said}
        </p>
      )}
      {cost?.note.map((line, at) => (
        <p key={at} data-testid="cost-note-line">
          {line}
        </p>
      ))}
      {cost?.source && (
        <p class="source-line" data-testid="cost-source">
          {cost.source.publisher} · {dateLine(new Date(cost.source.fetched_at), locale)}
        </p>
      )}
    </Sheet>
  );
}
