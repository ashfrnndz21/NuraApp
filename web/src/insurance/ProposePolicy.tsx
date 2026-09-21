import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { PolicyOut, PolicyType } from "../api/types";
import { fieldLabel } from "../onboarding/review";
import { session } from "../screens/record/parts";
import { t } from "../strings";
import { Notice } from "../ui/components";
import { ActionSheet, PillButton } from "../ui/kit";
import type { ConfirmedPolicyFields } from "./model";
import { sanitizeDisplayText } from "./model";

const POLICY_TYPES: readonly PolicyType[] = ["hospital", "outpatient", "critical_illness", "government_scheme"];

/** "Add this as your policy" (package 12a, item 1): the review card's own fields never become
 *  a `Policy` row by themselves (`app.insurance.policy`'s own module docstring: "that path
 *  always writes Facts, never a policy row directly") — this is the separate proposal, pre-
 *  filled from what was just confirmed, that a person still has to say yes to before anything
 *  joins the passport. Every field here is still his to change; nothing is written until
 *  `Save` really finishes (`ThreeStateButton`, inside `ActionSheet`). */
export function ProposePolicySheet({
  open,
  suggested,
  onClose,
  onSaved,
}: {
  open: boolean;
  suggested: ConfirmedPolicyFields;
  onClose: () => void;
  onSaved: (policy: PolicyOut) => void;
}): JSX.Element {
  const s = t();
  const p = s.insurance.passport;
  const [insurerName, setInsurerName] = useState(suggested.insurer ?? "");
  const [policyReference, setPolicyReference] = useState(suggested.policyNumber ?? "");
  const [covers, setCovers] = useState(suggested.plan ?? "");
  const [startDate, setStartDate] = useState(suggested.startDate ?? "");
  const [policyType, setPolicyType] = useState<PolicyType>("hospital");
  const [guaranteeLetter, setGuaranteeLetter] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const save = async (): Promise<void> => {
    setError(null);
    const { bearer, profileId } = session();
    const draft = {
      insurer_name: sanitizeDisplayText(insurerName, 120),
      policy_reference: policyReference.trim() ? sanitizeDisplayText(policyReference, 40) : null,
      policy_type: policyType,
      covered: null,
      covers: covers.trim() ? sanitizeDisplayText(covers, 400) : null,
      start_date: /^\d{4}-\d{2}-\d{2}$/.test(startDate.trim()) ? startDate.trim() : null,
      renewal_date: null,
      premium_due_date: null,
      status: "active" as const,
      guarantee_letter: guaranteeLetter,
    };
    try {
      const yes = await nura.mintPolicyYes(bearer, profileId, draft);
      const written = await nura.writePolicy(bearer, profileId, draft, yes.confirmation_id);
      onSaved(written);
    } catch (failure) {
      // Never a silent revert to idle: a refusal (a name too long, a role that cannot set a
      // policy) is named, the same `Notice` every other refusal in the app already uses.
      setError(failure);
      throw failure;
    }
  };

  return (
    <ActionSheet
      open={open}
      title={p.proposeTitle}
      sub={p.proposeSub}
      notNowLabel={s.onboarding.back}
      onClose={onClose}
      cta={{ label: p.proposeCta, busyLabel: p.proposeCtaBusy, doneLabel: p.proposeCtaDone, onAct: save }}
      testId="propose-policy-sheet"
    >
      <Notice error={error} />
      <div class="insurance-propose-fields">
      <label class="field-label" htmlFor="policy-insurer">
        {fieldLabel({ subject: "insurance_policy", attribute: "insurer" }, s)}
      </label>
      <input
        id="policy-insurer"
        type="text"
        value={insurerName}
        onInput={(e) => setInsurerName((e.target as HTMLInputElement).value)}
        maxLength={120}
        data-testid="propose-insurer"
      />
      <label class="field-label" htmlFor="policy-reference">
        {fieldLabel({ subject: "insurance_policy", attribute: "policy_number" }, s)}
      </label>
      <input
        id="policy-reference"
        type="text"
        value={policyReference}
        onInput={(e) => setPolicyReference((e.target as HTMLInputElement).value)}
        maxLength={40}
        data-testid="propose-reference"
      />
      <label class="field-label" htmlFor="policy-covers">
        {p.coversTitle}
      </label>
      <input
        id="policy-covers"
        type="text"
        value={covers}
        onInput={(e) => setCovers((e.target as HTMLInputElement).value)}
        maxLength={400}
        data-testid="propose-covers"
      />
      <label class="field-label" htmlFor="policy-start-date">
        {fieldLabel({ subject: "insurance_policy", attribute: "start_date" }, s)}
      </label>
      <input
        id="policy-start-date"
        type="text"
        inputMode="numeric"
        placeholder="YYYY-MM-DD"
        value={startDate}
        onInput={(e) => setStartDate((e.target as HTMLInputElement).value)}
        data-testid="propose-start-date"
      />
      <span class="field-label" id="policy-type-label">
        {p.policyTypeLabel}
      </span>
      <div class="pill-row" role="group" aria-labelledby="policy-type-label">
        {POLICY_TYPES.map((kind) => (
          <PillButton key={kind} compact variant="secondary" pressed={policyType === kind} onClick={() => setPolicyType(kind)} testId={`propose-type-${kind}`}>
            {s.insurance.type[kind]}
          </PillButton>
        ))}
      </div>
      <PillButton compact variant={guaranteeLetter ? "primary" : "secondary"} pressed={guaranteeLetter} onClick={() => setGuaranteeLetter(!guaranteeLetter)} testId="propose-guarantee-letter">
        {p.worksByGuaranteeLetter}
      </PillButton>
      </div>
    </ActionSheet>
  );
}
