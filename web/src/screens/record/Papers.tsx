import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ReviewCardOut } from "../../api/types";
import { go } from "../../flow";
import { paperDate } from "../../onboarding/dates";
import { facilityField, kindTitle, valueText } from "../../onboarding/review";
import { groupPapersByYear, paperStateChip } from "../../record/model";
import { profile } from "../../store/session";
import { fill, language, LOCALE, t, type Strings } from "../../strings";
import { Notice, Pill, Tile } from "../../ui/components";
import { ConnectionRow, Flag } from "../../ui/kit";
import { AddReport } from "../HomeParts";
import { ReviewStep } from "../onboarding/Records";
import { ReportTable } from "../onboarding/ReportTable";
import { Paged, RecordFrame, recordNote, session, takeNote, toRecord, useDateOf, useRead } from "./parts";

/** "Your papers" (E02-07 library part B): every paper he has ever added, newest first — the
 *  ones still waiting for his yes exactly as before, and now the ones he has already checked
 *  too, so there is somewhere to go back and look. Nothing new was needed of the backend to
 *  list or reopen them (`GET /review-cards` already returns every card); only the paper
 *  itself, behind "See the paper itself" on a reopened one, needed a route. */

/** One paper's state chip: coloured when it is a judgement (`Flag`), plain text for "Read",
 *  which is never one. */
function PaperChip({ card, s }: { card: ReviewCardOut; s: Strings }): JSX.Element {
  const chip = paperStateChip(card, s);
  if (chip.state) {
    return (
      <Flag state={chip.state} testId="paper-chip">
        {chip.label}
      </Flag>
    );
  }
  return (
    <span class="caption" data-testid="paper-chip">
      {chip.label}
    </span>
  );
}

/** One row of the list: the kind in plain words, the date on the paper and the facility, and
 *  the state chip — reused by the Health tab's short "Your papers" section and the full list
 *  here (E02-07 library part B #2). */
export function PaperRow({ card, dateOf, onOpen }: { card: ReviewCardOut; dateOf: (iso: string) => string; onOpen: () => void }): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const facility = facilityField(card);
  const facilityText = facility ? valueText(facility.value) : null;
  const dateText = card.document_date ? paperDate(card.document_date, LOCALE[language.value]) : dateOf(card.created_at);
  const line = facilityText ? fill(r.dateAndFacility, { date: dateText, facility: facilityText }) : dateText;
  return (
    <ConnectionRow
      name={kindTitle(card.document_kind, s)}
      line={line}
      trailing={<PaperChip card={card} s={s} />}
      onClick={onOpen}
      testId={card.confirmed_at ? "checked-paper" : "waiting-paper"}
      attrs={{ "data-card-id": card.card_id }}
    />
  );
}

/** The full list, under the Record (library part B #2): every paper newest first, grouped by
 *  year once there are enough to need it, an honest empty state with the way to add one, and
 *  a paper still waiting opens the review exactly as before — the one that is already
 *  checked opens read-only. */
export function PapersScreen(): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const [note] = useState(takeNote);
  const { data: cards, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.reviewCards(bearer, profileId, false);
  }, []);
  const groups = cards ? groupPapersByYear(cards) : [];
  const openRow = (card: ReviewCardOut) => () => toRecord({ name: "paper", card });
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const patient = papers?.display_name ?? "";
  const title = owner ? s.record.papers : fill(s.record.papersOther, { patient });
  const empty = owner ? s.record.papersNone : fill(s.record.papersNoneOther, { patient });

  return (
    <RecordFrame title={title} back={{ name: "hub" }} testId="record-papers">
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
          <p>{empty}</p>
          <AddReport papers={profile.value} />
        </Tile>
      )}
      {cards && cards.length > 0 && groups.length === 0 && (
        <Paged items={cards} render={(card) => <PaperRow key={card.card_id} card={card} dateOf={dateOf} onOpen={openRow(card)} />} />
      )}
      {cards && groups.length > 0 && (
        <div data-testid="papers-by-year">
          {groups.map((group) => (
            <section key={group.year} data-testid="paper-year-group">
              <p class="kick" data-testid="paper-year">
                {fill(s.record.paperYearGroup, { year: group.year })}
              </p>
              {group.cards.map((card) => (
                <PaperRow key={card.card_id} card={card} dateOf={dateOf} onOpen={openRow(card)} />
              ))}
            </section>
          ))}
        </div>
      )}
    </RecordFrame>
  );
}

/** One paper: still waiting for his yes, the review card exactly as before; already checked,
 *  reopened read-only (library part B #3). */
export function PaperScreen({ card }: { card: ReviewCardOut }): JSX.Element {
  const s = t();
  if (card.confirmed_at) return <ReopenedPaperScreen card={card} />;
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

/** A paper he already checked, opened again to look at, never to redo (library part B #3):
 *  the same report table, read-only — no "Looks right", no edit sheets, nothing tappable —
 *  with "You checked this on {date}" where the header's actions were, "See the paper itself"
 *  (the original photo or PDF, through the one small additive route this library adds) and
 *  "Ask about this paper" (a draft into Ask, naming the paper, never sent on its own). */
function ReopenedPaperScreen({ card }: { card: ReviewCardOut }): JSX.Element {
  const s = t();
  const r = s.onboarding.records;
  const locale = LOCALE[language.value];
  const papers = profile.value;
  const owner = papers?.standing === "owner";
  const name = papers?.display_name ?? "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const checkedOnDate = paperDate(card.confirmed_at ?? card.created_at, locale);
  const documentDateText = card.document_date ? paperDate(card.document_date, locale) : null;

  const seeItself = async () => {
    setBusy(true);
    setError(null);
    try {
      const { bearer, profileId } = session();
      const blob = await nura.reviewCardArtifact(bearer, profileId, card.card_id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const askAbout = () => {
    const paper = kindTitle(card.document_kind, s).toLowerCase();
    const date = documentDateText ?? checkedOnDate;
    go({ name: "ask", question: fill(s.record.paperAskPrefill, { paper, date }), draft: true });
  };

  return (
    <main class="screen" data-card-id={card.card_id} data-testid="reopened-paper">
      <ReportTable
        card={card}
        edits={{}}
        onEdit={() => {}}
        waiting={[]}
        documentDateText={documentDateText}
        dateText={paperDate(card.created_at, locale)}
        testId="review-card"
        readOnly={{
          checkedOnText: fill(owner ? r.checkedOn : r.checkedOnOther, { date: checkedOnDate, patient: name }),
          actions: (
            <>
              <button type="button" class="btn" onClick={() => void seeItself()} disabled={busy} data-testid="see-paper-itself">
                {r.seePaperItself}
              </button>
              <button type="button" class="btn" onClick={askAbout} data-testid="ask-about-paper">
                {r.askAboutPaper}
              </button>
            </>
          ),
        }}
      />
      <Notice error={error} />
      <Pill quiet onClick={() => toRecord({ name: "papers" })} testId="record-back">
        {s.record.back}
      </Pill>
    </main>
  );
}
