import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { ConsentOut } from "../../api/types";
import { afterSignIn, go } from "../../flow";
import { inForce, wordingLines } from "../../family/model";
import { Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead, whose } from "./common";

/** Keeping his papers is stopped by closing his account (#143): the backend's withdrawal says
 *  what closing means and when his papers go, and his yes closes it. Everything else — WhatsApp
 *  among them since #143 — is stopped here with one yes, after the backend says exactly what. */
const CLOSES = "hold_health_record";

/** E00-02: every agreement in force, in the words he read; stopping one, after the backend
 *  says what stopping will do; and the whole record, withdrawn ones included, to keep. */
export function ConsentsPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [asking, setAsking] = useState<{ consent: ConsentOut; lines: string[]; closes: boolean } | null>(null);
  const [stopped, setStopped] = useState<string[] | null>(null);
  const list = useRead(here ? () => family.consents(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  if (!here) return null;
  const pid = here.papers.profile_id;
  const ask = (consent: ConsentOut) =>
    a.act(consent.consent_id, async () => {
      setStopped(null);
      const said = await family.withdrawal(here.bearer, pid, consent.consent_id, here.lang);
      setAsking({ consent, lines: said.lines, closes: said.closes_account === true });
    });
  const stop = () =>
    a.act("confirm", async () => {
      if (!asking) return;
      if (asking.closes) {
        // Closed: nobody opens these papers now, him included; the doors say so.
        await family.closeAccount(here.bearer, pid, here.lang);
        setAsking(null);
        await afterSignIn();
        return;
      }
      const done = await family.withdraw(here.bearer, pid, asking.consent.consent_id, here.lang);
      setAsking(null);
      setStopped(done.lines);
      await list.reload();
    });
  return (
    <FamilyPage title={whose(here, words.consentsSelf, words.consentsOther)} part="consents">
      <Notice error={list.error} />
      {asking ? (
        <Tile paper testId="stop-confirm">
          <Lines lines={asking.lines} testId="stop-lines" />
          <Pill plum onClick={() => void stop()} disabled={a.busy} testId={asking.closes ? "close-yes" : "stop-yes"}>
            {asking.closes ? words.closeAccountYes : words.stopYes}
          </Pill>
          <Pill quiet onClick={() => (setAsking(null), a.clear())} testId="stop-cancel">
            {words.notNow}
          </Pill>
          <NoticeAt act={a} where="confirm" />
        </Tile>
      ) : (
        <>
          {stopped && (
            <Tile paper role="status" testId="stopped">
              <Lines lines={stopped} />
            </Tile>
          )}
          {inForce(list.value ?? []).map((consent) => (
            <Tile paper key={consent.consent_id} testId="consent">
              <Lines lines={wordingLines(consent)} testId="consent-words" />
              <Pill onClick={() => void ask(consent)} disabled={a.busy} testId={consent.purpose === CLOSES ? "close-account" : "stop"}>
                {consent.purpose === CLOSES ? words.closeAccount : words.stop}
              </Pill>
              <NoticeAt act={a} where={consent.consent_id} />
            </Tile>
          ))}
          {list.value && (
            <Pill onClick={() => go({ name: "family", part: "record" })} testId="open-record">
              {words.keepCopy}
            </Pill>
          )}
        </>
      )}
    </FamilyPage>
  );
}

/** The printable record the backend renders (`GET /consents/record.html`): shown as it is, in
 *  a frame that runs nothing, with the one way to keep it — saving the page to print. */
export function RecordPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const page = useRead(here ? () => family.consentRecord(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  const url = useMemo(() => (page.value ? URL.createObjectURL(new Blob([page.value], { type: "text/html" })) : null), [page.value]);
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  if (!here) return null;
  const title = whose(here, words.consentsSelf, words.consentsOther);
  return (
    <FamilyPage title={title} part="record">
      <Notice error={page.error} />
      {page.value && url && (
        <>
          <a class="pill plum" href={url} download="nura-consent-record.html" data-testid="save-record">
            {words.savePage}
          </a>
          <iframe class="record" title={title} sandbox="" srcDoc={page.value} data-testid="record-page" />
        </>
      )}
    </FamilyPage>
  );
}
