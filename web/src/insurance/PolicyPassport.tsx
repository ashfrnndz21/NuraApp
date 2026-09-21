import type { JSX } from "preact";
import type { EssentialItemOut, LedgerOut, PolicyOut } from "../api/types";
import { paperDate } from "../onboarding/dates";
import { fill, language, LOCALE, t } from "../strings";
import { Flag, Glass, PillButton, Reveal, RevealGroup } from "../ui/kit";
import { claimsForPolicy, ESSENTIAL_LIST_CAP, sanitizeDisplayText, splitBenefitLine, totalsForPolicy } from "./model";

const ESSENTIALS_SHOWN_FIRST = 5;

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

function PageMark({ page, pageMarker }: { page: number | null; pageMarker: string }): JSX.Element | null {
  if (page == null) return null;
  return (
    <small class="insurance-page" data-testid="essential-page">
      {fill(pageMarker, { page })}
    </small>
  );
}

/** The silent-truncation notice (independent review, package 12a fix round, item 4): shown
 *  under exactly the section a write actually cut at the backend's own cap
 *  (`PolicyOut.essentials_cut`) — never inferred here from a list's own length, since a
 *  policy that prints exactly twelve lines would be indistinguishable from one that printed
 *  forty. Two short lines, never one two-idea sentence (plain-words rule 2). */
function CutNotice({ n, lines, testId }: { n: number; lines: readonly [string, string]; testId: string }): JSX.Element {
  return (
    <p class="insurance-cut-notice" data-testid={testId}>
      {fill(lines[0], { n })} {lines[1]}
    </p>
  );
}

/** A covers/excludes/claim-step list: the first five lines always shown, the rest behind a
 *  native `<details>` disclosure — no component state at all, so the "Show all N" affordance
 *  needs no hook and works the same way under the plain prop-in/output-data test harness this
 *  package's other components already use. `ordered` draws the how-to-claim list as numbered
 *  steps in the policy's own order; the other lists draw as a plain bulleted list. */
function EssentialsList({ items, testId, showAllN, pageMarker, ordered }: { items: EssentialItemOut[]; testId: string; showAllN: string; pageMarker: string; ordered?: boolean }): JSX.Element {
  const shown = items.slice(0, ESSENTIALS_SHOWN_FIRST);
  const rest = items.slice(ESSENTIALS_SHOWN_FIRST);
  const Tag = ordered ? "ol" : "ul";
  const line = (item: EssentialItemOut, index: number): JSX.Element => (
    <li key={index} data-testid={`${testId}-line`}>
      <span>{sanitizeDisplayText(item.text)}</span>
      <PageMark page={item.page} pageMarker={pageMarker} />
    </li>
  );
  return (
    <>
      <Tag class="insurance-essentials-list" data-testid={testId}>
        {shown.map(line)}
      </Tag>
      {rest.length > 0 && (
        <details class="insurance-essentials-more">
          <summary data-testid={`${testId}-show-all`}>{fill(showAllN, { n: items.length })}</summary>
          <Tag class="insurance-essentials-list">{rest.map(line)}</Tag>
        </details>
      )}
    </>
  );
}

function BenefitsList({ items, testId, pageMarker }: { items: EssentialItemOut[]; testId: string; pageMarker: string }): JSX.Element {
  return (
    <div class="insurance-benefits-list" data-testid={testId}>
      {items.map((item, index) => {
        const { label, amount } = splitBenefitLine(sanitizeDisplayText(item.text));
        return (
          <div class="insurance-benefit-row" key={index} data-testid={`${testId}-row`}>
            <span class="insurance-benefit-label">{label}</span>
            {amount && <span class="insurance-benefit-amount">{amount}</span>}
            <PageMark page={item.page} pageMarker={pageMarker} />
          </div>
        );
      })}
    </div>
  );
}

/** The passport (package 12a, item 2): the policy as a card — insurer, plan, reference, the
 *  period and the state chip computed server-side (`PolicyOut.period_state`, never guessed
 *  here from a date and the browser's own clock) — then the four sections built only from
 *  what the policy's own pages said and were confirmed (`coverage_items`/`excludes`/
 *  `benefits`/`claim_steps`), then the claims filed against it, restyled from the ledger (T2)
 *  exactly as `Ledger.tsx` already shows them. Every amount is the policy's own, as printed;
 *  nothing here computes what he "will get" or whether something "is covered" for him. */
