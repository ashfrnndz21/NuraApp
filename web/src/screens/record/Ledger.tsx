import type { JSX } from "preact";
import * as nura from "../../api/nura";
import { Refused } from "../../api/client";
import type { LedgerLineOut, LedgerOut } from "../../api/types";
import { fill, language, t, type Strings } from "../../strings";
import { Notice, Tile } from "../../ui/components";
import { RecordFrame, session, useRead } from "./parts";

/** T2's ledger half ("coverage, insurance letters, claims, ledger"): every claim ever filed,
 *  in plain words, with the year's totals up top and the policy named small underneath each
 *  claim. Money's one door (`Scope.MONEY`, `app.insurance.ledger`): a caregiver or a viewer
 *  who does not hold it is told plainly that it is kept to him, never a bare "not open to
 *  you" — the backend still refuses the read (`OutOfScope`, 403); this screen only chooses
 *  the words for that one, named, refusal. */
export function LedgerScreen(): JSX.Element {
  const s = t();
  const { data: ledger, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.insuranceLedger(bearer, profileId, language.value);
  }, [language.value]);

  return (
    <RecordFrame title={s.record.ledger} back={{ name: "hub" }} testId="record-ledger">
      <LedgerBody ledger={ledger} error={error} s={s} />
    </RecordFrame>
  );
}

/** The screen's whole body, apart from the read: no hooks, so a test can hand it fixed data
 *  and read back exactly what a person would see, the same as `WhySheet`. */
export function LedgerBody({
  ledger,
  error,
  s,
}: {
  ledger: LedgerOut | null;
  error: unknown;
  s: Strings;
}): JSX.Element {
  const withheld = error instanceof Refused && error.refusal === "OutOfScope";
  return (
    <>
      {withheld ? (
        <Tile paper role="alert" testId="ledger-withheld">
          <p>{s.record.ledgerWithheld}</p>
        </Tile>
      ) : (
        <Notice error={error} />
      )}
      {ledger && (
        <>
          <Tile paper testId="ledger-totals">
            <p class="label">{fill(s.record.ledgerTotals, { year: ledger.year })}</p>
            <p data-testid="ledger-total-claimed">
              {s.record.ledgerClaimedLabel} {ledger.total_claimed_said}
            </p>
            <p data-testid="ledger-total-insurer">
              {s.record.ledgerInsurerPaidLabel} {ledger.total_paid_by_insurer_said}
            </p>
            <p data-testid="ledger-total-patient">
              {s.record.ledgerPatientPaidLabel} {ledger.total_paid_by_patient_said}
            </p>
          </Tile>
          {ledger.lines.length === 0 ? (
            <Tile paper testId="ledger-none">
              <p>{s.record.ledgerNone}</p>
            </Tile>
          ) : (
            <div class="lines" data-testid="ledger-lines">
              {ledger.lines.map((line) => (
                <LedgerRow key={line.claim_id} line={line} s={s} />
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

function LedgerRow({ line, s }: { line: LedgerLineOut; s: Strings }): JSX.Element {
  return (
    <Tile paper testId={`ledger-claim-${line.claim_id}`}>
      <p class="ledger-visit">{line.visit_purpose}</p>
      <p>{fill(s.record.ledgerOn, { date: line.visit_date_said })}</p>
      {line.claimed_amount_said && (
        <p data-testid="ledger-claimed">
          {s.record.ledgerClaimedLabel} {line.claimed_amount_said}
        </p>
      )}
      {line.paid_by_insurer_said && (
        <p data-testid="ledger-insurer-paid">
          {s.record.ledgerInsurerPaidLabel} {line.paid_by_insurer_said}
        </p>
      )}
      {line.paid_by_patient_said && (
        <p data-testid="ledger-patient-paid">
          {s.record.ledgerPatientPaidLabel} {line.paid_by_patient_said}
        </p>
      )}
      <p class="ledger-status">{line.status_word}</p>
      <p class="ledger-policy label">{line.policy_name}</p>
    </Tile>
  );
}
