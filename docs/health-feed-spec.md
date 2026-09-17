# Health feed — build specification (iOS)

The feed is the "For you today" section of Today and its "More for you" tail for the patient, the "For Pa this week" list and "Watching" panel for the caregiver, and the "Worth knowing this month" block in the Doctor Memo. This document specifies how it is built end to end.

---

## 0. The shape: a vertical, full-screen feed

The feed is a vertical pager: one card fills the screen, swipe up for the next, each card speaks when it arrives. This is the TikTok interaction model and it suits an older person better than a list, because it is one thing at a time and one gesture.

What differs from TikTok is the supply and the incentives.

**Order of supply for the patient.** Now (the tablet, the reading, the visit) → Today (one or two cards made for him today) → a gate ("That is all that is new. Keep going?") → His story (recall cards from his own record: what the doctor said, how a number changed, a family photo) → Learning (evergreen explainers about his conditions and medicines from allowed sources). Past the gate the feed is effectively endless, and everything in it is still about him.

**Order of supply for the caregiver and for adults managing their own health.** The same pager with no gate, denser cards, sources on every card, and doctor questions inline. Genuinely endless.

**Never.** No autoplay of the next card; each waits. No counts, badges or rewards. No content that isn't about the profile or isn't from an allowed source. No doctor questions or safety notices in the patient's feed. No optimisation for time in the feed: the metric is the tablet card being acted on, not minutes watched.

## 1. Placement

| Surface | What shows | Cap |
|---|---|---|
| Patient · Today (vertical pager) | Now → Today (1–2 new cards) → gate → His story → Learning | 2 new per day; endless past the gate |
| Patient · WhatsApp | The top card as a message with voice note | 1 per day |
| Patient · Home Screen widget | The top card's headline | — |
| Caregiver · For Pa | Every item generated this week with status (sent, opened, held), source, and actions | none |
| Caregiver · Watching | Active search jobs with source and cadence; add or pause | — |
| Doctor Memo · Worth knowing this month | Held items that are doctor questions | 3 |

Held items never reach the patient: doctor questions go to the memo; notices with nothing to do stay in the caregiver's list.

---

## 2. Card types

