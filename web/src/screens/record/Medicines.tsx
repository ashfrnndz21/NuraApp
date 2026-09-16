import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { LabelIn, LineOut, MedicineDraftOut, MoreOut, OrderPreviewOut } from "../../api/types";
import { browserAudio } from "../../feed/playback";
import { base64Of, isPdf } from "../../onboarding/actions";
import { StoryVoice } from "../../record/storyVoice";
import { speak } from "../../speech/speak";
import { confidenceLine, countOf, labelFromCard, lineQuestions, outcomeLine, reorderActions, severityLine, tidyLabel } from "../../record/model";
import { density } from "../../store/session";
import { fill, language, t } from "../../strings";
import { Field, Hear, Notice, Pill, Tile } from "../../ui/components";
import { Capture } from "../onboarding/parts";
import { Paged, RecordFrame, recordNote, session, takeNote, toRecord, upperFirst, useRead } from "./parts";

/** His medicines (E04-01): each line with where it came from and how sure Nura is, the count
 *  and — at the threshold — the reorder card's two buttons (E04-05), in the backend's words. */
export function MedicinesScreen({ start }: { start: number }): JSX.Element {
  const s = t();
  const [note] = useState(takeNote);
  const [said, setSaid] = useState<string[] | null>(null);
  // The line the family was asked about: its button stays down, so one yes is one task.
  const [askedFor, setAskedFor] = useState<string | null>(null);
  // What he reads before his yes: who will be asked, for which medicine (the backend's words).
  const [preview, setPreview] = useState<OrderPreviewOut | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: lines, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.medicines(bearer, profileId, language.value);
  }, [language.value]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setFailure(null);
    try {
      await work();
    } catch (refused) {
      setFailure(refused);
    } finally {
      setBusy(false);
    }
  };

  /** "Ask the family to order.": first the preview — who Nura will ask, and for what. If the
   *  family was already asked today, the backend's line says so and there is nothing to add. */
  const ask = (line: LineOut) =>
    run(async () => {
      setSaid(null);
      const { bearer, profileId } = session();
      const shown = await nura.orderPreview(bearer, profileId, line.line_id, language.value);
      if (shown.already_asked) {
        setSaid(shown.lines);
        setAskedFor(line.line_id);
        return;
      }
      setPreview(shown);
    });

  /** His yes, for exactly the person and the line the preview named; the backend says who
   *  does it next. */
  const yes = (shown: OrderPreviewOut) =>
    run(async () => {
      const { bearer, profileId } = session();
      const minted = await nura.mintOrder(bearer, profileId, shown.line_id, shown.asked_person_id);
      const asked = await nura.askToOrder(bearer, profileId, shown.line_id, minted.confirmation_id, language.value);
      setPreview(null);
      setSaid(asked.lines);
      setAskedFor(shown.line_id);
    });

  return (
    <RecordFrame title={s.record.medicines} back={{ name: "hub" }} testId="record-medicines">
      {note && (
        <Tile paper settled role="status" testId="record-note">
          {note.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </Tile>
      )}
      {said && (
        <Tile paper settled role="status" testId="asked">
          {said.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </Tile>
      )}
      <Notice error={error ?? failure} />
      {lines && lines.length === 0 && (
        <Tile paper testId="no-medicines">
          <h2 class="title">{s.today.noMedicines}</h2>
          <p>{s.today.noMedicinesSub}</p>
        </Tile>
      )}
      {lines && (
        <Paged
          items={lines}
          start={start}
          render={(line) => (
            <LineCard
              key={line.line_id}
              line={line}
              busy={busy || askedFor === line.line_id}
              preview={preview?.line_id === line.line_id ? preview : null}
              onAsk={() => void ask(line)}
              onYes={(shown) => void yes(shown)}
              onNo={() => setPreview(null)}
            />
          )}
        />
      )}
      <Pill onClick={() => toRecord({ name: "add" })} testId="add-medicine">
        {s.record.add}
      </Pill>
    </RecordFrame>
  );
}

interface LineCardProps {
  line: LineOut;
  busy: boolean;
  /** The preview of "Ask the family to order." for this line, waiting for his yes. */
  preview: OrderPreviewOut | null;
  onAsk: () => void;
  onYes: (shown: OrderPreviewOut) => void;
  onNo: () => void;
}

function LineCard({ line, busy, preview, onAsk, onYes, onNo }: LineCardProps): JSX.Element {
  const s = t();
  const actions = reorderActions(line);
  const counted = [...(line.count?.lines ?? []), ...(line.count?.reorder ?? [])];
  const questions = lineQuestions(line);
  const sure = confidenceLine(line, s);
  const twice = (line.duplicate_of?.length ?? 0) > 0;
  const patient = density() === "patient";
  return (
    <Tile paper={patient || actions !== null} glass={!patient && actions === null} testId="medicine-line">
      <h2 class="title">{upperFirst(line.name)}</h2>
      <p class="caption" data-testid="chemical">
        {line.generic} {line.strength}
      </p>
      {counted.length > 0 && (
        <div class="lines" data-testid="count">
          {counted.map((text, index) => (
            <p key={index}>{text}</p>
          ))}
        </div>
      )}
      {questions.length > 0 && (
        <div class="lines" data-testid="questions">
          {questions.map((text, index) => (
            <p key={index}>{text}</p>
          ))}
        </div>
      )}
      <p data-testid="confidence">{sure}</p>
      {/* The register's own match, not his yes (#206): only said when Nura had to match by
          name alone, without a strength to check it against — the ordinary case, an exact
          strength match too, says nothing extra here. */}
      {(line.registry_confidence ?? 1) < 1 && (
        <div class="lines" data-testid="registry-confidence">
          {s.record.matchByNameOnly.map((text, index) => (
            <p key={index}>{text}</p>
          ))}
        </div>
      )}
      {twice && <p data-testid="duplicate">{s.record.twice}</p>}
      <p class="provenance" data-testid="source">
        {line.source}
      </p>
      {actions && !preview && (
        <>
          <Pill plum onClick={onAsk} disabled={busy} testId="ask-to-order">
            {actions.askToOrder}
          </Pill>
          <Pill onClick={() => toRecord({ name: "more", lineId: line.line_id })} testId="i-have-more">
            {actions.iHaveMore}
          </Pill>
        </>
      )}
      {preview && (
        <div class="lines" role="group" data-testid="order-preview">
          {preview.lines.map((text, index) => (
            <p key={index}>{text}</p>
          ))}
          <Pill plum onClick={() => onYes(preview)} disabled={busy} testId="order-yes">
            {s.record.orderYes}
          </Pill>
          <Pill quiet onClick={onNo} disabled={busy} testId="order-no">
            {s.record.orderNo}
          </Pill>
          <Hear lines={preview.lines} />
        </div>
      )}
      <Pill onClick={() => toRecord({ name: "story", lineId: line.line_id })} testId="open-story">
        {s.record.aboutIt}
      </Pill>
      <Hear lines={[upperFirst(line.name), ...counted, ...questions, sure, line.source]} />
    </Tile>
  );
}

/** The story of one medicine (E04-06): what it is for, how to take it, what to look out for,
 *  what to stay away from, if he forgets — in his language, the boundary last. Hear reads
 *  the backend's own script on the phone; nothing plays by itself. */
export function StoryScreen({ lineId }: { lineId: string }): JSX.Element {
  const s = t();
  const { data: story, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.story(bearer, profileId, lineId, language.value);
  }, [lineId, language.value]);
  // One voice note a part (E04-06), fetched when the story opens and played only on a tap.
  const voice = useMemo(
    () =>
      new StoryVoice({
        fetch: (part) => {
          const { bearer, profileId } = session();
          return nura.storyVoice(bearer, profileId, lineId, part, language.value);
        },
        audio: browserAudio,
        speak,
      }),
    [lineId, language.value],
  );
  useEffect(() => {
    if (story?.voice_parts) voice.warm(story.voice_parts);
  }, [story, voice]);
  useEffect(() => () => voice.stop(), [voice]);
  const sections: [string, string][] = [
    ["purpose", s.record.storyPurpose],
    ["how_to_take", s.record.storyHow],
    ["watch_out", s.record.storyWatch],
    ["avoid", s.record.storyAvoid],
    ["if_forgotten", s.record.storyForgot],
    ["doctor_question", s.record.storyAsk],
  ];
  return (
    <RecordFrame title={story ? upperFirst(story.name) : s.record.aboutIt} back={{ name: "medicines" }} testId="record-story">
      <Notice error={error} />
      {story && (
        <Tile paper testId="story">
          <p class="caption" data-testid="chemical">
            {story.generic} {story.strength}
          </p>
          {sections.map(([key, title]) => {
            const lines = story[key as "purpose"];
            if (lines.length === 0) return null;
            return (
              <div class="lines" key={key} data-testid={`story-${key}`}>
                <p class="label">{title}</p>
                {lines.map((line, index) => (
                  <p key={index}>{line}</p>
                ))}
                {story.voice_parts?.includes(key) && (
                  <HearPart
                    label={s.record.hearParts[key as keyof typeof s.record.hearParts]}
                    onHear={() =>
                      void voice.hear(key, {
                        // As the backend says the part: every part but what it is for ends on the boundary.
                        lines: key === "purpose" ? lines : [...lines, ...story.boundary],
                        language: language.value,
                      })
                    }
                    testId={`hear-${key}`}
                  />
                )}
              </div>
            );
          })}
          <div class="lines boundary" data-testid="boundary">
            {story.boundary.map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </div>
          {/* A backend with no voice notes yet: the whole story in the phone's voice. */}
          {!story.voice_parts?.length && <Hear lines={story.lines} />}
        </Tile>
      )}
    </RecordFrame>
  );
}

/** One part's Hear: the same button as every card's, naming the part it plays in one whole
 *  phrase of the catalogue a screen reader says ("Hear what to look out for"), never a
 *  label and a colon, and never assembled. */
function HearPart({ label, onHear, testId }: { label: string; onHear: () => void; testId: string }): JSX.Element {
  const s = t();
  return (
    <Pill quiet onClick={onHear} label={label} testId={testId}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 10v4h3l4 4V6L7 10H4z" />
        <path d="M15 9a4 4 0 0 1 0 6" />
        <path d="M17.5 6.5a8 8 0 0 1 0 11" />
      </svg>
      {s.today.hear}
    </Pill>
  );
}

type AddStep = "photo" | "label" | "check";

/** Add a medicine (E04-03): a label photo (or a file), the label as read — typed where Nura
 *  could not read it — then the backend's check before anything is saved: what it means for
 *  the list, and every interaction, the severity and both medicines named. His yes saves it;
 *  a refusal (a high-risk medicine without a label photo) is said in one sentence. */
export function AddMedicineScreen(): JSX.Element {
  const s = t();
  const [step, setStep] = useState<AddStep>("photo");
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [label, setLabel] = useState<LabelIn>({});
  const [draft, setDraft] = useState<MedicineDraftOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const upload = (file: File) =>
    run(async () => {
      const { bearer, profileId } = session();
      const data = await base64Of(file);
      const taken = new Date(file.lastModified || Date.now()).toISOString();
      const card = isPdf(file)
        ? await nura.addImport(bearer, profileId, data, "application/pdf", taken, "share")
        : await nura.addPhoto(bearer, profileId, data, file.type || "application/octet-stream", taken);
      setArtifactId(card.artifact_id);
      setLabel(labelFromCard(card));
      setStep("label");
    });

  const ready = tidyLabel(label);
  const check = () =>
    run(async () => {
      if (!ready || !artifactId) return;
      const { bearer, profileId } = session();
      setDraft(await nura.medicineDraft(bearer, profileId, ready, artifactId));
      setStep("check");
    });

  const save = () =>
    run(async () => {
      if (!ready || !artifactId) return;
      const { bearer, profileId } = session();
      const yes = await nura.mintMedicine(bearer, profileId, ready, artifactId);
      await nura.addMedicine(bearer, profileId, ready, artifactId, yes.confirmation_id);
      recordNote.value = [s.record.added];
      toRecord({ name: "medicines" });
    });

  const set = (key: keyof LabelIn) => (value: string) =>
    setLabel({ ...label, [key]: key === "quantity" ? (value.trim() === "" ? null : Number(value)) : value });

  return (
    <RecordFrame title={s.record.add} back={{ name: "medicines" }} testId="record-add">
      {step === "photo" && (
        <Tile paper testId="add-photo">
          <p>{s.record.addLead}</p>
          <p>{s.record.addLead2}</p>
          <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={s.onboarding.records.photo} />
        </Tile>
      )}
      {step === "label" && (
        <Tile paper testId="add-label">
          <p>{s.record.addLead2}</p>
          <Field name="generic" label={s.record.nameLabel} value={label.generic ?? ""} onInput={set("generic")} big />
          <Field name="strength" label={s.record.strengthLabel} value={label.strength ?? ""} onInput={set("strength")} big />
          <Field name="dose_text" label={s.record.howLabel} value={label.dose_text ?? ""} onInput={set("dose_text")} big />
          <p class="caption">{s.record.howHint}</p>
          <Field name="quantity" label={s.record.countLabel} value={label.quantity ? String(label.quantity) : ""} onInput={set("quantity")} inputMode="numeric" big maxLength={4} />
          <Field name="prescriber" label={s.record.doctorLabel} value={label.prescriber ?? ""} onInput={set("prescriber")} big />
          <Pill plum onClick={() => void check()} disabled={busy || !ready} testId="check-medicine">
            {s.record.checkIt}
          </Pill>
        </Tile>
      )}
      {step === "check" && draft && (
        <>
          <Tile paper testId="add-check">
            <h2 class="title">{s.record.flaggedTitle}</h2>
            <p data-testid="outcome">{outcomeLine(draft.outcome, s)}</p>
            <p class="caption" data-testid="chemical">
              {draft.match.brand} {draft.match.generic} {draft.match.strength}
            </p>
            {/* Only a new line is screened against the list (E04-03); a refill or a new amount
                is not, so "nothing goes badly" is said only where the licensed data was asked. */}
            {draft.outcome === "new_line" && draft.flagged.length === 0 && <p data-testid="no-interactions">{s.record.flaggedNone}</p>}
          </Tile>
          {draft.flagged.map((flag) => (
            <Tile paper key={flag.other_line_id + flag.text_id} testId="interaction">
              {/* A pair a pharmacist has not yet checked (E04-03) never shows a severity
                  nobody has verified: `flag.question` already asks him to check with a
                  pharmacist too, in place of the usual "matters a lot/matters" claim. */}
              {!flag.awaiting_review && <p data-testid="severity">{severityLine(flag.severity, s)}</p>}
              <div class="lines">
                {flag.question.map((line, index) => (
                  <p key={index}>{line}</p>
                ))}
              </div>
              {/* The two medicines by their chemical names: second and small, under his words. */}
              <p class="caption" data-testid="pair">
                {fill(s.record.pair, { one: draft.match.generic, two: flag.other_generic })}
              </p>
              <Hear lines={flag.awaiting_review ? flag.question : [severityLine(flag.severity, s), ...flag.question]} />
            </Tile>
          ))}
          <Pill plum onClick={() => void save()} disabled={busy} testId="add-it">
            {s.record.addIt}
          </Pill>
          <Pill quiet onClick={() => setStep("label")} disabled={busy}>
            {s.onboarding.back}
          </Pill>
        </>
      )}
      <Notice error={error} />
    </RecordFrame>
  );
}

/** "I have more at home." (E04-05): how many, then his yes for exactly that number; the
 *  backend's count lines come back. A high-risk medicine's count rests on a photo of the box
 *  or the label, the same rule as its dose, so for one of those the photo comes first. */
export function MoreScreen({ lineId }: { lineId: string }): JSX.Element {
  const s = t();
  // Which medicine the number is for, in the backend's words, above the question.
  const { data: lines } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.medicines(bearer, profileId, language.value);
  }, [lineId, language.value]);
  const line = lines?.find((each) => each.line_id === lineId) ?? null;
  const [typed, setTyped] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [done, setDone] = useState<MoreOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const count = countOf(typed);
  const needsPhoto = line?.high_risk === true && photo === null;
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  /** The photo of the box or the label, kept the way a label photo is (E02). A file that is
   *  not a photo is kept too, and the backend says why it will not do. */
  const upload = (file: File) =>
    run(async () => {
      const { bearer, profileId } = session();
      const data = await base64Of(file);
      const taken = new Date(file.lastModified || Date.now()).toISOString();
      const card = isPdf(file)
        ? await nura.addImport(bearer, profileId, data, "application/pdf", taken, "share")
        : await nura.addPhoto(bearer, profileId, data, file.type || "application/octet-stream", taken);
      setPhoto(card.artifact_id);
    });
  const add = () =>
    run(async () => {
      if (count === null) return;
      const { bearer, profileId } = session();
      const yes = await nura.mintMore(bearer, profileId, lineId, count, photo);
      setDone(await nura.addMore(bearer, profileId, lineId, count, yes.confirmation_id, language.value, photo));
    });
  return (
    <RecordFrame title={s.record.moreTitle} back={{ name: "medicines" }} testId="record-more">
      {done ? (
        <Tile paper settled role="status" testId="more-done">
          {(done.count?.lines ?? []).map((line, index) => (
            <p key={index}>{line}</p>
          ))}
          <Hear lines={done.count?.lines ?? []} />
        </Tile>
      ) : (
        <Tile paper testId={needsPhoto ? "more-photo" : "more-form"}>
          {line && (
            <>
              <h2 class="title" data-testid="more-medicine">
                {upperFirst(line.name)}
              </h2>
              <p class="caption">
                {line.generic} {line.strength}
              </p>
            </>
          )}
          {needsPhoto ? (
            <>
              <p>{s.record.morePhoto}</p>
              <p>{s.record.morePhotoWhy}</p>
              <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={s.onboarding.records.photo} />
              <Hear lines={[s.record.morePhoto, s.record.morePhotoWhy]} />
            </>
          ) : (
            <>
              {photo && <p data-testid="more-photo-kept">{s.record.morePhotoKept}</p>}
              <p>{s.record.moreLead}</p>
              <Field name="more" label={s.record.moreLabel} value={typed} onInput={setTyped} inputMode="numeric" big maxLength={4} />
              <Pill plum onClick={() => void add()} disabled={busy || count === null} testId="more-yes">
                {s.record.moreYes}
              </Pill>
            </>
          )}
        </Tile>
      )}
      <Notice error={error} />
    </RecordFrame>
  );
}
