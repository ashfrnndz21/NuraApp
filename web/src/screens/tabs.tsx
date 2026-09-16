import { useEffect, useState } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import * as nura from "../api/nura";
import type { AppointmentOut } from "../api/types";
import { go } from "../flow";
import { startOnboarding } from "../onboarding/state";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine, timeLine } from "../today/model";
import { Card, Notice } from "../ui/components";
import { Icon, PaperTile, PillButton, SectionLabel } from "../ui/kit";
import { Shell } from "./Shell";

/** The Visits tab (D1, one tab set): his visits — the spine of the record — and, under them,
 *  getting ready for the next one. This is the surface the design system calls Visits for him
 *  and Plan for her; it is one screen for both, because it answers one question either way. */

function PlaceTitle({ children }: { children: ComponentChildren }): JSX.Element {
  return <h1 class="title place-title">{children}</h1>;
}

function useOwner(): { own: boolean; name: string } {
  const papers = profile.value;
  return { own: papers?.standing === "owner", name: papers?.display_name ?? "" };
}

/** The visits: each one's day and time, what it is for, and — for the next one — its brief and
 *  its questions, as rows: an icon, the word, the way in. */
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
    nura.appointments(bearer, papers.profile_id).then(
      setVisits,
      (failure: unknown) => {
        setVisits([]);
        setError(failure);
      },
    );
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
              <nav class="place-rows" aria-label={s.visit.open}>
                <button type="button" class="place-row" onClick={() => go({ name: "visit", appointmentId: visit.appointment_id })} data-testid="visit-open">
                  <Icon name="visits" />
                  <span class="place-word">{s.visit.open}</span>
                  <Icon name="chevron" />
                </button>
                <button type="button" class="place-row" onClick={() => go({ name: "brief", appointmentId: visit.appointment_id })} data-testid="visit-brief">
                  <Icon name="records" />
                  <span class="place-word">{s.day.briefOpen}</span>
                  <Icon name="chevron" />
                </button>
                <button type="button" class="place-row" onClick={() => go({ name: "questions", appointmentId: visit.appointment_id })} data-testid="visit-questions">
                  <Icon name="note" />
                  <span class="place-word">{s.day.questionsOpen}</span>
                  <Icon name="chevron" />
                </button>
              </nav>
            )}
          </PaperTile>
        );
      })}
    </>
  );
}

/** Getting ready for the next visit: his day's routine, a blood pressure to write down, and
 *  setting up from the papers. One Plum button at most, so the rows carry the rest. */
function GettingReady(): JSX.Element {
  const s = t();
  const papers = profile.value;
  return (
    <>
      <SectionLabel>{s.places.planTitle}</SectionLabel>
      <PaperTile testId="plan-ready">
        <p>{s.places.planLead}</p>
        <nav class="place-rows" aria-label={s.places.planTitle}>
          {papers?.scopes.includes("medicines") && (
            <button type="button" class="place-row" onClick={() => go({ name: "record", at: { name: "routine" } })} data-testid="plan-routine">
              <Icon name="today" />
              <span class="place-word">{s.record.routine}</span>
              <Icon name="chevron" />
            </button>
          )}
          {papers?.scopes.includes("readings") && (
            <button type="button" class="place-row" onClick={() => go({ name: "reading" })} data-testid="plan-reading">
              <Icon name="records" />
              <span class="place-word">{s.today.readingTitle}</span>
              <Icon name="chevron" />
            </button>
          )}
        </nav>
        {papers && (
          <PillButton onClick={() => void startOnboarding(papers)} testId="plan-set-up">
            {s.me.setUp}
          </PillButton>
        )}
      </PaperTile>
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
      <GettingReady />
    </Shell>
  );
}
