import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { LedgerOut, PolicyOut, ReviewCardOut } from "../api/types";
import { go } from "../flow";
import { LoadPolicyFlow } from "../insurance/LoadPolicy";
import { PolicyPassport } from "../insurance/PolicyPassport";
import { ProposePolicySheet } from "../insurance/ProposePolicy";
import { confirmedPolicyFields } from "../insurance/model";
import { profile, token } from "../store/session";
import { fill, language, t } from "../strings";
import "../ui/insurance.css";
import { Header, Notice, Tile } from "../ui/components";
import { focusHeading } from "../ui/focus";
import { Icon, Orb, PaperTile, PillButton, SoftText } from "../ui/kit";
import { Shell } from "./Shell";

type Mode = { name: "passport" } | { name: "load" };

/** Profile's Insurance row (package 12a — E13-03 plus the passport built on top of it):
 *  every policy on his profile, its own passport — what it covers, what it does not, benefits
 *  and limits, how to claim, all from what the record and the reviewed data really say — the
 *  claims filed against it, and the way to load a new policy paper. Reached only by a key that
 *  opens `Scope.MONEY` (`ProfileNav`'s own gate); a narrower key is refused (`OutOfScope`, 403)
 *  before a row is read, shown here exactly as any other refusal (`Notice`). */
export function InsuranceScreen(): JSX.Element {
  const s = t();
  const p = s.insurance.passport;
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";
  const [policies, setPolicies] = useState<PolicyOut[] | null>(null);
  const [ledger, setLedger] = useState<LedgerOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [mode, setMode] = useState<Mode>({ name: "passport" });
  const [proposing, setProposing] = useState<ReviewCardOut | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const refresh = (): void => {
    const bearer = token.value;
    const at = profile.value;
    if (!bearer || !at) return;
    nura.policies(bearer, at.profile_id, language.value).then(setPolicies, (failure: unknown) => {
      setPolicies([]);
      setError(failure);
    });
    nura.insuranceLedger(bearer, at.profile_id, language.value).then(setLedger, () => setLedger(null));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [papers?.profile_id]);
  useEffect(() => focusHeading(), [mode.name]);

  if (mode.name === "load") {
    return (
      <LoadPolicyFlow
        onCancel={() => setMode({ name: "passport" })}
        onDone={(card) => {
          setMode({ name: "passport" });
          if (card.document_kind === "insurance_policy") {
            setProposing(card);
          } else {
            setNote(p.savedAsPaper);
            refresh();
          }
        }}
      />
    );
  }

  return (
    <Shell tab="profile" testId="insurance-screen">
      <Header title={owner ? s.insurance.title : fill(s.insurance.titleOther, { patient: name })} onBack={() => go({ name: "profile" })} />
      <Notice error={error} />
      {note && (
        <Tile paper role="status" testId="insurance-note">
          <p>{note}</p>
        </Tile>
      )}

      {policies && policies.length === 0 && !error && (
        <div class="insurance-empty" data-testid="insurance-none">
          <Orb testId="insurance-empty-orb" />
          <SoftText as="p" text={owner ? s.insurance.none : fill(s.insurance.noneOther, { patient: name })} />
          <PillButton variant="primary" onClick={() => setMode({ name: "load" })} testId="add-policy">
            {p.addPolicy}
          </PillButton>
        </div>
      )}

      {policies && policies.length > 0 && (
        <div class="insurance-policies" data-testid="insurance-policies">
          {policies.map((policy) => (
            <PolicyPassport key={policy.policy_id} policy={policy} ledger={ledger} testId="policy-passport" />
          ))}
        </div>
      )}

      {policies && policies.length > 0 && (
        <PillButton variant="secondary" onClick={() => setMode({ name: "load" })} testId="add-another-policy">
          {p.addPolicy}
        </PillButton>
      )}

      <PaperTile testId="insurance-ledger-link">
        <nav class="place-rows" aria-label={s.record.ledger}>
          <button type="button" class="place-row" onClick={() => go({ name: "record", at: { name: "ledger" } })} data-testid="open-ledger">
            <Icon name="ledger" />
            <span class="place-word">{s.record.ledger}</span>
            <Icon name="chevron" />
          </button>
        </nav>
      </PaperTile>

      <ProposePolicySheet
        open={proposing !== null}
        suggested={proposing ? confirmedPolicyFields(proposing.fields) : { insurer: null, policyNumber: null, plan: null, startDate: null }}
        onClose={() => setProposing(null)}
        onSaved={() => {
          setProposing(null);
          refresh();
        }}
      />
    </Shell>
  );
}
