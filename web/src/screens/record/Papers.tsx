import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ReviewCardOut } from "../../api/types";
import { kindLine } from "../../onboarding/review";
import { fill, t } from "../../strings";
import { Notice, Pill, Tile } from "../../ui/components";
import { ReviewStep } from "../onboarding/Records";
import { Paged, RecordFrame, recordNote, session, takeNote, toRecord, useDateOf, useRead } from "./parts";

/** The papers waiting for his yes (E02-04): a photo or a PDF forwarded on WhatsApp files
 *  itself as a review card; here it is confirmed, on the same review card as onboarding's. */
export function PapersScreen(): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const [note] = useState(takeNote);
  const { data: cards, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.reviewCards(bearer, profileId, true);
  }, []);
  return (
    <RecordFrame title={s.record.papers} back={{ name: "hub" }} testId="record-papers">
      {note && (
        <Tile paper settled role="status" testId="record-note">
          {note.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </Tile>
      )}
      <Notice error={error} />
      {cards && cards.length === 0 && (
        <Tile paper testId="no-papers">
          <p>{s.record.papersNone}</p>
        </Tile>
      )}
      {cards && (
        <Paged
          items={cards}
          render={(card) => (
            <Tile paper key={card.card_id} testId="waiting-paper">
              <p data-card-id={card.card_id}>{kindLine(card.document_kind, s)}</p>
              <p class="caption">{fill(s.record.paperFrom, { date: dateOf(card.created_at) })}</p>
              <Pill plum onClick={() => toRecord({ name: "paper", card })} testId="open-paper">
                {s.record.paperOpen}
              </Pill>
            </Tile>
          )}
        />
      )}
    </RecordFrame>
  );
}

/** One waiting paper, on the review card: each line as read, how sure, a correction, and one
 *  yes. Back to the list after, saying it was written down. */
export function PaperScreen({ card }: { card: ReviewCardOut }): JSX.Element {
  const s = t();
  return (
    <ReviewStep
      key={card.card_id}
      card={card}
      onBack={() => toRecord({ name: "papers" })}
      onDone={() => {
        recordNote.value = [s.onboarding.records.saved];
        toRecord({ name: "papers" });
      }}
    />
  );
}
