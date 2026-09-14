import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { ConsentOut } from "../../api/types";
import { go } from "../../flow";
import { inForce, wordingLines } from "../../family/model";
import { Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead, whose } from "./common";

/** What the owner stops in the app with one yes (`app.consent.withdrawal.APP_STOPS`). Keeping
 *  his papers and WhatsApp carry the red-flag paths, and are stopped with the Nura team: the
 *  app does not offer what it cannot do, and the backend refuses it by name besides. */
const APP_STOPS: ReadonlySet<string> = new Set(["share_with_family", "recording", "calendar"]);

/** E00-02: every agreement in force, in the words he read; stopping one, after the backend
 *  says what stopping will do; and the whole record, withdrawn ones included, to keep. */
export function ConsentsPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [asking, setAsking] = useState<{ consent: ConsentOut; lines: string[] } | null>(null);
  const [stopped, setStopped] = useState<string[] | null>(null);
  const list = useRead(here ? () => family.consents(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  if (!here) return null;
  const pid = here.papers.profile_id;
  const ask = (consent: ConsentOut) =>
    a.act(consent.consent_id, async () => {
      setStopped(null);
      const said = await family.withdrawal(here.bearer, pid, consent.consent_id, here.lang);
      setAsking({ consent, lines: said.lines });
    });
  const stop = () =>
    a.act("confirm", async () => {
      if (!asking) return;
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
          <Pill plum onClick={() => void stop()} disabled={a.busy} testId="stop-yes">
            {words.stopYes}
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
              {APP_STOPS.has(consent.purpose ?? "") && (
                <Pill onClick={() => void ask(consent)} disabled={a.busy} testId="stop">
                  {words.stop}
                </Pill>
              )}
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
