import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { LedgerOut, PolicyOut, ReviewCardOut } from "../api/types";
import { go, openMe } from "../flow";
import { LoadPolicyFlow } from "../insurance/LoadPolicy";
import { PolicyPassport } from "../insurance/PolicyPassport";
import { ProposePolicySheet } from "../insurance/ProposePolicy";
import { confirmedPolicyFields } from "../insurance/model";
import { profile, token } from "../store/session";
import { fill, language, t } from "../strings";
import "../ui/insurance.css";
import { Notice, Tile } from "../ui/components";
import { focusHeading } from "../ui/focus";
import { Icon, Orb, PaperTile, PillButton, SoftText } from "../ui/kit";
import { Shell } from "./Shell";

type Mode = { name: "passport" } | { name: "load" };

const EMPTY_SUGGESTED = {
  insurer: null,
  policyNumber: null,
  plan: null,
  startDate: null,
  endDate: null,
  waitingPeriod: null,
  claimsContact: null,
  coverageItems: [],
  coverageItemsCut: false,
  excludes: [],
  excludesCut: false,
  benefits: [],
  benefitsCut: false,
  claimSteps: [],
  claimStepsCut: false,
};

/** The compact one-row header (item 7, the fix for the ~290px of chrome the first pass burned
 *  before any content): back chevron, the ONE h1, the same `open-me` door every compact
 *  header now keeps (`Ask.tsx`'s own `AskHeader`, the pattern this follows). */
function InsuranceHeader({ title, onBack, backLabel, meLabel }: { title: string; onBack: () => void; backLabel: string; meLabel: string }): JSX.Element {
  return (
    <header class="shell-head board-top-bar" data-testid="insurance-top-bar">
      <span class="head-start">
        <button type="button" class="head-button" aria-label={backLabel} onClick={onBack} data-testid="insurance-back">
          <Icon name="back" />
        </button>
      </span>
      <span class="head-mid">
        <h1 class="title top-bar-title">{title}</h1>
      </span>
      <span class="head-end">
        <button type="button" class="head-button" aria-label={meLabel} aria-haspopup="dialog" onClick={openMe} data-testid="open-me">
          <Icon name="menu" />
        </button>
      </span>
    </header>
  );
}

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

  // "See the policy itself" (item 9): the same audited artifact route a reopened paper
  // already uses (`Papers.tsx`'s own `seeItself`), read by the review card the essentials
  // came from — no new route, no new scope.
  const seeItself = async (reviewCardId: string): Promise<void> => {
    setError(null);
    try {
      const bearer = token.value;
      const at = profile.value;
      if (!bearer || !at) return;
      const blob = await nura.reviewCardArtifact(bearer, at.profile_id, reviewCardId);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      setError(failure);
    }
  };

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
    <Shell
      tab="profile"
      testId="insurance-screen"
      header={
        <InsuranceHeader
          title={owner ? s.insurance.title : fill(s.insurance.titleOther, { patient: name })}
          onBack={() => go({ name: "profile" })}
          backLabel={s.shell.back}
          meLabel={s.tabs.me}
        />
      }
    >
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
            <PolicyPassport key={policy.policy_id} policy={policy} ledger={ledger} onSeeItself={seeItself} testId="policy-passport" />
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
        suggested={proposing ? confirmedPolicyFields(proposing.fields) : EMPTY_SUGGESTED}
        cardId={proposing?.card_id ?? null}
        onClose={() => setProposing(null)}
        onSaved={() => {
          setProposing(null);
          refresh();
        }}
      />
    </Shell>
  );
}
