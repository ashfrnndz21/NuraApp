import { useEffect, useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { go } from "../flow";
import { profile, token } from "../store/session";
import { language, t } from "../strings";
import { Header, Notice } from "../ui/components";
import { PillButton } from "../ui/kit";
import { Shell } from "./Shell";

/** The emergency card (E00, reached from the Me sheet): the backend's own printable page, shown
 *  as it is — every line on it the backend's, the phone composes none — and one button to print
 *  it for his wallet. The page is sandboxed: it runs nothing and fetches nothing. */
export function EmergencyScreen(): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [page, setPage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.emergencyCardPage(bearer, papers.profile_id, language.value).then(
      (found) => {
        setPage(found);
        setError(null);
      },
      (failure: unknown) => {
        setPage(null);
        setError(failure);
      },
    );
  }, [bearer, papers?.profile_id, language.value]);
  // The frame is as tall as the card, so the shell's own page is the one that scrolls.
  const fit = () => {
    const body = frame.current?.contentDocument?.documentElement;
    if (frame.current && body) frame.current.style.height = `${body.scrollHeight}px`;
  };
  return (
    <Shell tab={null} testId="emergency-screen">
      <Header title={s.today.emergencyTitle} onBack={() => go({ name: "today" })} />
      <Notice error={error} />
      {page !== null && (
        <>
          <iframe ref={frame} class="emergency-page" title={s.today.emergencyTitle} srcdoc={page} sandbox="allow-same-origin allow-modals" onLoad={fit} data-testid="emergency-page" />
          <PillButton onClick={() => frame.current?.contentWindow?.print()} testId="emergency-print">
            {s.me.emergencyPrint}
          </PillButton>
        </>
      )}
    </Shell>
  );
}
