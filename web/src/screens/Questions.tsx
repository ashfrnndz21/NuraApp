import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { QuestionChange, VisitQuestionsOut } from "../api/types";
import { questionCard } from "../day/model";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { language, t } from "../strings";
import { Header, Hear, Notice, Pill, Tile } from "../ui/components";

type Stage = { kind: "card" } | { kind: "check"; text: string } | { kind: "remove"; questionId: string; text: string };

/** Questions for your visit (E05-02): his one card — the first three by priority, a
 *  reassurance, the boundary — as the backend wrote it. He adds one in his own words and keeps
 *  it on his yes to exactly those words; he takes one off on his yes to exactly that. Words
 *  that are not plain are refused by the backend, and its sentence is said. */
export function QuestionsScreen({ appointmentId }: { appointmentId: string }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [found, setFound] = useState<VisitQuestionsOut | null>(null);
  const [stage, setStage] = useState<Stage>({ kind: "card" });
  const [typed, setTyped] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const read = async () => {
    if (!bearer || !papers) return;
    try {
      setFound(await nura.visitQuestions(bearer, papers.profile_id, appointmentId));
    } catch (failure) {
      setError(failure);
    }
  };
  useEffect(() => {
    void read();
  }, [bearer, papers?.profile_id, appointmentId, language.value]);

  /** His yes to exactly this change, then the change on that yes. */
  const change = async (what: QuestionChange, done: string) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      const yes = await nura.mintQuestionYes(bearer, papers.profile_id, appointmentId, what);
      await nura.changeQuestion(bearer, papers.profile_id, appointmentId, what, yes.confirmation_id);
      setSaid(done);
      setTyped("");
      setStage({ kind: "card" });
      await read();
    } catch (failure) {
      setError(failure);
      setStage({ kind: "card" });
    } finally {
      setBusy(false);
    }
  };

  const lines = found ? questionCard(found) : [];
  return (
    <main class="screen" data-density={density()} data-testid="questions-screen" data-stage={stage.kind}>
      <Header title={s.day.questionsTitle} onBack={stage.kind === "card" ? () => go({ name: "visit", appointmentId }) : undefined} />
      <Notice error={error} />
      {said && (
        <Tile paper role="status" testId="said">
          <p>{said}</p>
        </Tile>
      )}
      {stage.kind === "card" && found && (
        <>
          <Tile paper testId="question-card">
            <div class="lines">
              {lines.map((line, at) => (
                <div key={at} class="clip-line" data-testid={line.questionId ? "question-line" : "card-line"}>
                  <p>{line.text}</p>
                  {line.questionId && (
                    <Pill quiet onClick={() => setStage({ kind: "remove", questionId: line.questionId!, text: line.text })} testId="question-remove">
                      {s.day.questionRemove}
                    </Pill>
                  )}
                </div>
              ))}
            </div>
            <Hear lines={found.spoken_card} />
          </Tile>
          <Tile paper testId="question-add">
            <label class="by-hand-label">
              <span class="label">{s.day.questionLabel}</span>
              <textarea
                class="field"
                name="question"
                maxLength={200}
                value={typed}
                onInput={(event) => setTyped((event.target as HTMLTextAreaElement).value)}
                data-testid="question-words"
              />
            </label>
            <Pill plum onClick={() => setStage({ kind: "check", text: typed.trim() })} disabled={!typed.trim()} testId="question-add-button">
              {s.day.questionAdd}
            </Pill>
          </Tile>
        </>
      )}
      {stage.kind === "check" && (
        <Tile paper sheet testId="question-check">
          <p>{s.day.questionCheck}</p>
          <blockquote data-testid="question-typed">{stage.text}</blockquote>
          <Pill plum onClick={() => void change({ text: stage.text }, s.day.questionKept)} disabled={busy} testId="question-yes">
            {s.day.questionYes}
          </Pill>
          <Pill onClick={() => setStage({ kind: "card" })} disabled={busy} testId="question-not-now">
            {s.reading.cancel}
          </Pill>
        </Tile>
      )}
      {stage.kind === "remove" && (
        <Tile paper sheet testId="question-remove-check">
          <p>{s.day.questionRemoveCheck}</p>
          <blockquote>{stage.text}</blockquote>
          <Pill plum onClick={() => void change({ question_id: stage.questionId, remove: true }, s.day.questionRemoved)} disabled={busy} testId="question-remove-yes">
            {s.day.questionRemoveYes}
          </Pill>
          <Pill onClick={() => setStage({ kind: "card" })} disabled={busy} testId="question-not-now">
            {s.reading.cancel}
          </Pill>
        </Tile>
      )}
    </main>
  );
}
