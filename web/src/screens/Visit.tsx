import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import { Refused } from "../api/client";
import * as nura from "../api/nura";
import type { ConsultOut, LogisticsOut, MemoCardOut, NoticeOut, VisitSummaryOut, WordingOut } from "../api/types";
import { decisionsFor, waitingSummary } from "../day/model";
import { go, openTab } from "../flow";
import { speak } from "../speech/speak";
import { density, profile, token } from "../store/session";
import { fill, isLanguage, language, t } from "../strings";
import { Header, Hear, Notice, Pill, TabBar, Tile } from "../ui/components";
import { browserClipDeps, ClipPlayer } from "../visit/clip";
import { CONSENT_REFUSALS, logisticsView, summaryView, timer } from "../visit/model";
import { browserRecorderDeps, canRecord, ConsultRecorder, type Kept } from "../visit/recorder";
import { browserUploadDeps, ChunkedUpload, isNoConnection, uploadCalls } from "../visit/upload";

/** The Visit screen (E05-03, E05-04, E02-05): the logistics card, then one big button.
 *
 *  **Start recording** first asks the backend for the notice. The backend refuses a key that
 *  does not change the visits, then asks the gate (the RECORDING consent in force). With no
 *  consent in force the owner reads today's words and says yes; anyone else is told the owner
 *  has not agreed. Only then is the notice shown and spoken, and the microphone opened. The
 *  recording begins with the notice itself, so the doctor's answer is its first seconds.
 *  **Dr Tan said yes** keeps listening; **Dr Tan said no** throws the audio away on the phone,
 *  and every chunk already sent away on the server too, and the notes can be written by hand.
 *  The audio goes to the server in chunks as it records (#129, `visit/upload`), so a dropped
 *  connection only delays it; **Stop** sends the rest and asks the server to put it together,
 *  which it keeps only after the doctor's yes. The page must stay in front: hidden, it stops
 *  listening at once, and says so
 *  (docs/adr/0006-consult-recording-on-the-web.md). The post-visit card is the backend's, each
 *  line with "Hear what Dr Tan said" when the recording has that line in it. */

type Stage =
  | { kind: "card" }
  | { kind: "gating" }
  | { kind: "consent"; words: WordingOut }
  | { kind: "asking"; notice: NoticeOut }
  | { kind: "recording"; notice: NoticeOut }
  | { kind: "held"; notice: NoticeOut; kept: Kept; away: boolean; offline?: boolean }
  | { kind: "saving"; notice: NoticeOut }
  | { kind: "done"; notice: NoticeOut; outcome: ConsultOut }
  | { kind: "no"; notice: NoticeOut }
  | { kind: "notes"; notice: NoticeOut; summary: VisitSummaryOut }
  /** A post-visit card from before, still waiting for his yes (E05-05). */
  | { kind: "waiting"; summary: VisitSummaryOut };

