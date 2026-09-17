import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { FeelingNoteOut, FeelingOut } from "../api/types";
import { keptCards } from "../day/offline";
import { whatToDoLines } from "../day/model";
import { whenNotReached } from "../day/redPath";
import { go } from "../flow";
import { bindingOf } from "../offline/todayCache";
import { profile, token } from "../store/session";
import { language, t } from "../strings";
import { Hear, Notice } from "../ui/components";
import { PaperTile, PillButton } from "../ui/kit";
import { Shell } from "./Shell";

/** One word tapped on the cloud, and the one thing it asks back (E17-02): the backend's
 *  question and its answers as buttons. His answer comes back as a note kept for the visit —
 *  the headline, what to tell the doctor, who does the next thing, the boundary last — or, when
 *  his yes makes the word red, as the red-flag path's card. */
export function FeelingScreen({ tap }: { tap: FeelingOut }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [note, setNote] = useState<FeelingNoteOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const question = tap.question;

  const answer = async (choice: { answer: string; red?: boolean }) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      const done = await nura.answerFeeling(bearer, papers.profile_id, tap.tap_id, choice.answer, language.value);
      if (done.red_flag) {
        const lines = done.card ? whatToDoLines(done.card) : done.lines;
        return go({ name: "whatToDo", lines, offline: null, refusal: null });
      }
      if (done.note) setNote(done.note);
      else go({ name: "today" });
    } catch (failure) {
      if (choice.red) {
        // The answer the backend says makes the word red, not sent: the red card, never less.
        const kept = await keptCards(papers.profile_id, bindingOf(papers));
        return go({ name: "whatToDo", ...whenNotReached("red_flag", failure, kept?.cards ?? null, papers.region, s, language.value) });
      }
      // Anything else: said in one sentence, and the question stays for him to answer again.
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const boundary = note?.boundary ? note.boundary.split("\n") : [];
  return (
    <Shell tab="home" testId="feeling-screen" ask={false}>
      <Notice error={error} />
      {!note && question && (
        <PaperTile testId="feeling-question">
          <h1 class="title">{question.words}</h1>
          {question.answers.map((one) => (
            <PillButton key={one.answer} onClick={() => void answer(one)} disabled={busy} testId={`answer-${one.answer}`}>
              {one.label}
            </PillButton>
          ))}
          <Hear lines={[question.words]} />
        </PaperTile>
      )}
      {note && (
        <PaperTile testId="feeling-note">
          <h1 class="title">{note.headline}</h1>
          <div class="lines" data-testid="note-lines">
            {note.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
            <p>{note.then}</p>
          </div>
          {boundary.length > 0 && (
            <div class="lines boundary" data-testid="boundary">
              {boundary.map((line, at) => (
                <p key={at}>{line}</p>
              ))}
            </div>
          )}
          <Hear lines={note.voice} />
        </PaperTile>
      )}
      <PillButton onClick={() => go({ name: "today" })} testId="back-today">
        {s.day.backToday}
      </PillButton>
    </Shell>
  );
}
