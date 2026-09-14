# ADR 0012 — The not-feeling-well cards for no network

Status: accepted (W7, the web client's patient day)

## Context

The not-feeling-well button (E13-02) and a red word on the feeling cloud (E17-02) are the two
paths where showing nothing is the worst outcome. On a phone they fail exactly when they are
needed: a lift, a basement car park, a hospital corridor. Two rules stand in the way of the
phone simply saying something itself:

- **The client composes no sentence.** Every line the patient reads is the backend's, verified
  by `app.safety.plain_words` and inside the boundary (`app.safety.boundary`, E16).
- **The red-flag decision is the backend's.** The words are read against one table
  (`app.safety.red_flags.detect`); the phone never guesses whether "chest pain" is red.

With no network, the backend cannot be asked for the card, nothing is written, and nobody is
told. Whatever the phone shows must not say "Mei knows now."

## Decision

1. **The backend defines two offline cards**, `GET /profiles/{id}/not-feeling-well/offline`
   (`app.safety.not_feeling_well.offline_cards`), read under the button's door (EMERGENCY, which
   every role holds), from the same catalogue as every what-to-do line
   (`app.channels.safety_strings`, `nfw.offline_*`), each line through `render`, inside the
   urgent shape of the not-feeling-well boundary:
   - `red_flag` — a red word tapped with no network: "You did right to say so." / "Nura could not
     send this to your family." / "Call the ambulance now on 995." / "After that, call Mei." /
     "Nura does not decide what is wrong."
   - `unknown` — the button pressed with no network, where nobody has read the words: "You did
     right to say so." / "Nura could not send this to your family." / "Call Mei now." / "If you
     feel very bad, call the ambulance now on 995." / "Nura does not decide what is wrong."
   The region picks the number (995, 999); the chief is whoever the button would name now, and
   "Call your family now." when there is nobody. Reading them writes nothing and escalates
   nothing.
2. **The phone keeps them** (`web/src/day/offline.ts`), bound to the key and parts that read them
   like every page it keeps (`todayCache.KEPT_PREFIXES` names `nfw.`, so a refusal, a switch of
   profile and sign-out delete them), read again once a day and in a new language, from Today
   whenever it is live.
3. **The last resort is the same words, built in.** A phone that kept no copy (cleared storage, a
   first launch that never reached Today) shows the catalogue's copy of the backend's card
   (`web/src/strings/*.ts`, `day.fallback`) for the profile's region, without the chief's name.
   `make language` holds those lines to the backend's own translations, one Malay and one Chinese
   line per English line, so the copy cannot drift.
4. **Which card.** A red word that could not be sent shows `red_flag`. The button, a failed answer
   to a tapped word's question, and a failed symptom send show `unknown`: the phone cannot tell
   whether the words were red, so it gives the calls without claiming anything was decided. A
   refusal (a 4xx) shows the refusal's sentence above the same card; the page says the phone is
   offline only when it is.
5. **A red word goes first when there is a network.** The client's one queue (`api/client.ts`)
   has an urgent lane: the red word's tap, its answer, the button and a symptom send go next,
   ahead of every read still waiting, behind only the one already on the wire. Calls still go one
   at a time (the dev database refuses two writes at once).

## Consequences

- The patient is never left with nothing, and never told the family knows when nobody was told.
- The `unknown` card may tell someone who is only tired to call the family, and the ambulance if
  it is very bad: the phone errs towards a call it cannot make for him.
- Nothing pressed with no network is queued and sent later from here. W4's offline tap queue
  (ADR 0010) may replay a feeling tap when the network returns; if it does, the flag and the
  family's notice come then, and the ladder with them.
- A red flag in the symptom log (E14-01) escalates on the backend exactly as the button does, but
  that route returns no what-to-do card; the web goes back to Today, where the flag's card is
  first. A card on that route is a follow-up for the backend.
