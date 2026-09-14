import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../../api/nura";
import type { ReviewCardOut, TimelineItemOut, TimelineOut } from "../../api/types";
import { kindLine } from "../../onboarding/review";
import { artifactLine, hangingLines, itemTitle, kindWord, papersToPut, providerLines, visitStatusLine } from "../../record/model";
import { density, profile } from "../../store/session";
import { fill, language, t } from "../../strings";
import { Field, Hear, Notice, Pill, Tile } from "../../ui/components";
import { Paged, RecordFrame, session, toRecord, useDateOf, useRead } from "./parts";

/** His visits (E03-01): the spine's three anchors in his words — the last check-up, the last
 *  visit, the next visit — then the visits and illnesses newest first, each with what hangs
 *  off it, paged by the backend's cursor. */
export function TimelineScreen(): JSX.Element {
  const s = t();
  const [pages, setPages] = useState<TimelineOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useRead(async () => {
    const { bearer, profileId } = session();
    try {
      setPages([await nura.timeline(bearer, profileId, language.value)]);
    } catch (failure) {
      setError(failure);
    }
  }, [language.value]);

  const cursor = pages.at(-1)?.next_cursor ?? null;
  const older = async () => {
    if (!cursor) return;
    setBusy(true);
    try {
      const { bearer, profileId } = session();
      const next = await nura.timeline(bearer, profileId, language.value, cursor);
      setPages([...pages, next]);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  const header = pages[0]?.header ?? [];
  const items = pages.flatMap((page) => page.items);
  const patient = density() === "patient";
  return (
    <RecordFrame title={s.record.timeline} back={{ name: "hub" }} testId="record-timeline">
      <Notice error={error} />
      {header.length > 0 && (
        <Tile paper testId="anchors">
          <div class="lines">
            {header.map((anchor) => (
              <p key={anchor.key} data-anchor={anchor.key}>
                {anchor.line}
              </p>
            ))}
          </div>
          <Hear lines={header.map((anchor) => anchor.line)} />
        </Tile>
      )}
      <Paged items={items} more={cursor ? older : null} render={(item) => <ItemTile key={`${item.kind}:${item.id}`} item={item} />} />
      {!patient && cursor && (
        <Pill onClick={() => void older()} disabled={busy} testId="older">
          {s.record.older}
        </Pill>
      )}
      {pages.length > 0 && !cursor && (!patient || items.length === 0) && (
        <p class="caption" data-testid="end-of-list">
          {s.record.endOfList}
        </p>
      )}
    </RecordFrame>
  );
}

function ItemTile({ item }: { item: TimelineItemOut }): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const episode = item.kind === "episode" ? item.episode : null;
  const visit = item.appointment;
  const lines = [
    ...(episode ? [fill(s.record.since, { date: dateOf(episode.opened_at) }), ...(episode.closed_at ? [fill(s.record.ended, { date: dateOf(episode.closed_at) })] : [])] : []),
    ...(visit ? [visit.purpose, visitStatusLine(visit.status, s) ?? ""].filter((line) => line.length > 0) : []),
    ...hangingLines(item, s),
  ];
  return (
    <Tile paper={density() === "patient"} glass={density() !== "patient"} testId="timeline-item">
      <h2 class="title" data-kind={item.kind}>
        {itemTitle(item)}
      </h2>
      <p class="caption">{dateOf(item.at)}</p>
      <div class="lines">
        {lines.map((line, index) => (
          <p key={index}>{line}</p>
        ))}
      </div>
      {episode && (
        <Pill onClick={() => toRecord({ name: "episode", episodeId: episode.episode_id })} testId="see-illness">
          {s.record.seeIllness}
        </Pill>
      )}
      {item.provider && (
        <Pill onClick={() => toRecord({ name: "provider", providerId: item.provider!.provider_id })} testId="see-doctor">
          {s.record.seeDoctor}
        </Pill>
      )}
      <Hear lines={[itemTitle(item), dateOf(item.at), ...lines]} />
    </Tile>
  );
}

/** An open illness and what is filed with it (E03-02): its papers, what was written down,
 *  the visits during it; and, on the chief's yes, a paper put with it. */
export function EpisodeScreen({ episodeId }: { episodeId: string }): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const [putting, setPutting] = useState<ReviewCardOut | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: view, error, reload } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.episode(bearer, profileId, episodeId);
  }, [episodeId]);
  const { data: cards, reload: reloadCards } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.reviewCards(bearer, profileId, false);
  }, [episodeId]);

  const put = async (card: ReviewCardOut) => {
    setBusy(true);
    setFailure(null);
    try {
      const { bearer, profileId } = session();
      const yes = await nura.mintAttach(bearer, profileId, card.artifact_id, episodeId);
      await nura.attachToEpisode(bearer, profileId, episodeId, card.artifact_id, yes.confirmation_id);
      setPutting(null);
      setSaid(s.record.putDone);
      await reload();
      await reloadCards();
    } catch (refused) {
      setFailure(refused);
    } finally {
      setBusy(false);
    }
  };

  const episode = view?.episode.episode ?? null;
  const open = episode !== null && episode.closed_at === null;
  const candidates = view && cards ? papersToPut(cards, view) : [];
  return (
    <RecordFrame title={episode?.label ?? s.record.timeline} back={{ name: "timeline" }} testId="record-episode">
      <Notice error={error ?? failure} />
      {said && (
        <Tile paper settled role="status" testId="put-done">
          <p>{said}</p>
        </Tile>
      )}
      {view && episode && putting === null && (
        <>
          <Tile paper testId="episode">
            <p>{fill(s.record.since, { date: dateOf(episode.opened_at) })}</p>
            {episode.closed_at && <p>{fill(s.record.ended, { date: dateOf(episode.closed_at) })}</p>}
            {hangingLines(view.episode, s).map((line, index) => (
              <p key={index}>{line}</p>
            ))}
          </Tile>
          {view.episode.artifacts.length > 0 && (
            <Tile paper testId="episode-papers">
              <h2 class="title">{s.record.illnessPapers}</h2>
              {view.episode.artifacts.map((artifact) => (
                <p key={artifact.artifact_id} data-artifact-id={artifact.artifact_id}>
                  {artifactLine(artifact, dateOf(artifact.captured_at), s)}
                </p>
              ))}
            </Tile>
          )}
          {view.episode.events.length > 0 && (
            <Tile paper testId="episode-moments">
              <h2 class="title">{s.record.illnessMoments}</h2>
              {view.episode.events.map((event) => (
                <p key={event.event_id}>{fill(s.record.momentOn, { what: event.label ?? "", date: dateOf(event.occurred_at) })}</p>
              ))}
            </Tile>
          )}
          {view.visits.length > 0 && (
            <Tile paper testId="episode-visits">
              <h2 class="title">{s.record.illnessVisits}</h2>
              {view.visits.map((visit) => (
                <p key={visit.id}>{fill(s.record.momentOn, { what: itemTitle(visit), date: dateOf(visit.at) })}</p>
              ))}
            </Tile>
          )}
          {open && cards && (
            <Tile paper testId="put-with">
              <h2 class="title">{s.record.putWith}</h2>
              {candidates.length === 0 && <p data-testid="nothing-to-put">{s.record.nothingToPut}</p>}
              {candidates.map((card) => (
                <div key={card.card_id} class="lines" data-testid="paper-to-put" data-artifact-id={card.artifact_id}>
                  <p>{kindLine(card.document_kind, s)}</p>
                  <p class="caption">{fill(s.record.paperFrom, { date: dateOf(card.created_at) })}</p>
                  <Pill onClick={() => setPutting(card)} testId="put-this">
                    {s.record.putThis}
                  </Pill>
                </div>
              ))}
            </Tile>
          )}
        </>
      )}
      {putting && (
        <Tile paper testId="put-ask">
          <p>{s.record.putAsk}</p>
          <p>{kindLine(putting.document_kind, s)}</p>
          <p class="caption">{fill(s.record.paperFrom, { date: dateOf(putting.created_at) })}</p>
          <Pill plum onClick={() => void put(putting)} disabled={busy} testId="put-yes">
            {s.record.putYes}
          </Pill>
          <Pill quiet onClick={() => setPutting(null)} disabled={busy}>
            {s.onboarding.back}
          </Pill>
        </Tile>
      )}
    </RecordFrame>
  );
}