export function PolicyPassport({ policy, ledger, onSeeItself, testId }: { policy: PolicyOut; ledger: LedgerOut | null; onSeeItself?: (reviewCardId: string) => void; testId?: string }): JSX.Element {
  const s = t();
  const p = s.insurance.passport;
  const totals = totalsForPolicy(ledger, policy.policy_id);
  const claims = claimsForPolicy(ledger, policy.policy_id);
  // Never a claim that cover is currently valid (independent review, item 1): `runs_to` is a
  // neutral "question" chip naming the date, `ended` is the one attention chip, and `undated`
  // draws no chip at all — nothing on file to say a date about.
  const chipState = policy.period_state === "ended" ? "attention" : policy.period_state === "runs_to" ? "question" : null;
  const plan = policy.plan ? sanitizeDisplayText(policy.plan, 120) : null;
  const covers = policy.covers ? sanitizeDisplayText(policy.covers, 400) : null;
  const covered = policy.covered ? sanitizeDisplayText(policy.covered, 120) : null;
  const cut = new Set(policy.essentials_cut);

  const locale = LOCALE[language.value];
  // The period line reads the SAME date the chip was computed from (`period_state_date`),
  // never `ends_on` read independently a second time (independent review, note 9: the two
  // once showed different dates for the same policy).
  const periodParts: string[] = [];
  if (policy.start_date) periodParts.push(fill(p.periodFrom, { date: paperDate(policy.start_date, locale) }));
  if (policy.period_state_date) periodParts.push(fill(p.periodTo, { date: paperDate(policy.period_state_date, locale) }));
  const period = periodParts.length > 0 ? periodParts.join(" ") : null;

  return (
    <section data-testid={testId} data-policy-id={policy.policy_id}>
      <Reveal>
        <Glass shape="card">
          <div class="insurance-passport-head">
            <h2>{policy.insurer_name}</h2>
            {chipState && (
              <Flag state={chipState} testId="policy-period-chip">
                {policy.period_state_said}
              </Flag>
            )}
          </div>
          {plan && <p class="insurance-passport-sub">{plan}</p>}
          <p class="insurance-passport-sub">{s.insurance.type[policy.policy_type]}</p>
          <p class="insurance-passport-sub">{s.insurance.status[policy.status]}</p>
          {period && <p class="insurance-passport-sub">{period}</p>}
          {policy.policy_reference && <p class="insurance-passport-sub">{fill(s.insurance.reference, { reference: sanitizeDisplayText(policy.policy_reference, 40) })}</p>}
          {policy.premium_due_date && <p class="insurance-passport-sub">{fill(s.insurance.premiumDue, { date: paperDate(policy.premium_due_date, locale) })}</p>}
          {covered && <p class="insurance-passport-sub">{fill(s.insurance.covered, { value: covered })}</p>}
          {policy.waiting_period && <p class="insurance-passport-sub">{fill(p.waitingPeriodLabel, { text: sanitizeDisplayText(policy.waiting_period, 200) })}</p>}
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
          {policy.review_card_id && onSeeItself && (
            <PillButton variant="quiet" compact onClick={() => onSeeItself(policy.review_card_id!)} testId="see-policy-itself">
              {p.seePolicyItself}
            </PillButton>
          )}
        </Glass>
      </Reveal>

      {/* The insurance boundary line (independent review, item 2): directly under the
       *  passport card, not at the foot of a long scroll — the same words the confirmation
       *  card already shows, since this passport is what a frightened person reads as Nura's
       *  own answer about his cover. */}
      <p class="insurance-boundary" data-testid="passport-boundary">
        {s.insurance.passport.confirmSafety.join(" ")}
      </p>

      <RevealGroup gap={140} className="insurance-sections">
        <Section title={p.coversTitle} testId="section-covers">
          {policy.coverage_items.length > 0 ? (
            <>
              <EssentialsList items={policy.coverage_items} testId="covers-list" showAllN={p.showAllN} pageMarker={p.pageMarker} />
              {cut.has("coverage_items") && <CutNotice n={ESSENTIAL_LIST_CAP} lines={p.essentialsCutNotice} testId="covers-cut-notice" />}
            </>
          ) : covers ? (
            <p data-testid="covers-typed-section">
              {covers} <small class="insurance-page">{p.typedLabel}</small>
            </p>
          ) : (
            <Fallback lines={p.notFound} />
          )}
        </Section>
        <Section title={p.excludesTitle} testId="section-excludes">
          {policy.excludes.length > 0 ? (
            <>
              <EssentialsList items={policy.excludes} testId="excludes-list" showAllN={p.showAllN} pageMarker={p.pageMarker} />
              {cut.has("excludes") && <CutNotice n={ESSENTIAL_LIST_CAP} lines={p.essentialsCutNotice} testId="excludes-cut-notice" />}
            </>
          ) : (
            <Fallback lines={p.notFound} />
          )}
        </Section>
        <Section title={p.benefitsTitle} testId="section-benefits">
          {policy.benefits.length > 0 ? (
            <>
              <BenefitsList items={policy.benefits} testId="benefits-list" pageMarker={p.pageMarker} />
              {cut.has("benefits") && <CutNotice n={ESSENTIAL_LIST_CAP} lines={p.essentialsCutNotice} testId="benefits-cut-notice" />}
            </>
          ) : (
            <Fallback lines={p.notFound} />
          )}
        </Section>
        <Section title={p.claimTitle} testId="section-claim">
          {policy.claim_steps.length > 0 || policy.guarantee_letter || policy.claims_contact ? (
            <>
              {policy.claim_steps.length > 0 && <EssentialsList items={policy.claim_steps} testId="claim-steps-list" showAllN={p.showAllN} pageMarker={p.pageMarker} ordered />}
              {cut.has("claim_steps") && <CutNotice n={ESSENTIAL_LIST_CAP} lines={p.essentialsCutNotice} testId="claim-steps-cut-notice" />}
              {policy.guarantee_letter && <p>{p.worksByGuaranteeLetter}</p>}
              {policy.claims_contact && (
                <p data-testid="claims-contact">
                  <b>{p.whoToContact}: </b>
                  {sanitizeDisplayText(policy.claims_contact, 200)}
                </p>
              )}
            </>
          ) : (
            <Fallback lines={p.notFound} />
          )}
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
