import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { DocumentOut, DocumentTag, ReviewCardOut } from "../../api/types";
import { base64Of, isPdf } from "../../onboarding/actions";
import { kindLine } from "../../onboarding/review";
import { backsLines } from "../../record/model";
import { fill, t } from "../../strings";
import { Notice, Pill, Tile } from "../../ui/components";
import { Capture } from "../onboarding/parts";
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

const TAGS: readonly DocumentTag[] = ["lpa", "medical_letter", "consent_form"];

/** The family's papers (E12-09): the lasting power of attorney, a doctor's letter, a signed
 *  form — kept by reference, with what each one backs. The chief adds one here. */
export function DocumentsScreen(): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const [tag, setTag] = useState<DocumentTag | null>(null);
  const [kept, setKept] = useState<DocumentOut[] | null>(null);
  const [added, setAdded] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.documents(bearer, profileId);
  }, []);
  const documents = kept ?? data;

  const upload = async (file: File) => {
    if (!tag) return;
    setBusy(true);
    setFailure(null);
    setAdded(false);
    try {
      const { bearer, profileId } = session();
      const bytes = await base64Of(file);
      const type = isPdf(file) ? "application/pdf" : file.type || "application/octet-stream";
      setKept(await nura.addDocument(bearer, profileId, bytes, type, new Date(file.lastModified || Date.now()).toISOString(), tag));
      setAdded(true);
      setTag(null);
    } catch (refused) {
      setFailure(refused);
    } finally {
      setBusy(false);
    }
  };

  return (
    <RecordFrame title={s.record.documents} back={{ name: "hub" }} testId="record-documents">
      <Notice error={error} />
      {added && (
        <Tile paper settled role="status" testId="document-added">
          <p>{s.record.documentAdded}</p>
        </Tile>
      )}
      {documents && documents.length === 0 && (
        <Tile paper testId="no-documents">
          <p>{s.record.noDocuments}</p>
        </Tile>
      )}
      {documents && (
        <Paged
          items={documents}
          render={(document) => (
            <Tile paper key={document.artifact_id} testId="document">
              <h2 class="title">{document.tag ? s.record.tags[document.tag] : fill(s.record.paperOn, { date: dateOf(document.captured_at) })}</h2>
              <p>{fill(s.record.keptOn, { date: dateOf(document.added_at ?? document.captured_at) })}</p>
              {backsLines(document, s).map((line, index) => (
                <p key={index} data-testid="backs">
                  {line}
                </p>
              ))}
            </Tile>
          )}
        />
      )}
      <Tile paper testId="add-document">
        <p>{s.record.documentsLead}</p>
        <p class="label">{s.record.chooseKind}</p>
        {TAGS.map((each) => (
          <Pill key={each} chosen={tag === each} onClick={() => setTag(each)} testId={`tag-${each}`}>
            {s.record.tags[each]}
          </Pill>
        ))}
        {tag && <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={s.onboarding.records.photo} />}
      </Tile>
      <Notice error={failure} />
    </RecordFrame>
  );
}
