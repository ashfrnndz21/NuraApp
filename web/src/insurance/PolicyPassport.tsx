import type { JSX } from "preact";
import type { LedgerOut, PolicyOut } from "../api/types";
import { fill, t } from "../strings";
import { Flag, Glass, Reveal, RevealGroup } from "../ui/kit";
import { claimsForPolicy, sanitizeDisplayText, totalsForPolicy } from "./model";

/** One section of the passport — a heading, then a card that either holds what is really on
 *  the record or the one calm line every "nothing here" state in this package uses (never a
 *  placeholder, never a blank card, never a guess): `docs/design/build-spec.md` §8's own rule
 *  for a scope-withheld row, applied the same way to a field the paper simply never carried. */
function Section({ title, testId, children }: { title: string; testId: string; children: JSX.Element | JSX.Element[] }): JSX.Element {
  const headingId = `${testId}-heading`;
  return (
    <div>
      <h3 class="insurance-section-title" id={headingId}>
        {title}
      </h3>
      <Reveal testId={testId}>
        <Glass shape="card" attrs={{ role: "group", "aria-labelledby": headingId }}>
          <div class="insurance-section-body">{children}</div>
        </Glass>
      </Reveal>
    </div>
  );
}

function Fallback({ lines }: { lines: readonly [string, string] }): JSX.Element {
  return (
    <div class="insurance-fallback" data-testid="section-not-found">
      <p>{lines[0]}</p>
      <p>{lines[1]}</p>
    </div>
  );
}

/** The passport (package 12a, item 2): the policy as a card — insurer, reference, the period
 *  state chip computed server-side (`PolicyOut.period_state`, never guessed here from a date
 *  and the browser's own clock) — then the four sections built only from what the record and
 *  the reviewed data already say, then the claims filed against it, restyled from the ledger
 *  (T2) exactly as `Ledger.tsx` already shows them. Every amount is the policy's own; nothing
 *  here computes what he "will get" or whether something "is covered" for him. */
export function PolicyPassport({ policy, ledger, testId }: { policy: PolicyOut; ledger: LedgerOut | null; testId?: string }): JSX.Element {
  const s = t();
  const p = s.insurance.passport;
  const totals = totalsForPolicy(ledger, policy.policy_id);
  const claims = claimsForPolicy(ledger, policy.policy_id);
  const chipState = policy.period_state === "ended" ? "attention" : "ok";
  const covers = policy.covers ? sanitizeDisplayText(policy.covers) : null;

  return (
    <section data-testid={testId} data-policy-id={policy.policy_id}>
      <Reveal>
        <Glass shape="card">
          <div class="insurance-passport-head">
            <h2>{policy.insurer_name}</h2>
            <Flag state={chipState} testId="policy-period-chip">
              {policy.period_state_said}
            </Flag>
          </div>
          <p class="insurance-passport-sub">{s.insurance.type[policy.policy_type]}</p>
          {policy.policy_reference && <p class="insurance-passport-sub">{fill(s.insurance.reference, { reference: sanitizeDisplayText(policy.policy_reference, 40) })}</p>}
          {totals && (
            <div class="insurance-stats" data-testid="policy-stats">
              <div>
                <b>{totals.claimed_said}</b>
                <small>{p.claimedThisYear}</small>
              </div>
              <div>
                <b>{totals.paid_by_insurer_said}</b>
                <small>{p.paidByInsurer}</small>
              </div>
              <div>
                <b>{totals.paid_by_patient_said}</b>
                <small>{p.paidByPatient}</small>
              </div>
            </div>
          )}
        </Glass>
      </Reveal>

      <RevealGroup gap={140} className="insurance-sections">
        <Section title={p.coversTitle} testId="section-covers">
          {covers ? <p>{covers}</p> : <Fallback lines={p.notFound} />}
        </Section>
        <Section title={p.excludesTitle} testId="section-excludes">
          <Fallback lines={p.notFound} />
        </Section>
        <Section title={p.benefitsTitle} testId="section-benefits">
          <Fallback lines={p.notFound} />
        </Section>
        <Section title={p.claimTitle} testId="section-claim">
          {policy.guarantee_letter ? <p>{p.worksByGuaranteeLetter}</p> : <Fallback lines={p.notFound} />}
        </Section>
      </RevealGroup>

      {claims.length > 0 && (
        <div>
          <h3 class="insurance-section-title" id={`${testId}-claims-heading`}>
            {p.claimsTitle}
          </h3>
          <Reveal testId="policy-claims">
            <div class="insurance-claims" role="group" aria-labelledby={`${testId}-claims-heading`}>
              {claims.map((claim) => (
                <Glass key={claim.claim_id} shape="row" className="insurance-claim-row" testId="policy-claim-row">
                  <span class="insurance-claim-text">
                    <b>{sanitizeDisplayText(claim.visit_purpose, 80)}</b>
                    <small>{claim.visit_date_said}</small>
                  </span>
                  {claim.claimed_amount_said && <span class="insurance-claim-amount">{claim.claimed_amount_said}</span>}
                  <Flag state={claim.status === "rejected" ? "attention" : claim.status === "paid" || claim.status === "approved" ? "ok" : "question"} testId="policy-claim-status">
                    {claim.status_word}
                  </Flag>
                </Glass>
              ))}
            </div>
          </Reveal>
        </div>
      )}
    </section>
  );
}