export function VisitScreen({ appointmentId }: { appointmentId: string }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [card, setCard] = useState<LogisticsOut | null>(null);
  const [none, setNone] = useState(false);
  const [stage, setStage] = useState<Stage>({ kind: "card" });
  const [error, setError] = useState<unknown>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  // His yes to the post-visit card (E05-05): the items he leaves out, and the memo card after.
  const [leftOut, setLeftOut] = useState<ReadonlySet<string>>(new Set());
  const [memos, setMemos] = useState<MemoCardOut | null>(null);
  const recorder = useMemo(() => new ConsultRecorder(browserRecorderDeps()), []);
  /** The recording's chunked upload (#129), from the moment the microphone opens. */
  const chunked = useRef<ChunkedUpload | null>(null);
  const clips = useMemo(
    () =>
      new ClipPlayer(
        browserClipDeps((artifactId, start, end) => nura.clip(bearer ?? "", papers?.profile_id ?? "", artifactId, start, end)),
      ),
    [bearer, papers?.profile_id],
  );
  const now = useRef<Stage>(stage);
  now.current = stage;

  const loadCard = async () => {
    if (!bearer || !papers) return;
    try {
      setCard(await nura.logistics(bearer, papers.profile_id, appointmentId));
    } catch (failure) {
      if (failure instanceof Refused && failure.status === 404) setNone(true);
      else setError(failure);
    }
  };

  useEffect(() => {
    void loadCard();
  }, [bearer, papers?.profile_id, appointmentId]);

  // A card from this visit still waiting for his yes opens first (E05-05): confirming it on the
  // web is what makes the memos, the planned follow-up and the facts.
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.summaries(bearer, papers.profile_id, appointmentId).then(
      (found) => {
        const waiting = waitingSummary(found);
        if (waiting) setStage((now) => (now.kind === "card" ? { kind: "waiting", summary: waiting } : now));
      },
      () => undefined, // a key without the visits' cards sees the logistics card only
    );
  }, [bearer, papers?.profile_id, appointmentId]);

  // Leaving the screen: anything not sent is let go, and a clip stops.
  useEffect(
    () => () => {
      chunked.current?.discard("left");
      recorder.discard();
      clips.forget();
    },
    [recorder, clips],
  );

  // A hidden page stops listening at once (a phone suspends it). Before the doctor's answer
  // the audio is thrown away, as on a no; after it, it is kept on the phone for one tap.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState !== "hidden") return;
      const current = now.current;
      if (current.kind === "asking") {
        recorder.discard();
        chunked.current?.discard("left");
        setSaid(s.visit.stoppedAway);
        setStage({ kind: "card" });
      } else if (current.kind === "recording") {
        void recorder.stop().then((kept) => {
          if (kept) setStage({ kind: "held", notice: current.notice, kept, away: true });
        });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [recorder, s]);

  const listen = async (notice: NoticeOut) => {
    const spoken = isLanguage(notice.language) ? notice.language : language.value;
    // The notice is shown and said first, in his language, to the doctor by name; the
    // microphone opens as it is said, so the recording holds the notice and the answer.
    speak({ lines: notice.spoken, language: spoken });
    if (!canRecord()) {
      setSaid(s.visit.noMic);
      setStage({ kind: "no", notice });
      return;
    }
    try {
      await recorder.start();
    } catch {
      setSaid(s.visit.noMic);
      setStage({ kind: "no", notice });
      return;
    }
    // The audio goes to the server in chunks as it records (#129): opened now, so the notice
    // and the doctor's answer are in its first chunk, and kept there only after his yes.
    const upload = new ChunkedUpload(
      browserUploadDeps(uploadCalls(bearer ?? "", papers?.profile_id ?? "", appointmentId)),
      recorder.mimeType,
      recorder.startedAt,
    );
    recorder.onData = (piece) => upload.add(piece);
    chunked.current = upload;
    upload.start();
    setStage({ kind: "asking", notice });
  };

  const begin = async () => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    setSaid(null);
    setStage({ kind: "gating" });
    try {
      const notice = await nura.recordingNotice(bearer, papers.profile_id, appointmentId);
      await listen(notice);
    } catch (failure) {
      if (failure instanceof Refused && CONSENT_REFUSALS.has(failure.refusal) && papers.standing === "owner") {
        try {
          setStage({ kind: "consent", words: await nura.recordingWording(language.value) });
        } catch (words) {
          setError(words);
          setStage({ kind: "card" });
        }
      } else {
        setError(failure);
        setStage({ kind: "card" });
      }
    } finally {
      setBusy(false);
    }
  };

  const agree = async (words: WordingOut) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      await nura.agreeToRecording(bearer, papers.profile_id, words.version, words.language);
    } catch (failure) {
      setError(failure);
      setBusy(false);
      return;
    }
    setBusy(false);
    await begin();
  };

  /** The recording kept: the chunks put together on the server; or, when the chunked upload
   *  could not end in a recording, the whole of it from the phone, once, as before (#128). */
  const finishRecording = async (kept: Kept): Promise<ConsultOut> => {
    const upload = chunked.current;
    if (upload) {
      try {
        return await upload.finish(kept.durationS);
      } catch (failure) {
        if (isNoConnection(failure)) throw failure;
        chunked.current = null;
      }
    }
    return nura.uploadRecording(bearer ?? "", papers?.profile_id ?? "", appointmentId, kept.blob, kept.durationS, kept.startedAt);
  };

  const keep = async (notice: NoticeOut, kept: Kept) => {
    if (!bearer || !papers) return;
    setStage({ kind: "saving", notice });
    setError(null);
    try {
      const outcome = await finishRecording(kept);
      const first = outcome.summary ? summaryView(outcome.summary).lines.find((line) => line.clip)?.clip : undefined;
      if (first) clips.warm(first);
      setStage({ kind: "done", notice, outcome });
    } catch (failure) {
      // Not kept yet: the audio stays on the phone. It goes again on one tap, or by itself the
      // moment the connection is back.
      const offline = isNoConnection(failure);
      if (!offline) setError(failure);
      setStage({ kind: "held", notice, kept, away: false, offline });
    }
  };

  const stop = async (notice: NoticeOut) => {
    const kept = await recorder.stop();
    if (kept) await keep(notice, kept);
  };

  // Stop came with no connection: the recording goes the moment the connection is back.
  useEffect(() => {
    if (stage.kind !== "held" || !stage.offline) return;
    const back = () => void keep(stage.notice, stage.kept);
    window.addEventListener("online", back);
    return () => window.removeEventListener("online", back);
  }, [stage]);

  const no = (notice: NoticeOut) => {
    recorder.discard();
    chunked.current?.discard("no");
    setStage({ kind: "no", notice });
  };

  const saveNotes = async (notice: NoticeOut) => {
    if (!bearer || !papers || busy || !notes.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const summary = await nura.writeNotes(bearer, papers.profile_id, appointmentId, notes.trim());
      setStage({ kind: "notes", notice, summary });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const driveYes = async (personId: string) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      const yes = await nura.mintDrive(bearer, papers.profile_id, appointmentId, personId);
      await nura.assignDriver(bearer, papers.profile_id, appointmentId, personId, yes.confirmation_id);
      setCard(await nura.logistics(bearer, papers.profile_id, appointmentId));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  /** His one yes to the whole card as shown: every item kept, but those he left out. The
   *  backend makes the memos, the planned follow-up and the facts; a medicine change is a
   *  question for the doctor and a flag, never a change. Then the memo card, in its words. */
  const confirm = async (summary: VisitSummaryOut) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      const decisions = decisionsFor(summary, leftOut);
      const yes = await nura.mintSummaryYes(bearer, papers.profile_id, summary.summary_id, decisions);
      await nura.confirmSummary(bearer, papers.profile_id, appointmentId, summary.summary_id, decisions, yes.confirmation_id);
      setMemos(await nura.memoCard(bearer, papers.profile_id));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  const toggle = (itemId: string) => {
    const next = new Set(leftOut);
    if (!next.delete(itemId)) next.add(itemId);
    setLeftOut(next);
  };

  const listening = stage.kind === "asking" || stage.kind === "recording";
  const offline = listening && chunked.current !== null && !chunked.current.connected.value;
  const doctor = card?.doctor ?? ("notice" in stage ? stage.notice.doctor : "");
  const view = card ? logisticsView(card) : null;
  const elapsed = timer(recorder.elapsed.value);

  /** The post-visit card (E05-05): each line in the backend's order with where it was said —
   *  the stretch of the recording, or the notes he wrote — and, until his yes, "Leave this out"
   *  under each thing heard and one yes for the whole card. */
  const summaryCard = (summary: VisitSummaryOut, testId: string) => {
    const shown = summaryView(summary);
    const open = !summary.confirmed_at && memos === null;
    return (
      <>
        <Tile paper testId={testId}>
          {open && <p data-testid="summary-lead">{s.day.summaryLead}</p>}
          <div class="lines" data-testid="summary-lines">
            {shown.lines.map((line, at) => {
              const out = line.itemId !== null && leftOut.has(line.itemId);
              return (
                <div key={at} class="clip-line" data-testid="summary-line" data-item-id={line.itemId ?? undefined} data-left-out={out ? "yes" : undefined}>
                  <p>{line.text}</p>
                  {line.clip && (
                    <Pill quiet onClick={() => void clips.play(`${at}`, line.clip!).catch(setError)} testId="hear-clip">
                      {fill(s.visit.hearClip, { doctor })}
                    </Pill>
                  )}
                  {open && line.itemId && (
                    <Pill quiet pressed={out} onClick={() => toggle(line.itemId!)} testId="leave-out">
                      {s.day.summaryLeaveOut}
                    </Pill>
                  )}
                  {out && (
                    <p class="caption" data-testid="left-out">
                      {s.day.summaryLeftOut}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
          {shown.boundary.length > 0 && (
            <div class="lines boundary" data-testid="boundary">
              {shown.boundary.map((line, at) => (
                <p key={at}>{line}</p>
              ))}
            </div>
          )}
          {!summary.recording_artifact_id && (
            <p class="provenance" data-testid="from-notes">
              {s.day.summaryFromNotes}
            </p>
          )}
          <Hear lines={shown.spoken} />
          {open && (
            <Pill plum onClick={() => void confirm(summary)} disabled={busy} testId="summary-yes">
              {s.day.summaryYes}
            </Pill>
          )}
        </Tile>
        {memos && (
          <>
            {doctor && (
              <Tile paper role="status" testId="summary-kept">
                <p>{fill(s.day.summaryKept, { doctor })}</p>
              </Tile>
            )}
            <Tile paper testId="memo-card">
              <div class="lines" data-testid="memo-lines">
                {memos.card.map((line, at) => (
                  <p key={at}>{line}</p>
                ))}
              </div>
              <Hear lines={memos.spoken_card} />
            </Tile>
          </>
        )}
      </>
    );
  };

  return (
    <main class="screen" data-density={density()} data-testid="visit-screen" data-stage={stage.kind}>
      <Header title={s.visit.title} onBack={listening ? undefined : () => go({ name: "today" })} />
      <Notice error={error} />
      {said && (
        <Tile paper role="status" testId="said">
          <p>{said}</p>
        </Tile>
      )}
      {none && <Tile paper testId="no-visit"><p>{s.visit.none}</p></Tile>}

      {(stage.kind === "card" || stage.kind === "gating") && view && (
        <>
          <Tile paper testId="logistics">
            <div class="lines" data-testid="logistics-lines">
              {view.lines.map((line, at) => (
                <p key={at} data-section={line.section}>
                  {line.text}
                </p>
              ))}
            </div>
            {view.note && (
              <figure class="note" data-testid="place-note">
                <figcaption class="caption">{view.note.label}</figcaption>
                <blockquote>{view.note.text}</blockquote>
              </figure>
            )}
            <p class="provenance">{s.visit.fromVisit}</p>
            <Hear lines={view.spoken} />
          </Tile>
          {view.suggestion && (
            <Tile paper testId="drive-suggestion">
              <p>{fill(s.visit.onDuty, { name: view.suggestion.name })}</p>
              <Pill onClick={() => void driveYes(view.suggestion!.personId)} disabled={busy} testId="drive-yes">
                {fill(s.visit.driveYes, { name: view.suggestion.name })}
              </Pill>
            </Tile>
          )}
          <Pill onClick={() => go({ name: "brief", appointmentId })} testId="open-brief">
            {s.day.briefOpen}
          </Pill>
          <Pill onClick={() => go({ name: "questions", appointmentId })} testId="open-questions">
            {s.day.questionsOpen}
          </Pill>
          <Pill onClick={() => void begin()} disabled={busy || stage.kind === "gating"} testId="start-recording">
            <span class="start-label">{s.visit.start}</span>
          </Pill>
          <p class="caption" data-testid="keep-open">
            {s.visit.keepOpen}
          </p>
        </>
      )}

      {stage.kind === "consent" && (
        <Tile paper sheet testId="recording-consent">
          <p>{s.visit.consentLead}</p>
          <div class="lines">
            {stage.words.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
          <Pill plum onClick={() => void agree(stage.words)} disabled={busy} testId="agree-recording">
            {s.consent.agree}
          </Pill>
        </Tile>
      )}

      {listening && (
        <>
          {stage.kind === "asking" && (
            <Tile paper testId="notice">
              <div class="lines">
                {stage.notice.spoken.map((line, at) => (
                  <p key={at}>{line}</p>
                ))}
              </div>
            </Tile>
          )}
          <Tile paper role="status" testId="listening">
            <p class="recording">
              <span class="dot" aria-hidden="true" data-testid="red-dot" />
              <span class="timer" data-testid="timer">
                {elapsed}
              </span>
              <span>{s.visit.listening}</span>
            </p>
            <p class="caption">{s.visit.keepOpen}</p>
            {offline && (
              <p class="caption" data-testid="no-connection">
                {s.visit.noConnection} {s.visit.sendLater}
              </p>
            )}
          </Tile>
          {stage.kind === "asking" ? (
            <>
              <Pill
                plum
                onClick={() => {
                  setStage({ kind: "recording", notice: stage.notice });
                  void chunked.current?.doctorSaidYes();
                }}
                testId="doctor-yes"
              >
                {fill(s.visit.saidYes, { doctor: stage.notice.doctor })}
              </Pill>
              <Pill onClick={() => no(stage.notice)} testId="doctor-no">
                {fill(s.visit.saidNo, { doctor: stage.notice.doctor })}
              </Pill>
            </>
          ) : (
            <Pill plum onClick={() => void stop(stage.notice)} testId="stop-recording">
              <span class="start-label">{s.visit.stop}</span>
            </Pill>
          )}
        </>
      )}

      {stage.kind === "held" && (
        <Tile paper testId="held">
          {stage.away && <p>{s.visit.stoppedAway}</p>}
          {stage.offline && (
            <>
              <p data-testid="no-connection">{s.visit.noConnection}</p>
              <p>{s.visit.sendLater}</p>
            </>
          )}
          <Pill plum onClick={() => void keep(stage.notice, stage.kept)} testId="keep-heard">
            {s.visit.keepHeard}
          </Pill>
        </Tile>
      )}

      {stage.kind === "saving" && (
        <Tile paper role="status" testId="saving">
          <p>{s.visit.saving}</p>
        </Tile>
      )}

      {stage.kind === "done" && (
        <>
          <Tile paper role="status" testId="saved">
            <p>{s.visit.saved}</p>
            {!stage.outcome.recording.heard && (
              <>
                <p>{s.visit.notHeard}</p>
                <p>{s.visit.notHeardSub}</p>
              </>
            )}
            {stage.outcome.recording.heard && !stage.outcome.summary && <p>{s.visit.cardLater}</p>}
          </Tile>
          {stage.outcome.summary && summaryCard(stage.outcome.summary, "summary")}
        </>
      )}

      {stage.kind === "no" && (
        <>
          <Tile paper testId="when-no">
            <div class="lines">
              {stage.notice.when_no.map((line, at) => (
                <p key={at}>{line}</p>
              ))}
            </div>
            <Hear lines={stage.notice.when_no} />
          </Tile>
          <Tile paper testId="by-hand">
            <h2 class="title">{fill(s.visit.byHandTitle, { doctor: stage.notice.doctor })}</h2>
            <label class="by-hand-label">
              <span class="label">{fill(s.visit.byHandLabel, { doctor: stage.notice.doctor })}</span>
              <textarea
                class="field"
                name="notes"
                maxLength={4000}
                value={notes}
                onInput={(event) => setNotes((event.target as HTMLTextAreaElement).value)}
                data-testid="notes"
              />
            </label>
            <Pill plum onClick={() => void saveNotes(stage.notice)} disabled={busy || !notes.trim()} testId="save-notes">
              {s.visit.byHandSave}
            </Pill>
          </Tile>
        </>
      )}

      {stage.kind === "notes" && summaryCard(stage.summary, "summary")}

      {stage.kind === "waiting" && (
        <>
          {!memos && (
            <Tile paper role="status" testId="summary-waiting">
              <p>{s.day.summaryWaiting}</p>
            </Tile>
          )}
          {summaryCard(stage.summary, "summary")}
        </>
      )}

      {!listening && stage.kind !== "saving" && stage.kind !== "held" && (
        <TabBar current="today" onSelect={openTab} />
      )}
    </main>
  );
}
