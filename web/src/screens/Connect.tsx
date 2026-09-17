import type { JSX } from "preact";
import * as family from "../api/family";
import * as nura from "../api/nura";
import type { DigestEntryOut, GrantOut } from "../api/familyTypes";
import type { FeedItemOut } from "../api/types";
import { useRead } from "./family/common";
import { startOfHisDay } from "../family/model";
import { variantOf } from "../feed/model";
import { go } from "../flow";
import { profile, token } from "../store/session";
import { language, LOCALE, t } from "../strings";
import { dateLine, timeLine } from "../today/model";
import { Card, Notice, Tile } from "../ui/components";
import { Avatar, FeatureTile, Icon, IconBadge, ListRow, PillButton, SectionHeader, TintCard } from "../ui/kit";
import { Shell } from "./Shell";

/** Connect (docs/design/nura-concept-board.html, the Connect screen): his family, his next
 *  call, what is near him, and the family thread, one glance each, before the existing Family
 *  screens each row opens. Every section reads what it shows: nothing here is typed outside
 *  the strings catalogue. A key without the family scope never reaches this screen — `nav.ts`
 *  leaves the tab off the bar before a tap could ask the backend for it. */
export function ConnectScreen(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  if (!bearer || !papers) return null;
  const lang = language.value;
  const locale = LOCALE[lang];
  const pid = papers.profile_id;
  return (
    <Shell tab="connect" testId="connect-screen">
      <h1 class="title place-title">{s.tabs.connect}</h1>
      <FamilySection bearer={bearer} profileId={pid} lang={lang} />
      <NextCallSection bearer={bearer} profileId={pid} lang={lang} locale={locale} />
      <NearYouSection bearer={bearer} profileId={pid} />
      <MessagesSection bearer={bearer} profileId={pid} lang={lang} locale={locale} />
    </Shell>
  );
}

/** "Your family": every key on his papers, as an avatar and a word — his relationship, in the
 *  backend's role words. Each avatar, "Add" and "See all" open the existing keys screen
 *  (`family/Keys.tsx`), the one place a key is cut, changed or closed. */
function FamilySection({ bearer, profileId, lang }: { bearer: string; profileId: string; lang: string }): JSX.Element {
  const s = t();
  const read = useRead(() => family.grants(bearer, profileId, lang), [profileId, lang]);
  const grants = read.value ?? [];
  const openKeys = () => go({ name: "family", part: "keys" });
  return (
    <section class="do-section" data-testid="connect-family">
      <SectionHeader title={s.connect.familyTitle} action={{ word: s.hub.seeAll, label: s.connect.seeAllFamily, onClick: () => go({ name: "family", part: "home" }), testId: "connect-family-all" }} />
      <Notice error={read.error} />
      {grants.length === 0 ? (
        <Card lines={[s.connect.noFamily]} testId="connect-no-family" />
      ) : (
        <div class="people-grid" data-testid="connect-family-grid">
          {grants.map((grant) => (
            <PersonTile key={grant.key_id} grant={grant} onClick={openKeys} />
          ))}
          <button type="button" class="person-tile" onClick={openKeys} data-testid="connect-add-person">
            <span class="avatar add" aria-hidden="true">
              <Icon name="add" />
            </span>
            <span class="person-name">{s.connect.addPerson}</span>
            <span class="person-role">{s.connect.addPersonLine}</span>
          </button>
        </div>
      )}
    </section>
  );
}

function PersonTile({ grant, onClick }: { grant: GrantOut; onClick: () => void }): JSX.Element {
  const s = t();
  return (
    <button type="button" class="person-tile" onClick={onClick} data-testid="connect-family-member">
      <Avatar name={grant.holder_name} tint="blush" />
      <span class="person-name">{grant.holder_name}</span>
      <span class="person-role">{s.family.roles[grant.role]}</span>
    </button>
  );
}

/** "Next call": the soonest call still ahead, from the calendar #235's backend keeps
 *  (`family.upcomingCalls`). "Call" dials `with_person_phone_e164` through the phone's own
 *  `tel:`; "Change" opens the calls screen (`family/Calls.tsx`) to reschedule or cancel it. */
