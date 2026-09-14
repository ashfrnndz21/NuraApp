import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { DocumentTag } from "../../api/familyTypes";
import { base64OfBytes, wallTime } from "../../family/model";
import { Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, NoticeAt, s, useAct, useHere, useRead } from "./common";

const TAGS: readonly DocumentTag[] = ["lpa", "medical_letter", "consent_form"];

/** E12-09: the papers behind the family list — an LPA, a doctor's letter, a consent form —
 *  kept by reference, each with what it backs and whether that is still on; and one more,
 *  a PDF or a photo, tagged. Owner and chief. */
export function DocumentsPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [tag, setTag] = useState<DocumentTag>("lpa");
  const list = useRead(here ? () => family.documents(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  const [added, setAdded] = useState<Awaited<ReturnType<typeof family.documents>> | null>(null);
  if (!here) return null;
  const shown = added ?? list.value;
  const upload = (file: File) =>
    a.act("upload", async () => {
      const data = base64OfBytes(await file.arrayBuffer());
      setAdded(await family.addDocument(here.bearer, here.papers.profile_id, { data, content_type: file.type || "application/pdf", captured_at: new Date().toISOString(), tag }));
    });
  return (
    <FamilyPage title={words.documents} part="documents">
      <Notice error={list.error} />
      {shown?.map((doc) => (
        <Tile paper key={doc.artifact_id} testId="document">
          <p>{doc.tag ? words.tags[doc.tag] : doc.content_type}</p>
          <p class="label">{wallTime(doc.captured_at, here.locale)}</p>
          {doc.backs.map((backing) => (
            <p key={backing.id} class="label" data-testid="document-backs">
              {(words.backs as Record<string, string>)[backing.kind] ?? backing.kind} <span class="chip">{backing.active ? words.stillOn : words.stoppedChip}</span>
            </p>
          ))}
        </Tile>
      ))}
      <Tile paper testId="add-document">
        <h2 class="title">{words.addDocument}</h2>
        <p class="label">{words.whatPaper}</p>
        <div class="choices" role="group" aria-label={words.whatPaper}>
          {TAGS.map((each) => (
            <Pill key={each} chosen={tag === each} onClick={() => setTag(each)} testId={`tag-${each}`}>
              {words.tags[each]}
            </Pill>
          ))}
        </div>
        <label class="pill" data-testid="choose-document">
          {words.chooseDocument}
          <input
            type="file"
            accept="application/pdf,image/*"
            onChange={(event) => {
              const input = event.target as HTMLInputElement;
              const file = input.files?.[0];
              if (file) void upload(file);
              input.value = "";
            }}
          />
        </label>
        <NoticeAt act={a} where="upload" />
      </Tile>
    </FamilyPage>
  );
}
