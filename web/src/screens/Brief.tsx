import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { briefView, type BriefView } from "../day/model";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { language, t } from "../strings";
import { Header, Hear, Notice, Tile } from "../ui/components";

/** Before your visit (E05-01): the whole pre-visit brief, as the backend rendered it from State
 *  in his language — what the visit is for, what changed, the questions, what to bring — and the
 *  boundary it ends on. The visit card on his feed carries only a part of it; this is all of it. */
export function BriefScreen({ appointmentId }: { appointmentId: string }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [view, setView] = useState<BriefView | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.brief(bearer, papers.profile_id, appointmentId).then((found) => setView(briefView(found)), setError);
  }, [bearer, papers?.profile_id, appointmentId, language.value]);
  return (
    <main class="screen" data-density={density()} data-testid="brief-screen">
      <Header title={s.day.briefTitle} onBack={() => go({ name: "visit", appointmentId })} />
      <Notice error={error} />
      {view && (
        <Tile paper testId="brief">
          <div class="lines" data-testid="brief-lines">
            {view.lines.map((line, at) => (
              <p key={at} data-section={line.section}>
                {line.text}
              </p>
            ))}
          </div>
          {view.boundary.length > 0 && (
            <div class="lines boundary" data-testid="boundary">
              {view.boundary.map((line, at) => (
                <p key={at}>{line}</p>
              ))}
            </div>
          )}
          <p class="provenance">{s.visit.fromVisit}</p>
          <Hear lines={view.spoken} />
        </Tile>
      )}
    </main>
  );
}