function NextCallSection({ bearer, profileId, lang, locale }: { bearer: string; profileId: string; lang: string; locale: string }): JSX.Element {
  const s = t();
  const read = useRead(() => family.upcomingCalls(bearer, profileId, lang), [profileId, lang]);
  const next = (read.value ?? [])[0] ?? null;
  return (
    <section class="do-section" data-testid="connect-next-call">
      <SectionHeader title={s.connect.nextCallTitle} />
      <Notice error={read.error} />
      {!next ? (
        <Card lines={[s.connect.noCall]} testId="connect-no-call" />
      ) : (
        <TintCard tint="peach" testId="connect-call-card" extra="call-card">
          <p class="card-title">{next.label ?? next.with_person_name}</p>
          <p class="card-line">
            {dateLine(new Date(next.scheduled_at), locale)} · {timeLine(new Date(next.scheduled_at), locale)}
          </p>
          <div class="call-actions">
            {next.with_person_phone_e164 && (
              <PillButton
                variant="primary"
                compact
                icon="phone"
                onClick={() => {
                  window.location.href = `tel:${next.with_person_phone_e164}`;
                }}
                testId="connect-call-button"
              >
                {s.connect.call}
              </PillButton>
            )}
            <PillButton variant="secondary" compact onClick={() => go({ name: "family", part: "calls" })} testId="connect-change-call">
              {s.connect.change}
            </PillButton>
          </div>
        </TintCard>
      )}
    </section>
  );
}

/** "Near you": the feed's own local cards — dengue, haze, heat, events near his area
 *  (`ChiefPanels.tsx`'s same `local` kind) — never a stub tile. A tap opens the one card
 *  screen every feed card opens; "See all" opens the full feed. */
function NearYouSection({ bearer, profileId }: { bearer: string; profileId: string }): JSX.Element {
  const s = t();
  const read = useRead(() => nura.feed(bearer, profileId), [profileId]);
  const items = (read.value?.items ?? []).filter((item) => variantOf(item) === "local").slice(0, 3);
  return (
    <section class="do-section" data-testid="connect-near-you">
      <SectionHeader title={s.connect.nearYouTitle} action={{ word: s.hub.seeAll, label: s.connect.seeAllNearYou, onClick: () => go({ name: "feed" }), testId: "connect-near-all" }} />
      <Notice error={read.error} />
      {items.length === 0 ? (
        <Card lines={[s.connect.noNearYou]} testId="connect-no-near-you" />
      ) : (
        <div class="do-grid" data-testid="connect-near-grid">
          {items.map((item) => (
            <NearYouTile key={item.item_id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

function NearYouTile({ item }: { item: FeedItemOut }): JSX.Element {
  return <FeatureTile icon="place" tint="sage" label={item.headline} caption={item.body[0] ?? ""} onClick={() => go({ name: "card", item })} testId="connect-near-item" />;
}

/** "Messages": the family thread's freshest lines, the same words the digest already narrates
 *  (`family/Thread.tsx`) — never a raw row. A tap, and "See all", open the thread. */
function MessagesSection({ bearer, profileId, lang, locale }: { bearer: string; profileId: string; lang: string; locale: string }): JSX.Element {
  const s = t();
  const since = startOfHisDay(Date.now(), 0);
  const read = useRead(() => family.digest(bearer, profileId, since, lang), [profileId, lang]);
  const entries = (read.value?.entries ?? []).filter((entry) => entry.lines.length > 0).slice(0, 2);
  const openThread = () => go({ name: "family", part: "thread" });
  return (
    <section class="do-section" data-testid="connect-messages">
      <SectionHeader title={s.connect.messagesTitle} action={{ word: s.hub.seeAll, label: s.connect.seeAllMessages, onClick: openThread, testId: "connect-messages-all" }} />
      <Notice error={read.error} />
      {entries.length === 0 ? (
        <Card lines={[s.connect.noMessages]} testId="connect-no-messages" />
      ) : (
        <Tile paper testId="connect-messages-list">
          {entries.map((entry, at) => (
            <MessageRow key={at} entry={entry} locale={locale} onClick={openThread} />
          ))}
        </Tile>
      )}
    </section>
  );
}

function MessageRow({ entry, locale, onClick }: { entry: DigestEntryOut; locale: string; onClick: () => void }): JSX.Element {
  return (
    <ListRow
      lead={<IconBadge icon="speaker" tint="lavender" shape="circle" />}
      title={entry.lines[0] ?? ""}
      line={entry.text}
      trailing={timeLine(new Date(entry.at), locale)}
      onClick={onClick}
      testId="connect-message-row"
    />
  );
}