| Type | Trigger | Content | Format |
|---|---|---|---|
| Explainer | New result, new medicine, new diagnosis | What it is, in plain words, for him | Text card + voice note; clip in T3 |
| Compressed video | A new medicine or condition with an allowlisted explainer video | The 20–30 seconds that apply, narrated | Clip with captions + link to full video |
| Own-data insight | A trend or a comparison | One number, one direction, one sentence | Text card + voice |
| Local alert | Environmental or outbreak bulletin matching address and conditions | What to do today | Text card |
| Food and habit | Weekly, by conditions and season | One concrete choice | Text card |
| Safety notice | Regulator or manufacturer notice matching a medicine | Checked against pack batch; **never a card in his feed** — held for the chief, and for the memo where it is a question for the doctor | Held |
| Recall action | A safety notice whose batch matches his own pack (#183) | What he can do about the box in his hand today, in his own words, ending on the boundary line — never the notice's own words | Text card + voice |
| Worth knowing | Guideline change, formulary addition, new option | Framed as a question for the doctor | Held → Doctor Memo |
| Seasonal | Fasting month, festive food, travel | Timing and food adjustments | Text card |

**A safety notice is never his card** (resolved 2026-09-16; §0 wins). This table and §9 once
read as though a notice matching the batch on his pack could be sent to him as a text card,
while §0 says no safety notices in the patient's feed. §0 is the rule. A regulator's notice
about one of his medicines is held for the chief, and where it is a question for his doctor it
goes to the memo — it is never a card he reads.

What he sees instead is a card about something **he** must do, in his own words, made the way
every other card of his is made and read by the pharmacist's first fifty before it reaches him
(`REVIEWED_TYPES`, `app/language/review.py`). "Your pack is one of the batches; bring it to the
pharmacy" is his card, because it is his to act on. "This batch was recalled" is not.

**The code does this now** (#181, #183, #224, #236). `app/delivery/feed/search.py` holds
every safety notice for the chief, batch match or not — unconditionally, so a notice never
reaches nobody (#224 review finding: a `continue` used to skip the caregiver notice whenever
its words also changed treatment). One whose words would start, stop or change a medicine is
never sent in its own words to any audience, hers included: `app/delivery/feed/items.py`'s
`create_item` refuses a `TreatmentChangingCard` outright, the same choke point that refuses a
`NOTICE` built for the patient (`NoticeNotForPatient`), so no later job or caller can send
either by mistake. Instead her card is rerouted to a fixed line
(`app/delivery/strings.py:needs_doctor_look_lines`) and a real question is filed for the
doctor through `reasoning.visits.memos.write_memo` (`search._ask_the_doctor`) — the same door
the post-visit summary uses, never a `FeedItem` nothing reads. It is still sampled for the
pharmacist's first fifty like every other reviewed type, whoever it is held for
(`app/language/review.py`).

**Built** (#183). `CardType.RECALL_ACTION` is his own card, independent of whether the
notice above was rerouted: only where the batch on his own pack matches, `search.py`'s
`JobKind.SAFETY` branch additionally writes a `RECALL_ACTION` card to `DeliverTo.PATIENT`
(`app/delivery/strings.py:recall_action_lines`) — in his own words, from the catalogue,
ending on the boundary line, never a word of the notice's own. `tests/test_feed.py` asserts
all of it: a matching recall gives him the action card and his chief the notice; a recall
that needs nothing of him reaches only his chief; and a recall that both matches his batch
and changes treatment still gives him the action card even though the notice itself is
rerouted to a doctor question.


Every card carries: `headline`, `body` (plain words), `why` (one sentence, plain), `source` (name, URL, date), `profileRefs` (facts it was built from), `format`, `language`, `audioURL`, `mediaURL`, `expiresAt`, `deliverTo` (patient / caregiver / memo).

---

## 3. Pipeline (backend)

1. **Jobs from State.** When State changes or on schedule, a job planner emits `SearchJob{profileId, kind, query terms, sources, cadence, reason}`. Kinds: explainer, safety, local, food, provider, worth-knowing, seasonal. Terms are derived from conditions, medicines (generic + brand + registration number), address, and calendar.
2. **Fetch.** Allowlisted sources only: regulator feeds (HSA, NPRA), ministry pages, hospital-group sites and video channels, professional societies. Fetch via RSS/APIs where available, otherwise a fetcher with robots respect and a cache. Video: YouTube Data API for allowlisted channels; transcripts via captions or Transcribe.
3. **Filter.** Relevance scoring against State: condition match, medicine match (exact generic or registration number), region match, recency, novelty (not seen by this profile), duplication across sources. Safety notices additionally match the batch number from the pack photo.
4. **Compress.** An LLM step with strict grounding: input is the source text or transcript plus the profile's relevant facts; output is `headline`, `body`, `why`, and for video `startSec`/`endSec`, all in the plain-words standard, in the profile's language. Output must cite the passage or timestamp it came from; uncited output is rejected. Anything that could change treatment is rewritten as a question for the doctor and routed to `memo`.
5. **Verify.** Automated checks: source is on the allowlist; every claim maps to a cited passage; readability score under the threshold; no banned words (glossary); boundary line present for inferring cards. Safety notices and worth-knowing items are queued for the pharmacist's review before first use of a new source; thereafter spot-checked.
6. **Localise and voice.** Translate body and why into the profile's language; synthesise audio (Polly for English, Malay, Mandarin; recorded or vendor voice for Hokkien); captions for clips; render a 20–30 s clip from a still or the licensed excerpt.
7. **Rank.** `score = urgency × relevance × novelty × formatFit × freshness`, with State-driven boosts (post-discharge, new medicine). Two-per-day cap, none on alert days, quiet hours respected. Held items get `deliverTo: caregiver` or `memo`.
8. **Deliver.** Write `FeedItem` rows; push a silent notification so the app refreshes; send the WhatsApp template for the top card if the patient is on WhatsApp; update the widget timeline.
9. **Learn.** Engagement events (opened, played, replayed, dismissed, asked-more) feed novelty and format fit; two ignored text cards flip the profile's preferred format to voice.

---

## 4. Data model

```
FeedItem(id, profileId, type, headline, body, why, language,
         source{name,url,publishedAt}, refs[factId], startSec?, endSec?,
         audioURL?, mediaURL?, captionsURL?, score, deliverTo,
         status{generated|held|sent|opened|played|dismissed}, createdAt, expiresAt)
SearchJob(id, profileId, kind, terms[], sources[], cadence, reason, lastRunAt, enabled)
Source(id, name, domain, kind, allowlisted, reviewStatus)
Engagement(itemId, profileId, personId, event, at, channel)
```

Items are scoped to a profile and encrypted with the profile's key. Sources are global.

---

## 5. API

```
GET  /profiles/{id}/feed?since=&audience=patient|caregiver   → [FeedItem]
POST /profiles/{id}/feed/{itemId}/events                     {event, channel}
GET  /profiles/{id}/watches                                  → [SearchJob]
POST /profiles/{id}/watches                                  {kind, terms, cadence}
PATCH /profiles/{id}/watches/{jobId}                         {enabled}
POST /profiles/{id}/feed/{itemId}/memo                       (add held item to the memo)
```

All calls carry the caller's key; scope enforcement filters items the key doesn't cover. Responses are cacheable with ETag.

---

## 6. iOS implementation

**Architecture.** SwiftUI, MVVM with an observable `FeedStore`. SwiftData cache of `FeedItem` for offline reading and instant launch. Networking through `URLSession` with async/await; ETag-based delta sync.

**Views.**
- `FeedPagerView`: a vertical `ScrollView` with `LazyVStack`, `.scrollTargetBehavior(.paging)` and `containerRelativeFrame(.vertical)` so each card fills the screen (iOS 17+); `scrollPosition` bound to the current item so the store knows which card is on screen. Cards are `FeedCardView` instances sized to the container.
- Supply: `FeedStore` exposes an ordered, cursor-paginated stream: `now`, `today`, `gate`, `story`, `learning`. Prefetch two cards ahead; append the next page when the last visible index is within two of the end. The gate is a real card; "Keep going" advances the cursor into `story`.
- Playback: the card on screen plays its voice note or clip on tap, never automatically on the next card; `AVQueuePlayer` warms the next asset while the current one plays. Captions render in the card body as the audio plays.
- `FeedCardView` switches on `type`: text, own-data (with a `Sparkline` shape), clip (poster + play), local, food. One action per card; `why` behind a disclosure in Chief mode, visible in patient mode.
- `ClipPlayerView`: `AVPlayer` with HLS or MP4, captions via `AVMediaSelection` or a synced caption view, large play target, playback rate 0.9 in patient mode.
- `VoiceNoteButton`: plays pre-rendered audio; falls back to `AVSpeechSynthesizer` for English, Malay and Mandarin if audio is missing.
- Caregiver: `ForPaFeedView` (list with status tags, source rows, actions) and `WatchesView` (toggle, add).

**Refresh.** `BGAppRefreshTask` scheduled daily; silent APNs push (`content-available`) on new items; pull-to-refresh in caregiver mode only (patient mode never shows a spinner or a pull gesture).

**Widgets.** `WidgetKit` medium widget: the top card headline and the Now item; timeline updated on push. Lock Screen widget stays the emergency card.

**Voice and accessibility.** Every card has an `accessibilityLabel` equal to its spoken script. Dynamic Type through accessibility sizes; layout tested at the largest. Reduce Motion disables card transitions. VoiceOver order: Now, For you, More for you.

**Patient mode constraints.** Vertical paging only, no horizontal gestures, no pull-to-refresh, no long-press. "Not for me" is a visible button on every card. The gate card sits between today's cards and the evergreen supply. No badges, no unread counts, no watched counters.

**Analytics.** Local event queue → `POST events` on next connection: opened, played (with seconds), replayed, dismissed, asked-more, shared.

**Localisation.** Strings externalised; body content arrives already localised from the backend; UI chrome via `String(localized:)` for English, Malay, Mandarin.

---

## 7. Safety and compliance

- Allowlist is data, reviewed quarterly by the pharmacist; adding a source requires review.
- No card may contain advice to start, stop or change a medicine; the verify step rejects it and reroutes to the memo as a question.
- Every card shows its source and why it exists; the boundary line appears on inferring cards.
- Video excerpts: link to the original, attribute the channel, keep excerpts within the platform's terms; prefer sources whose licences allow reuse, and fall back to a still plus narration where they don't.
- PDPA: feed items are profile data; they export and delete with the profile.
- App Review: the feed is informational content tied to a user's own data; the listing describes it that way.

---

## 8. Metrics

Cards sent per profile per week (target ≤ 10); open rate by type and format; play completion for clips; "asked-more" rate; dismiss rate (a health signal, not a failure); held-to-memo conversion; format switches; zero cards from non-allowlisted sources (hard check).

---

## 9. Acceptance criteria (v1)

- A new lab result produces an explainer card within 10 minutes, in the profile's language, with a voice note, citing the result and one allowlisted page.
- A new medicine produces an explainer and starts a daily safety-notice job within 1 minute.
- A safety notice is never a card in the patient's feed, whether or not it matches the batch on his pack: it is held for the caregiver, and for the doctor memo where it is a question for the doctor (§0, and the note under §2). Where there is something *he* must do, he gets his own card saying that, in his words, after the pharmacist's review.
- The patient's feed shows Now first, at most 2 new cards for today, then the gate card; past the gate it pages endlessly through his own story and evergreen learning without a single card from outside the allowlist or outside his profile.
- No card starts audio or video by itself; the next card never autoplays.
- Two unopened text cards switch the profile to voice-first delivery.
- Every card passes the plain-words check and shows source and why.
- Offline launch shows the last cached feed with no spinner.

---

## 10. Build estimate

Backend (jobs, fetch, filter, compress, verify, rank, API): one engineer, 4 weeks for text cards; +2 weeks for voice; +4 weeks for video compression and clip rendering.
iOS (views, store, cache, refresh, push, widget, player, accessibility): one engineer, 4 weeks for text and voice; +2 weeks for clips.
Pharmacist review of the initial allowlist and the first 50 cards: 8 hours.

Text-and-voice feed on TestFlight in 4–5 weeks with two engineers; clips in the following month.
