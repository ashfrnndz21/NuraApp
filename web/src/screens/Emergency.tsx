import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { go } from "../flow";
import { dropCard, emergencyOnly, keepsCard, loadCard, readCard, saveCard, type KeptCard } from "../offline/emergencyCache";
import { wantsHomeScreenHint } from "../offline/register";
import { bindingOf } from "../offline/todayCache";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine } from "../today/model";
import { Card, Header, Hear, Notice, Pill, Tile } from "../ui/components";
import { Shell } from "./Shell";

/** Open the backend's printable page for this card in a new tab, from the copy the phone
 *  kept — so it opens with no network too — for the phone's own Print (E13-01's page: paper,
 *  20px, high contrast, nothing fetched). */
function openPrintable(html: string): void {
  const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** The emergency card on the phone (E00-08, E13-01, ADR 0001's "the card one tap away"): its
 *  lines are the backend's verified sentences in his language and nothing else; the numbers to
 *  call are the card's data, as buttons; a big Print opens the backend's printable page. It is
 *  readable with no network and always says when it was read. */
export function EmergencyCard({ kept }: { kept: KeptCard }): JSX.Element {
  const s = t();
  const locale = LOCALE[language.value];
  const card = kept.card;
  const lines = card.lines.map((line) => line.text);
  const read = new Date(kept.fetchedAt);
  const callable = [...card.contacts].sort((a, b) => Number(b.role === "chief") - Number(a.role === "chief")).filter((each) => each.phone_e164);
  return (
    <Tile paper testId="emergency-card">
      <h2 class="title">{s.today.emergencyTitle}</h2>
      <div class="lines" data-testid="emergency-lines">
        {lines.map((line, at) => (
          <p key={at}>{line}</p>
        ))}
      </div>
      {card.medicines.length > 0 && (
        // The register's own name and strength for every active medicine, as data beside
        // the lines above — never through a sentence, so it does not depend on whether his
        // plain name could stand beside it there (`_medicine_label`, #222/#229). A stranger
        // reading this on the phone, not only on the printed page, needs "frusemide 40 mg",
        // not only "the water pill": these values are the register's, the same in every
        // language, so this is not `@patient` text and is not run through plain-words —
        // exactly the principle `emergency_card.py:132-133` already states for `strength`
        // and `generic`.
        <div class="medicine-data" data-testid="medicine-data">
          {card.medicines.map((medicine) => (
            <p key={medicine.line_id} class="caption" data-testid="medicine-chemical-name">
              {medicine.generic}{medicine.strength ? `, ${medicine.strength}` : ""}
              {medicine.high_risk_label && (
                // The word itself is the backend's (A3, clinical-safety review on #229's
                // own PR): catalogued, plain-words checked, in his language — never typed
                // into this screen outside the verified `render()` path the rest of the
                // card already goes through. Only the separating dot is ours.
                <strong data-testid="medicine-high-risk"> · {medicine.high_risk_label}</strong>
              )}
            </p>
          ))}
        </div>
      )}
      {callable.map((contact) => (
        <a key={contact.person_id} class="pill" href={`tel:${contact.phone_e164}`} data-testid="call-contact">
          {fill(s.emergency.callChief, { name: contact.name })}
        </a>
      ))}
      <a class="pill" href={`tel:${card.emergency_number}`} data-testid="call-ambulance">
        {fill(s.emergency.callAmbulance, { number: card.emergency_number })}
      </a>
      {kept.html && (
        <Pill plum onClick={() => openPrintable(kept.html!)} testId="print-card">
          {s.emergency.print}
        </Pill>
      )}
      <p class="provenance" data-testid="emergency-read">
        {fill(s.emergency.asOf, { date: dateLine(read, locale) })}
      </p>
      <Hear lines={lines} />
    </Tile>
  );
}

export function EmergencyScreen(): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [kept, setKept] = useState<KeptCard | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!bearer || !papers) return;
    const binding = bindingOf(papers);
    const id = papers.profile_id;
    void (async () => {
      const found = await loadCard(id, binding);
      setKept(found);
      try {
        setKept(await saveCard(id, await readCard(bearer, id, language.value), binding, new Date(), found));
      } catch (failure) {
        // No network, or a State behind the record: the card the phone kept stands, dated.
        if (keepsCard(failure)) return;
        // A no to this key: nothing of the card stays on the phone, and it is said.
        await dropCard(id);
        setKept(null);
        setError(failure);
      } finally {
        setLoaded(true);
      }
    })();
  }, [bearer, papers?.profile_id, language.value]);

  // An emergency-only key (a neighbour's) has the card and nothing else: no way back to a Today.
  const only = papers ? emergencyOnly(papers) : false;
  return (
    <Shell tab={only ? "today" : null} testId="emergency-screen">
      <Header title={s.today.emergencyTitle} onBack={only ? undefined : () => go({ name: "today" })} />
      <Notice error={error} />
      {kept ? (
        <EmergencyCard kept={kept} />
      ) : (
        loaded && !error && <Card lines={[s.emergency.none, s.emergency.noneSub]} testId="emergency-none" />
      )}
      {wantsHomeScreenHint() && (
        <Tile glass testId="home-screen-hint">
          <p>{s.today.homeScreen1}</p>
          <p>{s.today.homeScreen2}</p>
          <p>{s.today.homeScreen3}</p>
        </Tile>
      )}
    </Shell>
  );
}
