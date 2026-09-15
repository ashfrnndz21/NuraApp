import { useEffect, useState } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import * as nura from "../api/nura";
import type { AppointmentOut, LineOut } from "../api/types";
import { go } from "../flow";
import { startOnboarding } from "../onboarding/state";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine, lineTitle, questionLines, timeLine } from "../today/model";
import { Card, Hear, Notice } from "../ui/components";
import { FeedCard, Icon, PaperTile, PillButton } from "../ui/kit";
import { Shell } from "./Shell";

/** The tabs that are not Today (D1, stage 1). Each is one screen of what the app already has,
 *  in the new shell; the Record's and the Family's own screens (W5, W6) take their places as
 *  they land, and every one is restyled in stage 2. */

function PlaceTitle({ children }: { children: ComponentChildren }): JSX.Element {
  return <h1 class="title place-title">{children}</h1>;
}

function useOwner(): { own: boolean; name: string } {
  const papers = profile.value;
  return { own: papers?.standing === "owner", name: papers?.display_name ?? "" };
}

/** The visits, the spine of the record: each one's day and time, what it is for, and — for the
 *  next one — its brief and its questions. */
function VisitList(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const { own, name } = useOwner();
  const locale = LOCALE[language.value];
  const [visits, setVisits] = useState<AppointmentOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.appointments(bearer, papers.profile_id).then(setVisits, (failure: unknown) => {
      setVisits([]);
      setError(failure);
    });
  }, [bearer, papers?.profile_id]);
  if (!visits) return null;
  if (visits.length === 0) {
    return (
      <>
        <Notice error={error} />
        {!error && <Card lines={[own ? s.visit.none : fill(s.places.visitsNoneOther, { name })]} testId="no-visits" />}
      </>
    );
  }
  return (
    <>
      {visits.map((visit, at) => {
        const when = new Date(visit.scheduled_at);
        return (
          <PaperTile key={visit.appointment_id} testId="visit-item">
            <div class="card-head">
              <span class="card-icon">
                <Icon name="visits" />
              </span>
              <div>
                <h2 class="title">{dateLine(when, locale)}</h2>
                <p class="source-line">{timeLine(when, locale)}</p>
              </div>
            </div>
            {visit.purpose && <p>{visit.purpose}</p>}
            {at === 0 && (
              <>
                <PillButton onClick={() => go({ name: "visit", appointmentId: visit.appointment_id })} testId="visit-open">
                  {s.visit.open}
                </PillButton>
                <PillButton onClick={() => go({ name: "brief", appointmentId: visit.appointment_id })} testId="visit-brief">
                  {s.day.briefOpen}
                </PillButton>
                <PillButton onClick={() => go({ name: "questions", appointmentId: visit.appointment_id })} testId="visit-questions">
                  {s.day.questionsOpen}
                </PillButton>
              </>
            )}
          </PaperTile>
        );
      })}
    </>
  );
}

export function VisitsScreen(): JSX.Element {
  const s = t();
  const { own, name } = useOwner();
  return (
    <Shell tab="visits" testId="visits-screen">
      <PlaceTitle>{own ? s.places.visitsOwn : fill(s.places.visitsOther, { name })}</PlaceTitle>
      <VisitList />
    </Shell>
  );
}

/** The plan (stage 1): getting ready for the next visit, a blood pressure to write down, and
 *  setting up from the papers. */
export function PlanScreen(): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [next, setNext] = useState<AppointmentOut | null>(null);
  useEffect(() => {
    if (!bearer || !papers || !papers.scopes.includes("visits")) return;
    nura.appointments(bearer, papers.profile_id).then(
      (found) => setNext(found[0] ?? null),
      () => setNext(null),
    );
  }, [bearer, papers?.profile_id]);
  return (
    <Shell tab="plan" testId="plan-screen">
      <PlaceTitle>{s.places.planTitle}</PlaceTitle>
      {papers?.scopes.includes("medicines") && (
        <PaperTile testId="plan-routine-tile">
          <PillButton onClick={() => go({ name: "record", at: { name: "routine" } })} testId="plan-routine">
            {s.record.routine}
          </PillButton>
        </PaperTile>
      )}
      <PaperTile testId="plan-ready">
        <p>{s.places.planLead}</p>
        {next && (
          <>
            <PillButton onClick={() => go({ name: "visit", appointmentId: next.appointment_id })} testId="plan-visit">
              {s.visit.open}
            </PillButton>
            <PillButton onClick={() => go({ name: "brief", appointmentId: next.appointment_id })} testId="plan-brief">
              {s.day.briefOpen}
            </PillButton>
            <PillButton onClick={() => go({ name: "questions", appointmentId: next.appointment_id })} testId="plan-questions">
              {s.day.questionsOpen}
            </PillButton>
          </>
        )}
        <PillButton onClick={() => go({ name: "reading" })} testId="plan-reading">
          {s.today.readingTitle}
        </PillButton>
        {papers && (
          <PillButton onClick={() => void startOnboarding(papers)} testId="plan-set-up">
            {s.me.setUp}
          </PillButton>
        )}
      </PaperTile>
    </Shell>
  );
}
