import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ClassCandidateOut, LabelIn, LineOut, MedicineDraftOut, MoreOut, OrderPreviewOut, ReviewCardOut, SlotOut } from "../../api/types";
import { sendPaperStream } from "../../capture/session";
import { browserAudio } from "../../feed/playback";
import { reportRow } from "../../onboarding/review";
import { refreshCardNow } from "../../offline/emergencyCache";
import { bindingOf } from "../../offline/todayCache";
import { base64Of, isPdf } from "../../onboarding/actions";
import { PaperBubble, ReadingProgress } from "../onboarding/PaperReading";
import { usePaperTrace } from "../onboarding/paperTrace";
import { StoryVoice } from "../../record/storyVoice";
import { speak } from "../../speech/speak";
import {
  classQuestionFor,
  confidenceLine,
  countOf,
  displayExtractedText,
  labelFromCard,
  lineQuestions,
  nextTypedField,
  outcomeLine,
  registryRow,
  reorderActions,
  severityLine,
  tidyLabel,
} from "../../record/model";
import { density, profile } from "../../store/session";
import { aboutWhom, fill, language, t } from "../../strings";
import { Field, Hear, Notice, Pill, Tile } from "../../ui/components";
import { ActionSheet, ChipRow, ConnectionRow, Flag, Glass, Orb, PillButton, RevealGroup, SectionLabel } from "../../ui/kit";
import { Capture } from "../onboarding/parts";
import { Paged, RecordFrame, recordNote, session, takeNote, toRecord, upperFirst, useRead } from "./parts";

/** His medicines (E04-01): each line with where it came from and how sure Nura is, the count
 *  and — at the threshold — the reorder card's two buttons (E04-05), in the backend's words.
 *  "Your tablets" in the blueprint's language (redesign package 11): today's doses first,
 *  reading the same endpoints and the same tap the app's Taken flow already uses, then the
 *  registry — one glass row a medicine, his word for it first, the chemical name small and
 *  second, tapped open for the full record. */
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
  const [openLine, setOpenLine] = useState<string | null>(null);
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

  const opened = lines?.find((each) => each.line_id === openLine) ?? null;

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
      {lines && lines.length > 0 && <TodayDoses />}
      {lines && lines.length === 0 && (
        <Tile paper testId="no-medicines">
          <Orb size="lg" testId="no-medicines-orb" />
          <h2 class="title">{s.today.noMedicines}</h2>
          <Pill plum onClick={() => toRecord({ name: "add" })} testId="add-medicine-empty">
            {s.record.add}
          </Pill>
        </Tile>
      )}
      {lines && lines.length > 0 && (
        <>
          <SectionLabel testId="registry-label">{s.record.medicines}</SectionLabel>
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
                onOpen={() => setOpenLine(line.line_id)}
              />
            )}
          />
        </>
      )}
      {(!lines || lines.length > 0) && (
        <Pill onClick={() => toRecord({ name: "add" })} testId="add-medicine">
          {s.record.add}
        </Pill>
      )}
      <ActionSheet
        open={opened !== null}
        title={opened ? registryRow(opened, s).name : ""}
        sub={opened ? registryRow(opened, s).chemical : undefined}
        notNowLabel={s.onboarding.back}
        onClose={() => setOpenLine(null)}
        testId="medicine-sheet"
      >
        {opened && <LineDetail line={opened} />}
      </ActionSheet>
    </RecordFrame>
  );
}

/** Today's doses (redesign package 11): the same read and the same tap the app's Taken flow
 *  already stands on (`GET …/medicines/today`, `POST …/medicines/{line}/taken`) — restyled
 *  here, never re-plumbed. One glass row a dose, the backend's own sentence, and the
 *  backend's own word on the button, before and after ("Taken" to him, "Pa took it" to
 *  anyone else — `taken_label`, `today/model.ts`). */
function TodayDoses(): JSX.Element | null {
  const s = t();
  const { data: slots, reload } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.dosesToday(bearer, profileId, language.value);
  }, [language.value]);
  const [tapping, setTapping] = useState<string | null>(null);
  if (!slots || slots.length === 0) return null;
  const key = (slot: SlotOut) => `${slot.line_id}:${slot.anchor}`;
  const tap = async (slot: SlotOut) => {
    setTapping(key(slot));
    try {
      const { bearer, profileId } = session();
      await nura.taken(bearer, profileId, slot.line_id, slot.anchor);
      await reload();
    } finally {
      setTapping(null);
    }
  };
  return (
    <>
      <SectionLabel testId="today-kick">{s.record.todayKick}</SectionLabel>
      <RevealGroup testId="today-doses">
        {slots.map((slot) => (
          <Glass key={key(slot)} shape="row" testId="today-dose">
            <div class="report-row-top">
              <div class="report-row-name">
                <b>{slot.card}</b>
              </div>
              {slot.taken ? (
                <Flag state="ok" testId="today-taken">
                  {slot.taken_label}
                </Flag>
              ) : (
                <PillButton variant="primary" compact onClick={() => void tap(slot)} disabled={tapping === key(slot)} testId="today-tap">
                  {slot.taken_label}
                </PillButton>
              )}
            </div>
          </Glass>
        ))}
      </RevealGroup>
    </>
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
  onOpen: () => void;
}

