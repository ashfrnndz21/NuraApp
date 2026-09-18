import type { VisitProposalOut, VisitSource } from "../api/types";
import { fill, type Strings } from "../strings";

/** T2's "Nura suggests" rows (Health's Coming up, Connect's next-visit tile): what the
 *  planner found (`GET /profiles/{id}/visits/proposed`), never a booking of its own. This
 *  module is only the two lines a row needs worked out on the phone; the backend's own words
 *  (`purpose`, plain-words verified, in his voice) are read as they are for the owner, and
 *  never shown to a caregiver's key as they are — she reads `visitSuggest.rowOther` by name
 *  instead, the same rule every other "his own words vs about him by name" line follows. */

const WHY_KEY: Record<VisitSource, keyof Strings["visitSuggest"]> = {
  follow_up: "followUpWhy",
  medicine_review: "medicineReviewWhy",
  test_coming: "testComingWhy",
  screening_due: "screeningDueWhy",
};

/** The row's headline: his own words, read as the backend wrote them, or — on a caregiver's
 *  key — the screen's own line, by name. */
export function suggestionLine(proposal: VisitProposalOut, owner: boolean, name: string, s: Strings): string {
  return owner ? proposal.purpose : fill(s.visitSuggest.rowOther, { name });
}

/** Why this proposal is here, named by its source — one of the four the planner reads
 *  (`app.reasoning.visits.planner.VisitSource`), never his own free words. */
export function suggestionWhy(source: VisitSource, s: Strings): string {
  return s.visitSuggest[WHY_KEY[source]];
}
