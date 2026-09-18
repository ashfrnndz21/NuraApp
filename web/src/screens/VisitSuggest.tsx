import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { VisitProposalOut } from "../api/types";
import { go } from "../flow";
import { profile, token } from "../store/session";
import { language, t } from "../strings";
import { IconBadge, PillButton, TintCard } from "../ui/kit";
import { suggestionLine, suggestionWhy } from "../visits/model";
import { useRead } from "./family/common";

/** T2's "Nura suggests" rows (Health's Coming up, Connect's next-visit tile): every visit the
 *  planner proposes right now, cited, never booked and never a message to a clinic. "Book it"
 *  opens the visits tab with the proposal's own day and purpose to hand; "Not now" hides it
 *  for 90 days, his own tap the yes for that (`GET/POST …/visits/proposed`,
 *  `app.reasoning.visits.planner`). Nothing renders while there is nothing suggested — an
 *  empty list is silence, not a stub row. */
export function VisitSuggestions({ owner, name }: { owner: boolean; name: string }): JSX.Element | null {
  const bearer = token.value;
  const papers = profile.value;
  const read = useRead(
    bearer && papers ? () => nura.visitsProposed(bearer, papers.profile_id, language.value) : null,
    [bearer, papers?.profile_id, language.value],
  );
  const proposals = read.value?.proposals ?? [];
  if (proposals.length === 0) return null;
  return (
    <>
      {proposals.map((proposal) => (
        <SuggestionRow key={proposal.proposal_id} proposal={proposal} owner={owner} name={name} onChanged={read.reload} />
      ))}
    </>
  );
}

function SuggestionRow({
  proposal,
  owner,
  name,
  onChanged,
}: {
  proposal: VisitProposalOut;
  owner: boolean;
  name: string;
  onChanged: () => Promise<void>;
}): JSX.Element {
  const s = t();
  const [busy, setBusy] = useState(false);
  const bearer = token.value;
  const papers = profile.value;
  const decline = async () => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    try {
      await nura.declineVisitProposal(bearer, papers.profile_id, proposal.proposal_id);
      await onChanged();
    } finally {
      setBusy(false);
    }
  };
  return (
    <TintCard tint="peach" testId="visit-suggestion" extra="visit-card">
      <div class="card-row">
        <IconBadge icon="calendar" tint="paper" />
        <p class="grow card-line">{suggestionLine(proposal, owner, name, s)}</p>
      </div>
      <p class="source-line">{suggestionWhy(proposal.source, s)}</p>
      <div class="call-actions">
        <PillButton variant="primary" compact icon="calendar" onClick={() => go({ name: "visits" })} testId="suggestion-book">
          {s.visitSuggest.bookIt}
        </PillButton>
        <PillButton variant="secondary" compact onClick={() => void decline()} disabled={busy} testId="suggestion-not-now">
          {s.visitSuggest.notNow}
        </PillButton>
      </div>
    </TintCard>
  );
}
