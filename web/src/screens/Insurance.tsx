import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { PolicyOut } from "../api/types";
import { go } from "../flow";
import { profile, token } from "../store/session";
import { fill, LOCALE, language, t } from "../strings";
import { dateLine } from "../today/model";
import { Header, Notice, Tile } from "../ui/components";
import { Shell } from "./Shell";

/** Profile's Insurance row (E13-03, `GET /profiles/{id}/insurance/policies`): every policy on
 *  his profile, newest of each lineage, in plain words — the policy list only. The Ledger
 *  (claim amounts, #260) is a later screen; this one names what he is covered under, what it
 *  covers, when it renews and when the next payment is due, nothing invented. Reached only by
 *  a key that opens `Scope.MONEY` (`ProfileNav`'s own gate, same as "Insurance letters"). */
export function InsuranceScreen(): JSX.Element {
  const s = t();
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";
  const locale = LOCALE[language.value];
  const [policies, setPolicies] = useState<PolicyOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const bearer = token.value;
    const at = profile.value;
    if (!bearer || !at) return;
    nura.policies(bearer, at.profile_id).then(setPolicies, (failure: unknown) => {
      setPolicies([]);
      setError(failure);
    });
  }, [papers?.profile_id]);

  return (
    <Shell tab="profile" testId="insurance-screen">
      <Header title={owner ? s.insurance.title : fill(s.insurance.titleOther, { patient: name })} onBack={() => go({ name: "profile" })} />
      <Notice error={error} />
      {policies && policies.length === 0 && !error && (
        <Tile paper testId="insurance-none">
          <p>{owner ? s.insurance.none : fill(s.insurance.noneOther, { patient: name })}</p>
        </Tile>
      )}
      {policies?.map((policy) => <PolicyTile key={policy.policy_id} policy={policy} locale={locale} />)}
    </Shell>
  );
}

function PolicyTile({ policy, locale }: { policy: PolicyOut; locale: string }): JSX.Element {
  const s = t();
  return (
    <Tile paper testId="policy">
      <h2 class="title">{policy.insurer_name}</h2>
      <p class="caption">{s.insurance.type[policy.policy_type]}</p>
      <p>{s.insurance.status[policy.status]}</p>
      {policy.covers && <p>{fill(s.insurance.covers, { value: policy.covers })}</p>}
      {policy.renewal_date && <p>{fill(s.insurance.renews, { date: dateLine(new Date(policy.renewal_date), locale) })}</p>}
      {policy.premium_due_date && <p>{fill(s.insurance.premiumDue, { date: dateLine(new Date(policy.premium_due_date), locale) })}</p>}
      {policy.policy_reference && <p class="source-line">{fill(s.insurance.reference, { reference: policy.policy_reference })}</p>}
    </Tile>
  );
}
