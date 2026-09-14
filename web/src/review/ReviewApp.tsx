import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { Refused } from "../api/client";
import { deployment } from "../api/nura";
import * as review from "../api/review";
import type { ReviewItemOut, StatusOut } from "../api/review";
import { fill, t } from "../strings";
import { Field, Header, Notice, Pill, Tile } from "../ui/components";

const KEPT = "nura.review.staff";

function keptToken(): string | null {
  try {
    return sessionStorage.getItem(KEPT);
  } catch {
    return null;
  }
}

function keep(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(KEPT, token);
    else sessionStorage.removeItem(KEPT);
  } catch {
    /* the page works without it; the token is asked for again */
  }
}

/** The pharmacist's queue: the first fifty renderings of each card type, and new sources,
 *  each approved, rejected with a reason, or rewritten as a proposed catalogue change. It
 *  shows no profile, no person and no name, because the queue holds none (ADR 0007). */
export function ReviewApp(): JSX.Element {
  const words = t().review;
  const [token, setToken] = useState<string | null>(keptToken());
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<StatusOut | null>(null);
  const [items, setItems] = useState<ReviewItemOut[]>([]);
  const [verdict, setVerdict] = useState<"pending" | "any">("pending");
  const [error, setError] = useState<unknown>(null);

  const load = async (staff: string, which = verdict) => {
    const [found, queue] = await Promise.all([review.reviewStatus(staff), review.reviewQueue(staff, which)]);
    setStatus(found);
    setItems(queue);
  };
  useEffect(() => {
    if (token) load(token).catch((failure: unknown) => (setError(failure), setToken(null), keep(null)));
  }, []);

  const open = async () => {
    setError(null);
    try {
      // A laptop's token is a dev run's only (ADR 0007): anywhere else it is never sent.
      if (draft.trim().startsWith("nura-dev-") && !(await deployment()).dev) throw new Refused("NotStaff", 403);
      await load(draft.trim());
      setToken(draft.trim());
      keep(draft.trim());
      setDraft("");
    } catch (failure) {
      setError(failure);
    }
  };
  const show = async (which: "pending" | "any") => {
    if (!token) return;
    setVerdict(which);
    try {
      await load(token, which);
    } catch (failure) {
      setError(failure);
    }
  };

  if (!token) {
    return (
      <main class="screen review" data-testid="review-sign-in">
        <Header title={words.title} />
        <Tile paper>
          <Field name="staff-token" label={words.tokenLabel} value={draft} onInput={setDraft} type="password" autoComplete="off" />
          <Pill plum onClick={() => void open()} disabled={!draft.trim()} testId="review-open">
            {words.open}
          </Pill>
        </Tile>
        <Notice error={error} />
      </main>
    );
  }
  return (
    <main class="screen review" data-testid="review-queue">
      <Header title={words.title} />
      <Notice error={error} />
      {status && (
        <Tile paper testId="review-status">
          <h2 class="title">{words.statusTitle}</h2>
          <table class="data">
            <thead>
              <tr>
                <th>{words.cardType}</th>
                <th>{words.sampled}</th>
                <th>{words.pending}</th>
                <th>{words.stillToCheck}</th>
              </tr>
            </thead>
            <tbody>
              {status.card_types.map((row) => (
                <tr key={row.card_type} data-testid="review-type" data-flag={String(row.flag)}>
                  <td>{row.card_type}</td>
                  <td>{row.sampled}</td>
                  <td>{row.pending}</td>
                  <td>{row.flag ? "●" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p class="label">{fill(words.sourcesWaiting, { count: status.sources_pending })}</p>
        </Tile>
      )}
      <div class="row">
        <Pill chosen={verdict === "pending"} onClick={() => void show("pending")} testId="review-pending">
          {words.showPending}
        </Pill>
        <Pill chosen={verdict === "any"} onClick={() => void show("any")} testId="review-all">
          {words.showAll}
        </Pill>
      </div>
      <h2 class="title">{words.queueTitle}</h2>
      {items.map((item) => (
        <Item key={item.item_id} item={item} staff={token} onDecided={() => load(token)} />
      ))}
      <Pill quiet onClick={() => (setToken(null), keep(null), setStatus(null), setItems([]))} testId="review-leave">
        {words.leave}
      </Pill>
    </main>
  );
}

function Item({ item, staff, onDecided }: { item: ReviewItemOut; staff: string; onDecided: () => Promise<void> }): JSX.Element {
  const words = t().review;
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [headline, setHeadline] = useState(item.lines.headline ?? "");
  const [body, setBody] = useState((item.lines.body ?? []).join("\n"));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const decide = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      await onDecided();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  const meta = [item.kind, item.card_type, item.language, item.sample_number === null ? null : `#${item.sample_number}`].filter(Boolean).join(" · ");
  return (
    <Tile paper testId="review-item">
      <p class="item-meta">{meta}</p>
      {item.lines.headline && <h2 class="title">{item.lines.headline}</h2>}
      <div class="lines" data-testid="review-lines">
        {(item.lines.body ?? []).map((line, at) => (
          <p key={at}>{line}</p>
        ))}
        {item.lines.why && <p class="caption">{item.lines.why}</p>}
      </div>
      {item.verdict === "pending" ? (
        <>
          <Field name="review-reason" label={words.reasonLabel} value={reason} onInput={setReason} maxLength={500} />
          {editing && (
            <>
              <Field name="review-headline" label={words.headline} value={headline} onInput={setHeadline} />
              <label class="by-hand-label">
                <span class="label">{words.body}</span>
                <textarea class="field" name="review-body" rows={4} value={body} onInput={(event) => setBody((event.target as HTMLTextAreaElement).value)} />
              </label>
              <Pill
                plum
                disabled={busy}
                onClick={() =>
                  void decide(() =>
                    review.rewrite(staff, item.item_id, { headline: headline.trim() || undefined, body: body.split("\n").map((line) => line.trim()).filter(Boolean) }, reason.trim() || null),
                  )
                }
                testId="review-save-rewrite"
              >
                {words.saveRewrite}
              </Pill>
            </>
          )}
          {!editing && (
            <div class="row">
              <Pill disabled={busy} onClick={() => void decide(() => review.approve(staff, item.item_id, reason.trim() || null))} testId="review-approve">
                {words.approve}
              </Pill>
              <Pill disabled={busy} onClick={() => void decide(() => review.reject(staff, item.item_id, reason.trim()))} testId="review-reject">
                {words.reject}
              </Pill>
              <Pill disabled={busy} onClick={() => setEditing(true)} testId="review-rewrite">
                {words.rewrite}
              </Pill>
            </div>
          )}
        </>
      ) : (
        <p class="label" data-testid="review-decided">
          {words.decided}: {item.verdict}
          {item.reason ? ` — ${item.reason}` : ""}
        </p>
      )}
      <Notice error={error} />
    </Tile>
  );
}