function LineCard({ line, busy, preview, onAsk, onYes, onNo, onOpen }: LineCardProps): JSX.Element {
  const s = t();
  const row = registryRow(line, s);
  const actions = reorderActions(line);
  const counted = [...(line.count?.lines ?? []), ...(line.count?.reorder ?? [])];
  const questions = lineQuestions(line);
  const sure = confidenceLine(line, s);
  const patient = density() === "patient";
  return (
    <Tile paper={patient || actions !== null} glass={!patient && actions === null} testId="medicine-line">
      <button type="button" class="medicine-line-open" onClick={onOpen} data-testid="medicine-line-open">
        <h2 class="title">{row.name}</h2>
        <p class="caption" data-testid="chemical">
          {line.generic} {line.strength}
        </p>
      </button>
      {row.highRisk && (
        <Flag state="attention" testId="high-risk">
          {s.record.severity.major}
        </Flag>
      )}
      {row.form && <p data-testid="form">{row.form}</p>}
      {row.howMany && <p data-testid="how-many">{row.howMany}</p>}
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
      {line.monthly_cost_said && (
        <p class="caption" data-testid="monthly-cost">
          {line.monthly_cost_said}
        </p>
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
      {row.duplicate && <p data-testid="duplicate">{s.record.twice}</p>}
      {row.source && (
        <p class="provenance" data-testid="source">
          {row.source}
        </p>
      )}
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
      <Hear lines={[row.name, ...counted, ...questions, sure, ...(line.monthly_cost_said ? [line.monthly_cost_said] : []), row.source ?? ""]} />
    </Tile>
  );
}

/** The full record, in the ActionSheet a tap on a row opens: every field the line holds, one
 *  paragraph each, a field it does not hold simply not shown (redesign package 11). */
function LineDetail({ line }: { line: LineOut }): JSX.Element {
  const s = t();
  const row = registryRow(line, s);
  return (
    <div class="lines" data-testid="medicine-detail">
      {row.form && <p>{row.form}</p>}
      {row.howMany && <p>{row.howMany}</p>}
      {row.supplyLines.map((text, index) => (
        <p key={index}>{text}</p>
      ))}
      {row.monthlyCost && <p>{row.monthlyCost}</p>}
      {row.duplicate && <p>{s.record.twice}</p>}
      {row.source && (
        <p class="provenance" data-testid="sheet-source">
          {row.source}
        </p>
      )}
    </div>
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

type AddStep = "entry" | "reading" | "confirm" | "which" | "notsure" | "label" | "check" | "done";

/** A file picked for the reading screen: its name for the bubble, and a thumbnail only for a
 *  photo — revoked the moment it is no longer shown (the same rule papers.spec.ts holds the
 *  onboarding flow to: nothing of a photo stays on the phone). */
function useFileBubble(): { file: { name: string; thumb: string | null } | null; show: (file: File) => void; clear: () => void } {
  const [file, setFile] = useState<{ name: string; thumb: string | null } | null>(null);
  useEffect(
    () => () => {
      if (file?.thumb) URL.revokeObjectURL(file.thumb);
    },
    [file],
  );
  return {
    file,
    show: (picked: File) => setFile({ name: picked.name, thumb: picked.type.startsWith("image/") ? URL.createObjectURL(picked) : null }),
    clear: () => setFile(null),
  };
}

/** A typed label as one whole sentence, kept as the entry's own artefact (`nura.medicineTyped`)
 *  — his own words, never composed into anything grander than what he actually gave. */
function typedSentence(label: LabelIn): string {
  return [label.generic, label.strength, label.form, label.dose_text].filter((each) => each && each.trim().length > 0).join(", ");
}

/** The duplicate question, about him by name for anyone reading with a key that is not his
 *  own (Mei's wording, `about-him.spec.ts`) — done here, not through `aboutHim()`'s own
 *  whitelist, because that mechanism only ever swaps a plain string, never an array of
 *  lines, and this question is two lines (plain-words rule 2, one idea a line). */
function duplicateLines(s: ReturnType<typeof t>): string[] {
  const name = aboutWhom.value;
  const lines = name ? s.record.addDuplicateQuestionOther : s.record.addDuplicateQuestion;
  return name ? lines.map((line) => line.split("{patient}").join(name)) : lines;
}

/** Add a medicine (E04-03, redesign package 11, #302): a photo, a screenshot or a file — the
 *  live paper-reading flow papers already use, reused rather than rebuilt — or typed in by
 *  hand. What Nura read (or what he typed) is shown back as a confirmation card, "Looks
 *  right" or "Fix"; a box naming only a family of medicines ("STATIN") asks which one, from
 *  the licensed register's own members, never from a guess; his yes checks the label for
 *  interactions before anything is saved, and a label that adds nothing new is put to him as
 *  a question, never a bare refusal. */
export function AddMedicineScreen(): JSX.Element {
  const s = t();
  const [step, setStep] = useState<AddStep>("entry");
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [card, setCard] = useState<ReviewCardOut | null>(null);
  const [label, setLabel] = useState<LabelIn>({});
  const [candidates, setCandidates] = useState<ClassCandidateOut[]>([]);
  const [draft, setDraft] = useState<MedicineDraftOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const bubble = useFileBubble();
  const paper = usePaperTrace();

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
      bubble.show(file);
      paper.start();
      setStep("reading");
      const read = await sendPaperStream(file, paper.onStep);
      setCard(read);
      setLabel(labelFromCard(read));
      setArtifactId(read.artifact_id);
      bubble.clear();
      setStep("confirm");
    });

  /** "Looks right.": classify the name against the register before anything is checked —
   *  a class such as "STATIN" asks which one (#302) instead of being taken as a product. */
  const looksRight = () =>
    run(async () => {
      const ready = tidyLabel(label);
      if (!ready) {
        setStep("label");
        return;
      }
      const { bearer, profileId } = session();
      const found = await nura.medicineClassify(bearer, profileId, ready.generic ?? "");
      const question = classQuestionFor(found);
      if (question.kind === "ask") {
        setCandidates(question.candidates);
        setStep("which");
        return;
      }
      await checkWith(ready);
    });

  const pick = (candidate: ClassCandidateOut) =>
    run(async () => {
      const ready = tidyLabel({ ...label, generic: candidate.generic });
      if (!ready) return;
      setLabel({ ...label, generic: candidate.generic });
      await checkWith(ready);
    });

  const checkWith = async (ready: NonNullable<ReturnType<typeof tidyLabel>>) => {
    let source = artifactId;
    if (!source) {
      const { bearer, profileId } = session();
      const kept = await nura.medicineTyped(bearer, profileId, typedSentence(label), new Date().toISOString());
      source = kept.artifact_id;
      setArtifactId(source);
    }
    const { bearer, profileId } = session();
    setDraft(await nura.medicineDraft(bearer, profileId, ready, source));
    setStep("check");
  };

  const check = () =>
    run(async () => {
      const ready = tidyLabel(label);
      if (!ready) return;
      await checkWith(ready);
    });

  const save = () =>
    run(async () => {
      const ready = tidyLabel(label);
      if (!ready || !artifactId) return;
      const { bearer, profileId } = session();
      const yes = await nura.mintMedicine(bearer, profileId, ready, artifactId);
      await nura.addMedicine(bearer, profileId, ready, artifactId, yes.confirmation_id);
      // The kept emergency card's list is this same medicine's, from now (#171): a paramedic
      // reading the phone tonight must not see the list from before this add.
      const papers = profile.value;
      if (papers) await refreshCardNow(bearer, profileId, bindingOf(papers), language.value, new Date());
      setStep("done");
    });

  const set = (key: keyof LabelIn) => (value: string) =>
    setLabel({ ...label, [key]: key === "quantity" ? (value.trim() === "" ? null : Number(value)) : value });

  const nextField = nextTypedField(label);

  return (
    <RecordFrame title={s.record.add} back={{ name: "medicines" }} testId="record-add">
      {step === "entry" && (
        <Tile paper testId="add-entry">
          <p>{s.record.addLead}</p>
          <Capture onFile={(file) => void upload(file)} busy={busy} photoLabel={s.onboarding.records.photo} />
          <Pill onClick={() => setStep("label")} testId="add-type-it">
            {s.record.addTypeIt}
          </Pill>
        </Tile>
      )}
      {step === "reading" && bubble.file && (
        <Tile paper testId="add-reading">
          <PaperBubble name={bubble.file.name} thumb={bubble.file.thumb} testId="add-paper-bubble" />
          <ReadingProgress status={paper.trace.length > 0 ? paper.trace[paper.trace.length - 1]!.text : s.record.addLead2} testId="add-reading-status" />
        </Tile>
      )}
      {step === "confirm" && card && (
        <Tile paper testId="add-confirm">
          <h2 class="title">{s.record.addLead2}</h2>
          <RevealGroup testId="add-confirm-rows">
            {card.fields
              .filter((field) => field.subject === "medicine")
              .sort((a, b) => a.position - b.position)
              .map((field) => {
                const row = reportRow(field, s);
                // A label and its value, stacked — never side by side (`report-value-num`
                // is sized for a short number, and a dose line is a sentence): a long,
                // extracted, unconfirmed line must wrap on its own line, never overflow the
                // card or crowd its own "Check this one" flag off the edge.
                // A number's own unit ("5" → "5 mg") is worth repeating; a sentence field's
                // (the dose instruction) already carries its words, so its own `unit` (the
                // dose's tablet/mL) would only repeat the value's last word.
                const showUnit = row.unit && field.attribute !== "dose";
                return (
                  <Glass key={row.fieldId} shape="row" testId={`add-confirm-row-${field.attribute}`}>
                    <p class="caption">{row.label}</p>
                    <p>
                      <b>{displayExtractedText(row.valueText)}</b>
                      {showUnit && ` ${displayExtractedText(row.unit)}`}
                    </p>
                    {row.needsAttention && (
                      <span class="flag-chip question" data-testid="add-check-this-one">
                        {s.onboarding.records.checkThisOne}
                      </span>
                    )}
                  </Glass>
                );
              })}
          </RevealGroup>
          <Pill plum onClick={() => void looksRight()} disabled={busy} testId="looks-right">
            {s.record.addLooksRight}
          </Pill>
          <Pill quiet onClick={() => setStep("label")} disabled={busy} testId="add-fix">
            {s.record.addFix}
          </Pill>
        </Tile>
      )}
      {step === "which" && (
        <Tile paper testId="add-which">
          <h2 class="title">{fill(s.record.addWhichLead, { name: upperFirst(displayExtractedText(label.generic ?? "")) })}</h2>
          <p>{s.record.addWhichQuestion}</p>
          <p class="caption">{s.record.addWhichHint}</p>
          <ChipRow testId="which-chips">
            {candidates.map((candidate) => (
              <button key={candidate.generic} type="button" class="glass-chip chip-tap" onClick={() => void pick(candidate)} data-testid={`which-${candidate.generic}`}>
                {upperFirst(candidate.generic)}
              </button>
            ))}
            <button type="button" class="glass-chip chip-tap" onClick={() => setStep("notsure")} data-testid="which-not-sure">
              {s.record.addNotSure}
            </button>
          </ChipRow>
        </Tile>
      )}
      {step === "notsure" && (
        <Tile paper testId="add-not-sure">
          {s.record.addNotSureNote.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
          <Pill onClick={() => setStep("entry")} testId="add-not-sure-again">
            {s.onboarding.back}
          </Pill>
        </Tile>
      )}
      {step === "label" && (
        <Tile paper testId="add-label">
          <p>{card ? s.record.addLead2 : s.record.addTypeLead}</p>
          <Field name="generic" label={s.record.nameLabel} value={label.generic ?? ""} onInput={set("generic")} big />
          <Field name="strength" label={s.record.strengthLabel} value={label.strength ?? ""} onInput={set("strength")} big disabled={!label.generic?.trim() && nextField === "generic"} />
          <Field name="form" label={s.record.formLabel} value={label.form ?? ""} onInput={set("form")} big disabled={nextField === "generic" || nextField === "strength"} />
          <Field name="dose_text" label={s.record.howLabel} value={label.dose_text ?? ""} onInput={set("dose_text")} big />
          <p class="caption">{s.record.howHint}</p>
          <Field name="quantity" label={s.record.countLabel} value={label.quantity ? String(label.quantity) : ""} onInput={set("quantity")} inputMode="numeric" big maxLength={4} />
          <Field name="prescriber" label={s.record.doctorLabel} value={label.prescriber ?? ""} onInput={set("prescriber")} big />
          <Pill plum onClick={() => void check()} disabled={busy || !tidyLabel(label)} testId="check-medicine">
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
          {draft.outcome === "duplicate" ? (
            <Tile paper testId="add-duplicate">
              {duplicateLines(s).map((line, index) => (
                <p key={index}>{line}</p>
              ))}
              <Pill plum onClick={() => setStep("label")} testId="duplicate-yes">
                {s.record.addDuplicateYes}
              </Pill>
              <Pill quiet onClick={() => toRecord({ name: "medicines" })} testId="duplicate-no">
                {s.record.addDuplicateNo}
              </Pill>
            </Tile>
          ) : (
            <>
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
        </>
      )}
      {step === "done" && (
        <Tile paper settled role="status" testId="add-done">
          <ConnectionRow
            name={s.record.medicines}
            line={s.record.addedConnection}
            onClick={() => {
              recordNote.value = [s.record.added];
              toRecord({ name: "medicines" });
            }}
            testId="see-in-registry"
          />
        </Tile>
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