/** His doctors and clinics (E03-03), with how many visits and the last and the next. */
export function ProvidersScreen(): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const { data: providers, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.providers(bearer, profileId);
  }, []);
  return (
    <RecordFrame title={s.record.providers} back={{ name: "hub" }} testId="record-providers">
      <Notice error={error} />
      {providers && (
        <Paged
          items={providers}
          render={(summary) => (
            <Tile paper={density() === "patient"} glass={density() !== "patient"} key={summary.provider.provider_id} testId="provider">
              <h2 class="title">{summary.provider.name}</h2>
              <p class="caption">{kindWord(summary.provider.kind, s)}</p>
              <div class="lines">
                {providerLines(summary, dateOf, s).map((line, index) => (
                  <p key={index}>{line}</p>
                ))}
              </div>
              <Pill onClick={() => toRecord({ name: "provider", providerId: summary.provider.provider_id })} testId="see-doctor">
                {s.record.seeDoctor}
              </Pill>
            </Tile>
          )}
        />
      )}
    </RecordFrame>
  );
}

/** One doctor or clinic: where it is, the visits, the papers, the medicines on its name, and —
 *  for the owner and his chief only — their notes about the place, which the chief writes.
 *  A note naming a medicine or an illness is refused, and the refusal is said. */
export function ProviderScreen({ providerId }: { providerId: string }): JSX.Element {
  const s = t();
  const dateOf = useDateOf();
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: history, error, reload } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.provider(bearer, profileId, providerId);
  }, [providerId]);
  const papers = profile.value;
  const mayWrite = papers?.standing === "owner" || papers?.role === "chief";

  const save = async () => {
    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      const { bearer, profileId } = session();
      await nura.noteOnProvider(bearer, profileId, providerId, text.trim());
      setText("");
      setSaved(true);
      await reload();
    } catch (refused) {
      setFailure(refused);
    } finally {
      setBusy(false);
    }
  };

  const place = history?.provider;
  return (
    <RecordFrame title={place?.name ?? s.record.providers} back={{ name: "providers" }} testId="record-provider">
      <Notice error={error} />
      {history && place && (
        <>
          <Tile paper testId="provider-place">
            <p class="caption">{kindWord(place.kind, s)}</p>
            {place.address && (
              <>
                <p class="label">{s.record.where}</p>
                <p>{place.address}</p>
              </>
            )}
            {place.phone_e164 && (
              <>
                <p class="label">{s.record.phone}</p>
                <p>{place.phone_e164}</p>
              </>
            )}
          </Tile>
          {history.visits.length > 0 && (
            <Tile paper testId="provider-visits">
              <h2 class="title">{s.record.timeline}</h2>
              {history.visits.map((visit) => (
                <div class="lines" key={visit.appointment_id}>
                  <p>{fill(s.record.momentOn, { what: visit.purpose, date: dateOf(visit.scheduled_at) })}</p>
                  {visitStatusLine(visit.status, s) && <p class="caption">{visitStatusLine(visit.status, s)}</p>}
                </div>
              ))}
            </Tile>
          )}
          {history.papers.length > 0 && (
            <Tile paper testId="provider-papers">
              <h2 class="title">{s.record.illnessPapers}</h2>
              {history.papers.map((paper) => (
                <p key={paper.artifact.artifact_id}>{artifactLine(paper.artifact, dateOf(paper.artifact.captured_at), s)}</p>
              ))}
            </Tile>
          )}
          {history.medicines.length > 0 && (
            <Tile paper testId="provider-medicines">
              <h2 class="title">{s.record.medicinesFrom}</h2>
              {history.medicines.map((medicine) => (
                <p key={medicine.line_id} class="caption">
                  {medicine.generic} {medicine.strength}
                </p>
              ))}
            </Tile>
          )}
          {(history.notes.length > 0 || mayWrite) && (
            <Tile paper testId="provider-notes">
              <h2 class="title">{s.record.notesTitle}</h2>
              <p class="caption">{s.record.notesOnly}</p>
              {history.notes.map((note) => (
                <div class="lines" key={note.note_id} data-testid="place-note">
                  <p>{note.text}</p>
                  <p class="caption">{fill(s.record.writtenOn, { date: dateOf(note.written_at) })}</p>
                </div>
              ))}
              {mayWrite && (
                <>
                  <Field name="place-note" label={s.record.noteLabel} value={text} onInput={setText} maxLength={200} />
                  <Pill plum onClick={() => void save()} disabled={busy || text.trim().length === 0} testId="save-note">
                    {s.record.noteSave}
                  </Pill>
                </>
              )}
              {saved && (
                <p role="status" data-testid="note-saved">
                  {s.record.noteSaved}
                </p>
              )}
            </Tile>
          )}
          <Notice error={failure} />
        </>
      )}
    </RecordFrame>
  );
}

/** What changed since this reader last looked (E03-04): new facts, visits, keys, notes, and
 *  what is still waiting, in the backend's lines. Reading it is looking. */
export function ChangesScreen(): JSX.Element {
  const s = t();
  const { data: changes, error } = useRead(() => {
    const { bearer, profileId } = session();
    return nura.changes(bearer, profileId, language.value);
  }, [language.value]);
  return (
    <RecordFrame title={s.record.changes} back={{ name: "hub" }} testId="record-changes">
      <Notice error={error} />
      {changes && (
        <Tile paper testId="changes" >
          <div class="lines" data-testid="changes-lines">
            {changes.lines.map((line) => (
              <p key={line.key} data-section={line.section}>
                {line.text}
              </p>
            ))}
          </div>
          {changes.waiting.length > 0 && (
            <div class="lines" data-testid="changes-waiting">
              <p class="label">{s.record.waiting}</p>
              {changes.waiting.map((line) => (
                <p key={line.key}>{line.text}</p>
              ))}
            </div>
          )}
          <Hear lines={[...changes.lines.map((line) => line.text), ...changes.waiting.map((line) => line.text)]} />
        </Tile>
      )}
    </RecordFrame>
  );
}
