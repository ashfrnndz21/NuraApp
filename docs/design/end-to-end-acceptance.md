# End-to-end acceptance specification — what "the entire app works" means

**Status: binding.** This is the gate ADR 0019's Consequences names: *"The signed build is the
extreme last step (owner, 22 Sep 23:30). Apple Developer + EAS … happens only after the entire
app works end to end … verified in the iOS Simulator (once Xcode is installed) and in Expo Go. No
builder may start EAS or signing work before the owner says the app is complete."*
(`docs/adr/0019-one-stateful-system-nura-run-and-the-event-protocol.md`, Consequences). Every item
below is a condition of that gate. Nothing in this document authorises step 6; only the owner does,
once every item here is ticked on the sign-off sheet in §13.

Every item is numbered **A-001** upward and carries: the observable behaviour in the person's own
words, the exact pass criterion, the safety/data rule it depends on, how it is verified, and the
blueprint scene / user story / defect it comes from. Where a source is silent on a detail, this
document says **"(to be specified by the owner)"** rather than inventing one. No dates or hours
appear anywhere below, per the same rule this repository applies to itself.

**Sources**, cited throughout by short name:

- **ADR 0019** — `docs/adr/0019-one-stateful-system-nura-run-and-the-event-protocol.md`
- **design-build-2** — `docs/design/design-build-2.md` (the 32-section experience spec, §1; the
  delivery checklist, §3; the twelve-step plan, §4)
- **reading** — `docs/design/design-build-2-reading.md` (the 26-scene reading, step 1)
- **map** — `docs/design/design-build-2-map.md` (the 56-moment interaction map and three state
  machines, step 2)
- **mobile-architecture** — `docs/design/mobile-architecture.md` (the native stack, the `AIState`
  table, §3)
- **product-spec** — `git show origin/product-spec-doc:docs/NURA-PRODUCT-SPEC.md` (user stories,
  Built/Partly/Not built, §2–§8)
- **blueprint-v2** — `git show origin/blueprint-v2:docs/design/experience-blueprint-v2.html` (33
  scenes, the `:root` motion tokens, the `SC` array's `s.see`/`s.does` prose)
- **audit** — `docs/design/audit-2026-09-22.md` (§2 screen-by-screen, §3 intelligence layer, §5
  defects D-0…D-25, §7 Part D agentic-system analysis)
- **build-spec** — `docs/design/build-spec.md` (packages 1–24, incl. 7a whose-paper and 24 ASEAN)
- **plain-words** — `docs/plain-words.md` (the thirteen rules, the glossary, the `kind="ask"`
  profile)
- **feed-spec** — `docs/health-feed-spec.md` (feed safety rules, card types, acceptance criteria)
- **scopes** — `backend/app/keys/scopes.py` (roles, scopes, key windows)
- **strings** — `web/src/strings/en.ts` (the real patient-facing wording, quoted with line numbers)

---

## 0. Definitions

**A-001 — "Works."** A behaviour "works" when it is **true of the running app against the real
FastAPI backend** (fixture or live-AI adapter, per §9), not true of a mock, a storyboard or the
blueprint's own JS. The blueprint (`blueprint-v2`) is the *reference for the interaction*, never
the thing being tested — every scene's `s.see`/`s.does` text is a target, not a stand-in for a
real screen. *Source: design-build-2 §1 ("a real, production-quality consumer application … not a
static mockup"); ADR 0019 point 2 ("the screen is a projection of state").*

**A-002 — "Verified."** An item is verified only when the method named in its own row has actually
run and produced the stated evidence (a capture, a passing test, a measured trace, an audit-log
row) — not when a person believes it works. Where an item names more than one method (e.g. Simulator
*and* Expo Go), **both** must pass independently; a pass in one engine never substitutes for the
other, because the audit's single largest finding was an engine-specific failure invisible on the
other engine (D-0, WebKit-only). *Source: audit §1, §5 D-0; ADR 0019 Consequences.*

**A-003 — The three engines.** (a) **iOS Simulator** — once Xcode is installed on the build Mac,
the native or web-in-simulator target running under a simulated device. (b) **Expo Go** — the
native/Expo path running on the owner's own iPhone, the real hardware and the real WebKit-class
engine. (c) **Web** — Chromium and WebKit via Playwright, the client that exists today and remains
the fallback for the caregiver on a desktop (mobile-architecture §2). A "both engines" requirement
below always means Chromium *and* WebKit for a web-only item, and Simulator *and* Expo Go for a
native item, per the ADR's own closing sentence. *Source: ADR 0019 Consequences; mobile-architecture
§5; design-build-2 §3.*

**A-004 — Roles.** **Pa** — the patient; elderly; reads in Malay, Chinese or English; sometimes
reached only on WhatsApp; holds a `KeyRole.CHIEF` key by default over his own profile (`scopes.py`
`ALL_SCOPES`). **Mei** — the caregiver; holds a chief key over Pa's profile in the demo seed
("every scope, the same window as any chief's" — product-spec §1); day-to-day runs his care. **A
clinic key** — `KeyRole.CLINIC`, scoped to `PROFILE, MEDICINES, VISITS, READINGS, RECORDS`, windowed
`SEVENTY_TWO_HOURS`, never `NOTES` or `MONEY` (`scopes.py` `ROLE_SCOPES`, `DEFAULT_WINDOW`). **A
viewer** — `KeyRole.VIEWER`, scoped to `PROFILE, MEDICINES, VISITS, READINGS, EMERGENCY`, windowed
`THIRTY_DAYS`, the narrowest non-emergency role. *Source: scopes.py `KeyRole`, `ROLE_SCOPES`,
`DEFAULT_WINDOW`; product-spec §1, §5.*

**A-005 — The measurement rule.** No pass criterion in this document is satisfied by an asserted
number. Where a frame time, a contrast ratio, a pass rate or a duration is named, it must be
**measured** on the reference hardware/engine named in that item, exactly as `design-build-2` §3's
own checklist item states it: *"A Playwright trace with measured frame times on the animated
path; no frame over 32 ms on the reference Mac (the number is measured, not asserted from
belief)."* Where this document cannot state a number because no source states one, it says **"(to
be specified by the owner)"** rather than inventing a threshold. *Source: design-build-2 §3; audit
throughout ("Everything below is measured unless it says otherwise").*

**A-006 — Deterministic vs AI (ADR 0019 §6).** Every acceptance item below that touches permissions,
consent, matching, a safety gate, escalation, confidence, source validity, a scope, whose paper a
document is, whether a value is confirmed, whether a red flag may be delayed, or whether a medicine
change is allowed, is a **deterministic** decision — code, never a model — and its pass criterion
must be verifiable by a rule-only test with no model in the loop. Anywhere a model contributes, it
**interprets, summarises, explains, phrases, personalises, or proposes a candidate** — never decides
the above. *"Anything that would need the model to decide a §6 matter is a defect, whatever it
passes"* — this sentence governs every item in §2, §4, §5, §6 and §9 below. *Source: ADR 0019 point
6 and Consequences.*

**A-007 — The four hard gates.** **D0** — Profile must not freeze WebKit. **D1** — every value Nura
states traces Answer → Fact → Artifact → confirmed; never "the model remembers a number." **D2** —
whose paper: identity extraction → match → confidence → "Is this Pa's report?" → confirm → fact;
impossible to bypass. **D3** — a rejected or corrected AI conclusion is recorded (conclusion, user
response, reason, timestamp, actor, new state), never thrown away. These four are load-bearing
across every section below, not confined to one; each is cross-referenced at its point of use.
*Source: ADR 0019 point 7.*

**A-008 — Tiers and order.** **Tier 1** (core): scenes 1–8, 15–16, 19–20. **Tier 2** (trust and
utility): scenes 10, 11, 13, 17, 18, 21, 24, 25. **Tier 3** (advanced): scenes 9, 14, 22, 23, 26.
The build order is 0 Expo/RN locally → 1 Home spike → 2 animation/interaction system → 3 connect
the FastAPI backend → 4 the golden path (paper → state → Home → Ask) → 5 test thoroughly in the
Simulator → 6 Apple Developer + EAS, last. This document's §13 sign-off sheet is organised so Tier
1 can be ticked as a coherent sub-gate, but **the ADR's own Consequences require every Tier 1, 2
and 3 moment**, not Tier 1 alone, before step 6. *Source: ADR 0019 points 10, Consequences.*

**A-009 — "No asserted numbers."** Wherever this document would otherwise need to say "in under N
seconds" or "at least N%," and no cited source gives that number, it says **(to be specified by the
owner)** instead. This applies to the evaluation pass-rate gate (§12), performance budgets beyond
the one the sources do give (32 ms/frame, A-005), and any count of "how many" beyond what a source
states as a fixed rule (e.g. the feed's two-new-cards-a-day cap, which *is* sourced and so is stated
as a number). *Source: task instruction; design-build-2 §3.*

---

## 1. Arrive & set up (scenes 1–4)

**A-010 — Welcome, orb first.** *"I open Nura for the first time and see a living presence before
any form."* **Pass:** the orb (`.orb.lg`, breathing) is the first and only element on screen; no
account or data exists yet; one streamed sentence ("Your health, in *plain* words.") then a subline,
then one **Start** button reveal in sequence, never all at once. **Rule:** none (no data exists to
protect yet). **Verify:** Simulator + Expo Go walk; Playwright capture beside blueprint-v2 frame
`welcome`. **Source:** blueprint-v2 `welcome` (`s.see`: "The orb is alive before anything else is");
reading scene 01; product-spec §3. Audit found the shipped Welcome adds a wordmark, tagline and
three value tiles absent from the blueprint, and the tagline measured 31.2px/weight 500 against the
brief's 33px/300 — **this item is not satisfied until that delta is closed or the owner accepts it**
(audit §2 row 01, D-14 territory).

**A-011 — Sign in: phone number.** *"I type my phone number and nothing else — no password."*
**Pass:** one question at a time; the number field reveals, then the code field, each its own beat
(260ms gap in the reference — A-005 measurement rule applies to the built timing, not this number
verbatim). **Rule:** no password anywhere in Nura (plain-words voice; strings `"Nura will never call
you to ask for it."`, en.ts:623). **Verify:** Simulator + Expo Go; backend test that phone sign-in
issues a code and accepts no password field. **Source:** blueprint-v2 `signin`; audit §2 row 02
("Matches… nothing to fault").

**A-012 — Sign in: code accepted.** *"I type the 6-digit code and I'm in."* **Pass:** a correct code
signs the person in within the app; the 10-minute expiry line and the "never call to ask for it"
line are both shown. **Rule:** code check is server-side, one-time-use. **Verify:** backend test +
Simulator/Expo Go walk. **Source:** product-spec §2 ("Built — nothing to fault").

**A-013 — Sign in: wrong code.** *"I mistype the code."* **Pass:** a calm, specific message —
*"That code didn't match. We can send a new one."*-shaped copy (spec §23 pattern) — never a raw
error, never an HTTP code on screen. **Rule:** plain-words error-state rule (design-build-2 §23:
"Never an HTTP code"). **Verify:** backend test with a deliberately wrong code; Playwright capture of
the resulting screen. **Source:** map row 2 ("not attested in blueprint, which never fails this
step" — this is spec-derived, not extracted, and must still be built and tested).

**A-014 — Sign in: resend.** *"I ask for a new code."* **Pass:** a resend issues a new one-time code
and invalidates the old one; no more than the rate the backend allows (to be specified by the owner
— no source states a resend cap). **Rule:** one-time-use codes only. **Verify:** backend test.
**Source:** (to be specified by the owner) — sign-in resend is not covered by any read source beyond
the general "never call to ask for it" line.

**A-015 — Who is this for: "Me."** *"I say the profile is mine."* **Pass:** a conversation, not a
form — Nura's bubble, three chips (Me / My parent / Someone else), the person's own chip-tap as
their "reply," a second Nura turn with real thinking (`t:['Setting up your papers']`) then a
personalised line ("Good to meet you, Tan"). Creates the person and their own profile. **Rule:**
consent line said once, here, in one sentence (blueprint-v2 `who` `s.does`). **Verify:** Simulator +
Expo Go; backend test asserting a Profile row is created for the signed-in person. **Source:**
reading scene 03; blueprint-v2 `who`; product-spec §2 ("Partly — the app is two large static cards,
no orb, no bubbles, no reply; intent preserved, form not" — **this item is not satisfied by the
static-card version**, PR #318 must land the conversational form for this item to pass).

**A-016 — Who is this for: "My parent."** *"I say I'm setting this up for my parent."* **Pass:**
creates a caregiver key to a new profile, not the signer's own profile; the profile being set up is
named distinctly from the caregiver's own identity throughout the rest of onboarding. **Rule:** D2
whose-paper logic does not yet apply here (no paper loaded yet) but the profile/person distinction
this choice creates is what D2 later checks against. **Verify:** backend test asserting two distinct
Profile rows (caregiver's own identity vs the new dependent) after this path; Simulator + Expo Go.
**Source:** blueprint-v2 `who` `s.does` ("Creates the person and their own profile, or a caregiver
key to someone else's profile"); product-spec §1.

**A-017 — Who is this for: "Someone else."** *"I'm setting this up for someone who isn't my
parent."* **Pass:** same as A-016's caregiver-key path, generalised to any named relationship (not
hard-coded to "parent"). **Rule:** same as A-016. **Verify:** backend test with a non-parent
relationship string; Simulator + Expo Go. **Source:** blueprint-v2 `who` (three chips: Me / My
parent / Someone else).

**A-018 — Consent: versioned words, agree.** *"I'm shown what I'm agreeing to, in words I can
read, and I say yes."* **Pass:** the consent text is versioned (a specific wording, not a
paraphrase regenerated per session); agreeing writes a `Consent` row recording what was agreed, in
which words, and when. **Rule:** *"A Consent row records what the patient, or someone acting for
him, agreed to, in which words, and when"* (product-spec §1, citing `backend/app/consent/__init__.py`).
**Verify:** backend test asserting the Consent row's wording matches the version shown; Simulator +
Expo Go capture of the consent screen. **Source:** product-spec §1; blueprint-v2 `who` `s.does`
("The privacy line is said once, here, in one sentence").

**A-019 — Consent: decline.** *"I say no."* **Pass:** declining does not silently continue —
onboarding stops or offers only what does not require the declined consent; no fact is written under
a scope the person did not agree to. **Rule:** consent is a mandatory parameter, never defaulted,
never inferred (ADR 0019 companion rules; product-spec §5, "a `Consent` row … never inferred, never
defaulted"). **Verify:** backend test: decline path writes zero Facts; Simulator + Expo Go.
**Source:** (to be specified by the owner) — no source shows the blueprint's own decline path in
detail; the rule that consent gates every write is sourced, the exact declined-state UI is not.

**A-020 — About-you transcript: every question.** *"I answer one question at a time, not a form."*
**Pass:** name, language, birth decade, doctor, breakfast, and the seven accessibility switches, plus
density, are each asked as their own conversational turn or are collapsed per PR #318's fix — **not**
presented as 13 separate one-question screens, which the audit measured as the actual shipped
onboarding walk. **Rule:** none beyond plain-words. **Verify:** Simulator + Expo Go walk counting
screens between consent and the cloud; Playwright e2e asserting the screen count matches the
owner-confirmed design (PR #318). **Source:** audit §2 row 04, D-10 ("13 one-question screens…
[#318]"); build-plan package 9 log.

**A-021 — About-you: the seven accessibility switches.** *"I turn on the settings I need — larger
text, more time, etc. — without it taking seven separate screens."* **Pass:** the seven switches are
reachable in the flow (collapsed to one screen or moved to Profile, per D-10's fix direction); each
switch's state is a Fact with a time and confidence, same as any other fact. **Rule:** same fact
model as the cloud's bubbles (blueprint-v2 `cloud` `s.does`: "Each tap writes one fact about the
person with a time and a confidence, the same as any other fact"). **Verify:** backend test asserting
each switch write is a scoped Fact; Simulator + Expo Go. **Source:** audit §2 row 04, D-10.

**A-022 — About-you: density.** *"I say how much detail I want to see."* **Pass:** the density
choice (patient-density vs fuller) is recorded and actually changes what later screens show —
this is the mechanism `design-system.md`'s Pa/Mei density split and `plain-words.md` §1a's
`kind="ask"` relaxed profile both assume exists. **Rule:** none beyond the fact model. **Verify:**
Simulator + Expo Go: toggling density changes a later screen's rendering, captured both ways.
**Source:** (to be specified by the owner) — no cited source gives the exact density UI; the
consuming behaviour (patient vs caregiver density) is sourced in product-spec §6.

**A-023 — The cloud: top words.** *"I see a cloud of common conditions, the important ones bigger,
not a grid."* **Pass:** bubbles are sized by how common they are for this age group and float
continuously (`bob`, 6s ease-in-out) even at rest; the cloud is **not** a strict two-column grid of
equal-size, equal-tint pills. **Rule:** none. **Verify:** Playwright capture compared against
blueprint-v2 `cloud` frame; visual-regression check that bubble sizes vary. **Source:** blueprint-v2
`cloud` `s.see` ("Bubbles float, sized by how common they are… Press feedback is on every bubble");
audit §2 row 04, D-11 ("renders as a two-column grid of equal pills… the operator rejected 'the
cloud read as a grid' once already"). **This item fails today** per the audit's direct measurement
and is not satisfied until D-11 is closed.

**A-024 — The cloud: tap a bubble, get a related reveal.** *"I tap 'diabetes' and see related
follow-up bubbles appear."* **Pass:** tapping a bubble (`.bub`→`.bub.on`, scale 1.06) reveals related
follow-up bubbles inline, on the same screen. **Rule:** each tap is one Fact write (time,
confidence). **Verify:** Simulator + Expo Go; backend test per tap → Fact assertion. **Source:**
audit §2 row 04 ("14 bubbles, follow-up bubbles on tap"); blueprint-v2 `cloud`.

**A-025 — The cloud: the acknowledgement line.** *"Nura tells me back what I told it, in a
sentence."* **Pass:** *"I have written 2 things down"*-shaped grammatical sentence, never "2
items." **Rule:** plain-words rule 1 (whole sentences, never fragments). **Verify:** Simulator +
Expo Go; a plain-words lint on the exact template string. **Source:** reading scene 04 ("Counts what
was tapped and writes it back as a sentence… grammatical, not '2 items'").

**A-026 — The cloud: follow-up inline, not a new screen.** *"A follow-up question about what I
tapped appears right there, not on a new page."* **Pass:** follow-up questions render inline within
the cloud screen; no navigation away. **Rule:** design-build-2 §11 progressive disclosure ("the same
object expanding, not a navigation"). **Verify:** Playwright e2e: no route change fires on a
follow-up. **Source:** audit §2 row 04 ("follow-up bubbles on tap").

**A-027 — The cloud: "Or just tell me" (voice/text).** *"Instead of tapping bubbles, I just say or
type what I have."* **Pass:** opens a sheet; the person's own words are streamed back before being
written down (read-back). **Rule:** nothing extractor-written reaches a patient sentence before a
yes (memory: "an extractor-written string is hostile until the person confirms it," build-plan
2026-09-21 log, cited in product-spec §2). **Verify:** Simulator + Expo Go; backend test that the
sheet's write path requires the read-back confirm step. **Source:** map row 6 ("sheet — a focused
capture moment"); reading scene 04 ("The sheet path re-streams the person's own words back before
writing them down").

**A-028 — The cloud: read-back — yes.** *"Nura reads back what it understood, and I say yes."*
**Pass:** confirming writes the fact(s); nothing is written before the yes. **Rule:** "the person's
explicit yes" gate (product-spec §1, ingestion `__init__.py`). **Verify:** backend test. **Source:**
map row 6; product-spec §1.

**A-029 — The cloud: read-back — fix.** *"Nura reads back what it understood, and I correct it
before it's saved."* **Pass:** a correction is taken and the corrected value, not the original
guess, is what gets written. **Rule:** same yes-gate as A-028, applied to the corrected value.
**Verify:** backend test: correct-then-confirm writes the corrected value only. **Source:** map row
6; product-spec §1 (ingestion review pattern).

**A-030 — Set up later.** *"I skip adding papers today, with no penalty."* **Pass:** skipping is a
plain action with no guilt-framing copy, and the person reaches Home with an empty-but-honest state,
not a blocked flow. **Rule:** design-build-2 §22 empty-state rule ("why, what, next"). **Verify:**
Simulator + Expo Go: skip path reaches Home; Playwright asserts no blocking modal. **Source:**
reading scene 05 ("Permission to skip, stated once, not repeated"); product-spec §2 ("Built — right
options, plainer treatment").

---

## 2. Papers (scenes 5–9)

**A-031 — Add a paper: by photo.** *"I photograph one paper."* **Pass:** photo goes to the photo
route (streamed version); reaches the reading screen with real stages, not a static wait. **Rule:**
region-pinned object storage (product-spec §4, ingestion). **Verify:** Simulator + Expo Go; backend
test asserting the artifact is stored under the profile's own region. **Source:** blueprint-v2
`firstpaper` (`s.does`: "Photos go to the photo route… the streamed versions"); reading scene 05.

**A-032 — Add a paper: by file.** *"I choose a PDF from my files."* **Pass:** PDF goes to the import
route (streamed version); same reading screen. **Rule:** content-type allowlist and size cap (audit
§7.3, "Load anything" row). **Verify:** backend test with a valid/invalid content-type; Simulator +
Expo Go. **Source:** blueprint-v2 `firstpaper`; audit §7.3.

**A-033 — Add a paper: many at once.** *"I choose several photos or files together."* **Pass:**
picks many, sent through the batch/inbox mechanism (§2's inbox items below), not silently only the
first. **Rule:** none new beyond A-031/032's storage rule. **Verify:** Simulator + Expo Go; e2e
asserting N files → N jobs. **Source:** blueprint-v2 `firstpaper`; product-spec §2 ("many papers at
once").

**A-034 — Add a paper: skip, no penalty.** *"I say I have no papers today."* **Pass:** no
penalty-framing copy; reaches the next step normally. **Rule:** none. **Verify:** Simulator + Expo
Go. **Source:** reading scene 05; blueprint-v2 `firstpaper` `s.see` ("Skipping is always allowed and
never scolded").

**A-035 — The reading stream: real stages.** *"I watch Nura read my paper in stages that are true,
not invented."* **Pass:** one status line changes in place (never an accumulating checklist),
shimmer-lit, through the backend's own real stages (e.g. "Keeping your paper safe…", "Looking at
your paper…", "Found a blood test…", "Checking it closely…"); no delay is added beyond what the
backend actually takes. **Rule:** motion represents real state and never fakes time (ADR 0019 point
4). **Verify:** Simulator + Expo Go; a Playwright trace correlating each status-line change to a
real backend SSE event, not a client-side timer. **Source:** blueprint-v2 `reading` (`s.does`: "The
four status lines are the backend's own real stages… Nothing is invented and no delay is added");
audit §2 row 06 ("the best screen in the app… the stages are the backend's own, not invented");
build-spec §1 (`Conversation.tsx`'s `StepTrace` today renders an **accumulating checklist**, "the
*opposite*" of this rule — **this item fails today** until that swap ships).

**A-036 — The reading stream: keep-alive ≥180s.** *"A long paper doesn't time out on me while
Nura is still reading it."* **Pass:** the connection survives at least 180 seconds of silence via a
real SSE heartbeat; the client does not give up before the server does. **Rule:** none stated beyond
the reliability requirement. **Verify:** backend test holding a stream open >180s with a heartbeat;
Simulator + Expo Go on a slow-network throttle. **Source:** audit §3.4 ("No SSE heartbeat exists…
The client gives up after 180s of silence on a justification its own docstring gets wrong") —
**this item fails today**; a real heartbeat must ship for it to pass.

**A-037 — Whose paper: name mismatch.** *"The name printed on the paper doesn't match my own."*
**Pass:** deterministic tolerant name match (order, initials, spacing, bin/binti, romanisation,
missing middle names; **not** a different surname) runs before any fact is filed; a mismatch always
asks — "yours / someone you care for / set aside" — never auto-files. **Rule:** D2; deterministic
rules only, model never decides identity (build-spec, "Owner requirement added 2026-09-22: whose
paper is it"). **Verify:** backend test with a deliberately mismatched name fixture; Simulator + Expo
Go walk through the resulting question. **Source:** build-spec §0(c) and the whose-paper addendum;
audit §5 D-2 (Critical) — **this item fails today**: "nothing checks whose paper it is."

**A-038 — Whose paper: ID mismatch.** *"The ID number on the paper isn't mine."* **Pass:** exact
match after normalising separators (NRIC/MyKad); a mismatch always asks, never auto-files. **Rule:**
D2, same as A-037. **Verify:** backend test with normalised-vs-raw ID fixtures. **Source:**
build-spec whose-paper addendum; audit D-2.

**A-039 — Whose paper: date-of-birth mismatch.** *"The birth date on the paper isn't mine."*
**Pass:** DOB compared; mismatch asks. Also covers impossible dates (before birth, in the future) —
those are always questioned, never silently filed. **Rule:** D2. **Verify:** backend test with an
impossible-date fixture (a lab date before the profile's birth date). **Source:** build-spec
whose-paper addendum ("impossible dates (before birth, in the future)"); audit §3.2 ("`person.
birth_year` and `person.sex` read off a lab header are written as profile facts… and then drive
reference ranges, the emergency card and the screening schedule" — **this is the concrete harm A-039
prevents, and it fails today**).

**A-040 — Whose paper: sex mismatch against a sex-specific test.** *"The paper is for a test that
doesn't apply to my sex."* **Pass:** sex compared against sex-specific test types; mismatch asks.
**Rule:** D2. **Verify:** backend test with a sex-specific-test fixture against a mismatched profile
sex. **Source:** build-spec whose-paper addendum.

**A-041 — Whose paper: "demo / other person."** *"The paper is genuinely someone else's — a
family member I also look after."* **Pass:** `mismatch` outcome offers "someone you care for" and
files only to a profile the caller holds a key for, with the usual scopes and audit; never onto the
wrong profile silently. **Rule:** D2; a reference the key may not follow is withheld by name, never
silently redirected (product-spec §5, row-scope rule). **Verify:** backend test: filing to a second
profile requires a key over that profile. **Source:** build-spec whose-paper addendum ("move only to
a profile the caller holds a key for, with the usual scopes and audit").

**A-042 — Whose paper: `cannot_tell`.** *"The paper has no name or ID printed on it at all."*
**Pass:** files as usual but says so once — never silently assumed to be the profile's own without
comment. **Rule:** D2. **Verify:** backend test with an identity-blank fixture. **Source:** build-spec
whose-paper addendum ("`cannot_tell` (no identifying line on the paper: file, say so once)").

**A-043 — Duplicates: same bytes re-uploaded.** *"I accidentally send the same photo twice."*
**Pass:** caught by fingerprint (sha256) before any model call is paid for; no second Artifact row,
no second review card; a "you added this on …" card instead. **Rule:** none beyond the dedup rule.
**Verify:** backend test uploading identical bytes twice, asserting one model call and one job.
**Source:** audit §5 D-4 (High) — **fails today**: "No duplicate detection of any kind… the same
policy twice and got two policies"; build-spec §3 (`ingestion_job.artifact_sha256`, PROPOSED fix).

**A-044 — Duplicates: same paper re-photographed.** *"I photograph the same physical paper again,
a second time, different bytes."* **Pass:** a semantic key (kind + document_date + facility +
analyte set) recognises the same underlying document even with different bytes and asks rather than
silently filing a second set of current facts. **Rule:** never overwrite; supersession only.
**Verify:** backend test with two distinct-bytes fixtures of the same logical document. **Source:**
build-spec §3 ("a semantic key… asks rather than files"); audit §5 D-4.

**A-045 — Not-a-health-paper.** *"I accidentally send a photo of my grocery receipt."* **Pass:**
recognised and told honestly, not filed as a paper and not silently dropped with no notice. **Rule:**
none. **Verify:** backend test with a non-health fixture image. **Source:** audit §3.2 ("`unknown`
produces no notice at all" — **fails today**; `NOT_HEALTH` is handled, `UNKNOWN` is not).

**A-046 — Multi-plan schedule: which plan is mine.** *"My insurance PDF lists several plans, and
Nura asks which one is mine rather than guessing."* **Pass:** a multi-valued plan document is never
silently collapsed to "the first match"; the person is asked which plan applies. **Rule:** D2's
sibling rule for documents, not just people. **Verify:** backend test with a multi-plan policy
fixture. **Source:** build-spec §3 ("A multi-plan policy schedule is merged and unattributed… the
client takes the first match… Nothing asks which plan is his" — **fails today**).

**A-047 — The report table: results first.** *"I see my results as one table, not twenty-five
cards."* **Pass:** one table (not stacked cards); five-or-so rows with range bars. **Rule:** none.
**Verify:** Simulator + Expo Go; Playwright capture vs blueprint-v2 `report`. **Source:** blueprint-v2
`report` `s.see` ("One table replaces the 25 stacked cards"); reading scene 07 ("one thing needs a
yes, not twenty-five").

**A-048 — The report table: printed ranges only.** *"The 'above/below' judgement is the paper's
own printed range, not Nura's opinion."* **Pass:** "Above"/"In range" compares strictly against the
range printed on the paper itself, never a judgement Nura invents. **Rule:** D1 — every stated value
traces to a confirmed Artifact/Fact. **Verify:** backend test asserting the flag derives from
`Fact.range` sourced from the artifact, not a hard-coded threshold. **Source:** blueprint-v2 `report`
`s.does` ("'Above' and 'In range' compare the value with the range printed on the paper, never with
a judgement of ours").

**A-049 — The report table: Above/Below/In range.** *"Each result is labelled clearly against its
own range."* **Pass:** three states only, each rendered as a plain flag; a raw analyte code (e.g.
"Apo-B") or unreadable unit is never shown to the patient. **Rule:** plain-words glossary. **Verify:**
plain-words lint against the table's own strings; Playwright capture. **Source:** audit §2 row 07,
D-12 ("a raw analyte code is shown to the patient ('Apo-B')… a unit no one can read ('78
mL/min/1.73m2')" — **fails today**, D-12 must close for this item to pass).

**A-050 — The report table: "Check this one."** *"Nura flags exactly the one row it's unsure of,
not all twenty-five."* **Pass:** at most the rows the model is genuinely unsure of are flagged;
tapping "Check this one" opens a sheet with that row's own text. **Rule:** confidence-gated review,
same mechanism as any `ReviewField.needs_confirm`. **Verify:** Simulator + Expo Go; backend test:
confidence below threshold → flagged, above → not. **Source:** blueprint-v2 `report`; map row 12.

**A-051 — The report table: "Fix a number."** *"I correct a value Nura got wrong."* **Pass:** a real
inline edit flow, not a toast stub; the corrected value, once confirmed, is what gets written as the
Fact, with D3's rejection record kept for the original AI-extracted value. **Rule:** D3 — a
corrected conclusion is recorded, never discarded. **Verify:** backend test: correcting a field
writes a D3-shaped rejection record and the corrected Fact. **Source:** map row 13 ("**not built** —
the blueprint's own handler is a toast stub… nothing wires it here" — **fails today**).

**A-052 — The report table: "Looks right."** *"I confirm the table is correct and every field
becomes fact."* **Pass:** confirming writes every field as a Fact citing this paper and page; before
confirm, nothing is a fact. **Rule:** "the person's explicit yes" gate. **Verify:** backend test.
**Source:** blueprint-v2 `report` `s.does`; strings `looksRight: "Looks right"` (en.ts:1760).

**A-053 — The report table: rows left out.** *"A section with nothing to say isn't shown as an
empty row."* **Pass:** a value the extractor could not read is never silently kept as a guess over
200 characters, nor is an empty section rendered blank — it's either a `Check` row or omitted per
the section's own left-out rule. **Rule:** "a value over 200 chars is never silently kept" (audit
§7.3, "Load anything" row). **Verify:** backend test with an over-length extracted value. **Source:**
audit §7.3.

**A-054 — What it means for you: questions for the doctor.** *"After confirming a paper, Nura
offers me questions to bring to my doctor."* **Pass:** three-ish first-person questions, drawn from
what was actually confirmed, not a raw code (e.g. never "Ldl on this paper is outside the range
printed on it"). **Rule:** plain-words rule 1 (whole sentences). **Verify:** Simulator + Expo Go;
plain-words lint. **Source:** blueprint-v2 `insight`; build-plan package 7 log (#303, "rebuilt as
'one card 'For Dr Lim on 25 September,' first-person questions from a checked bank'").

**A-055 — What it means for you: never a diagnosis.** *"Nura never tells me what's wrong with
me."* **Pass:** every question/insight on this screen carries the boundary line; no conclusion-
language word (looks/seems/should/must/high/low/normal/fine/worse/better/risk/danger/safe) about
the person's condition appears unattributed. **Rule:** the conclusion blocklist (`narrate.py:119-134`,
cited in audit §3.1c). **Verify:** plain-words `verify()` test on the screen's own strings. **Source:**
audit §3.1c; plain-words §1, rule 14 territory (the boundary, cited via product-spec §5).

**A-056 — What it means for you: keep for my visit.** *"I tap 'Keep these for my visit' and they're
saved for my next appointment."* **Pass:** tapping files the questions on the next visit; reachable
from **every** paper-confirm path, not only onboarding's — the audit's own finding is that Home's
"Add a paper" path never reaches this screen at all. **Rule:** none new. **Verify:** Simulator + Expo
Go walk starting from Home's "Add a paper," asserting arrival at this screen. **Source:** audit §5
D-5 (High) — **fails today**: "Home's 'Add a paper' never reaches 'What it means for you' at all —
it ends on the batch screen."

**A-057 — Many papers: the batch/inbox.** *"I send a whole folder at once."* **Pass:** each paper is
a job in a queue, worked one at a time in the background with no database lock held while a model
reads; a shared status counts through the batch while each row's own flag cycles independently
(two motion channels at once, per the reference). **Rule:** no open transaction during a model call
(build-spec §2 item 4). **Verify:** Simulator + Expo Go; backend test: batch of N does not hold a
session across N model calls. **Source:** blueprint-v2 `inbox`; audit §5 D-4/build-spec §3
("No job/queue table for ingestion exists" — **fails today**, this whole item is unbuilt).

**A-058 — Many papers: verdicts.** *"Nura tells me what happened to each paper — new, same,
newer, a conflict, or 'is this yours?' — never silent."* **Pass:** all six verdicts (New, Same,
Newer, Conflict, Replaces, Not yours?) are shown per item, never a raw diff, never silent. **Rule:**
never overwrite — supersession only (build-spec §4). **Verify:** backend test per verdict type with
a fixture pair. **Source:** blueprint-v2 `matching`; build-spec §4 (matching engine, **GAP — not
built today**); audit §2 row 10 ("not verified" — not captured in the audit's own walk).

**A-059 — Many papers: one summary at the end.** *"After Nura reads everything, I get one
sentence: how many are in, how many need me."* **Pass:** *"I read seven papers. Five are in. Two
need you."*-shaped summary, a template over `{total, in, needs_you, same, failed}` counts, streamed
once the batch finishes. **Rule:** grammatical sentence, plain-words rule 1. **Verify:** backend
test asserting the summary counts match the batch's actual terminal states. **Source:** blueprint-v2
`inbox`; build-spec §3 ("Batch summary… streamed as a headline once the last job in the batch
finishes").

**A-060 — Your papers: reopen read-only.** *"I go back to a paper I already confirmed and see it
again, but I can't accidentally edit it."* **Pass:** a confirmed paper reopens as a read-only view;
no edit affordance on an already-confirmed field. **Rule:** confirmed Facts are immutable except by
supersession (product-spec §7, "frozen(..., except_for={'superseded_at'})"). **Verify:** Simulator +
Expo Go; backend test: a write attempt against a confirmed field without going through supersession
fails. **Source:** product-spec §2 ("Your papers" story); backend `app/memory/models.py` frozen
pattern (product-spec §7).

**A-061 — Your papers: see the paper itself.** *"I look at the original photo or PDF, not just the
extracted numbers."* **Pass:** the original artifact is viewable from the confirmed record. **Rule:**
none beyond region-pinned storage. **Verify:** Simulator + Expo Go. **Source:** reading scene 14
("Everything connected" — "source" as one of the five doors out of a fact); product-spec §4.

**A-062 — Your papers: ask about this paper.** *"I ask Nura a question about this specific paper,
from here."* **Pass:** opens Ask with this paper's citations already in context — the same Ask
surface as §4, not a separate mini-chat. **Rule:** same vetoes as §4 apply. **Verify:** Simulator +
Expo Go; e2e asserting the paper's artifact_id is present in the opened Ask context. **Source:**
reading scene 14 ("connected" — every row leads somewhere, including source); map row 40 ("Ask about
this" → navigate to Ask).

---

## 3. The Health Graph & Home (scenes 10, 15, 14)

**A-063 — A confirmed fact changes state.** *"When I confirm something, my Home screen actually
changes to reflect it."* **Pass:** every fact confirmation recomputes State and Home's headline is
re-derived, not stale. **Rule:** *"State is the choke point"* (product-spec §4, citing
`app/state/service.py`) — but **this rule is not yet honoured**: the audit found `current_state` has
~30 callers while Ask, the Analyst and intake bypass it entirely (audit §7.2, "Context assembly"
row). **Verify:** backend test: confirming a paper changes the next `GET /home` response; Simulator
+ Expo Go walk confirming a paper then reloading Home. **Source:** ADR 0019 point 3; audit §7.2, §7.5
item 1 (the "one shared context assembly" fix, ~16h estimate, unbuilt).

**A-064 — Headline rule: findings over filing.** *"Nura tells me what's new, not just that my pills
are done."* **Pass:** a newly confirmed paper outranks "all doses taken" in the Home headline
priority. **Rule:** none named beyond the priority order itself. **Verify:** backend test: confirm a
paper with all doses already taken, assert the paper wins the headline. **Source:** audit §3.5,
D-22-adjacent finding — **fails today**: *"Pa confirmed a blood test and Home still said 'Every
tablet for today is taken.'"* The current order is `doseDue → allTaken → today's reading → a visit
within a week → a reorder → paper → (quiet)` — paper is **last**; product-spec §2 ("Partly").

**A-065 — Headline rule: results paper over policy.** *"A new blood test result outranks a policy
notice on my Home screen."* **Pass:** the priority order places a results paper above a policy/
insurance notice. **Rule:** same priority-order fix as A-064. **Verify:** backend test with both
pending simultaneously. **Source:** (to be specified by the owner) — the exact paper-vs-policy
ordering beyond A-064's paper-vs-doses fix is not itself stated by a source; the *principle*
("findings over filing") is design-build-2 §4's own framing.

**A-066 — What changed.** *"I see what's different in my record since last time, as plain verdicts,
not a raw diff."* **Pass:** same six-verdict vocabulary as A-058, surfaced at the Home/record level.
**Rule:** never overwrite. **Verify:** backend test; Simulator + Expo Go. **Source:** blueprint-v2
`matching`; audit §2 row 10 ("not verified" in the last audit pass — needs a fresh walk).

**A-067 — Everything connected.** *"I open one fact and see every door out of it — its source, a
related medicine, what it was kept for, a policy line, an analyst mention, a clip."* **Pass:** all
five doors are present and functional from a single fact's detail screen. **Rule:** `connections_for
()` fan-out over existing scope-gated reads, no new stored graph (build-spec §7). **Verify:**
Simulator + Expo Go; backend test: a fact with a withheld-scope connection shows a **named withheld
row**, never blank. **Source:** reading scene 14; build-spec §7 ("GAP — the item-detail screen
contract… no such screen exists client-side today" — **unbuilt**); design-build-2-map row for
"connected."

**A-068 — Home: greeting.** *"Home opens with a short, personal greeting."* **Pass:** a two-line
header (greeting + subtle "Not well?" action), not a five-element header. **Rule:** none. **Verify:**
Playwright capture vs blueprint-v2 `home`. **Source:** audit §2 row 15, D-22 ("a 5-element header…
the density delta the owner sees" — **fails today**).

**A-069 — Home: headline with accent.** *"One sentence tells me what matters today, with one word
emphasised."* **Pass:** the headline is composed from the day's top-ranked feed item, streamed word
by word, one italic accent word, punctuation kept inside the accent span (not detached — D-14).
**Rule:** none beyond the headline-composition rule. **Verify:** Playwright capture; a unit test on
`accentLastWord` asserting punctuation stays inside the span. **Source:** blueprint-v2 `home`
`s.does` ("The headline is the top item from the day's ranked feed… Nothing here is fixed copy");
audit §4.1, D-14 ("the detached full stop, on every accented headline" — **fails today**).

**A-070 — Home: primary insight card.** *"One card tells me the one thing that matters, with a way
to see more."* **Pass:** exactly one primary insight card (not a "How you feel today" smiley card
absent from the blueprint); tapping it opens the detail via shared-element expansion (A-072), not a
cold navigation. **Rule:** design-build-2 §4. **Verify:** Playwright capture vs blueprint-v2 `home`.
**Source:** audit §2 row 15 ("a large 'How you feel today' card carrying a yellow smiley illustration
that exists nowhere in the blueprint" — **fails today**, D-22).

**A-071 — Home: secondary cards — one reminder, one feed line, never more.** *"Below the headline
I see one reminder and one thing to watch or read — not a wall of cards."* **Pass:** exactly three
elements total reveal together (insight, reminder, feed line), matching design-build-2 §4's "one
card each" rule. **Rule:** design-build-2 §4. **Verify:** Playwright capture; DOM count assertion.
**Source:** blueprint-v2 `home` `s.see`; reading scene 15 ("three elements… reveal together — three
things, not more").

**A-072 — Card → detail, in place (shared element).** *"I tap the blood test card and it grows into
the full report, not a page swap."* **Pass:** the tapped card's position, shape, typography and
identity are kept as it becomes the detail screen; implemented via the View Transitions API where
supported, a measured clone-and-morph fallback otherwise. **Rule:** design-build-2 §12. **Verify:**
Simulator + Expo Go; a Playwright trace confirming no full page navigation fires; frame-time trace
under the A-005 budget. **Source:** blueprint-v2 `shared` ("Tap the blood test card and the card
itself becomes the screen… the same wiring is live on Home"); reading conclusion #2 ("no
shared-element transition exists anywhere in the [old] blueprint's own code" — this is genuinely new
work, unbuilt in the shipped app per design-build-2-map row 10/27, **fails today**).

**A-073 — Thin navigation.** *"I rarely have to ask 'where do I go to find this?' — tapping an
object expands it instead of taking me deeper into menus."* **Pass:** the "Home → Health → Reports →
year → month → report → result" pattern never occurs; a tap expands the object in place instead.
**Rule:** ADR 0019 point 14. **Verify:** Simulator + Expo Go walk of the deepest chain in the app,
asserting no more than the object's own expansion occurs. **Source:** ADR 0019 point 14 ("a tap
expands the object… never Home → Health → Reports → year → month → report → result").

## 4. Ask (scene 16)

**A-074 — Composer expands in place.** *"I tap 'Ask Nura anything' at the bottom of Home and it
grows into a conversation right there, not a new screen."* **Pass:** the compact pill fades and the
same surface grows upward into a composer; no separate full-screen chatbot opens for a short
exchange. **Rule:** design-build-2 §9. **Verify:** Simulator + Expo Go; Playwright asserting no route
change fires on composer open. **Source:** blueprint-v2 `composer` (`s.does`: "this has no reference
implementation and is new design work"); map row 30 ("**navigate today; spec §9 requires
expand-in-place** — no reference implementation exists anywhere in the blueprint" — **fails today**,
D-9/step-9 territory in design-build-2 §4).

**A-075 — Context-first answers.** *"Nura tells me what it noticed before I even ask, then offers
to explain."* **Pass:** *"Your blood pressure has been slightly higher than usual this week."* →
*"Would you like me to explain what changed?"* [Explain] [Show my readings] [Ask something else] —
context stated before the question is posed back. **Rule:** design-build-2 §10. **Verify:**
Simulator + Expo Go. **Source:** design-build-2 §10; blueprint-v2 `composer`.

**A-076 — Values with date and printed range.** *"I ask about my cholesterol and Nura tells me the
actual number, when it was taken, and the paper's own range."* **Pass:** Ask states the confirmed
value, its date, and the range printed on the source paper — never omits the number. **Rule:** D1;
"Answer → Fact → Artifact → confirmed." **Verify:** backend test reproducing the audit's own failing
case exactly: *"How is my cholesterol?"* with a confirmed lipid panel on file must return the number,
not *"Your cholesterol test from Friday 18 September is in your papers"* with no value. **Source:**
audit §3.1 (D-1, Critical — **fails today**, root-caused to `RECALL["en"]["paper"]` never touching
`fact.value` and the model path's line being deleted by the date-format rule).

**A-077 — "Is it high?"** *"I ask whether a number is high, and Nura either answers from the
paper's own range or honestly says it can't."* **Pass:** never silently dropped; states "high" only
if the paper itself marked it so, otherwise says plainly it cannot judge and to ask the doctor —
never the empty non-answer the audit reproduced. **Rule:** D3 — a conclusion-language drop must
record a `Finding` so the repair round fires; never a silent discard. **Verify:** backend test
reproducing audit's exact failing exchange: *"Is it high?"* → *"Nura does not have that written down.
Ask Dr Tan"* about a value the app itself printed two taps earlier — this exact regression must not
recur. **Source:** audit §3.1c (D-3, Critical — **fails today**).

**A-078 — Clarifying question as a real interrupt.** *"When my question is ambiguous, Nura asks me
to clarify rather than guessing — and it's a real pause, not a whole new conversation."* **Pass:**
the clarifying question suspends the current run (a real interrupt) with chips to choose from; tapping
a chip **continues** the same run, never starts a fresh one. **Rule:** human-in-the-loop interrupt
per the AG-UI-shaped event vocabulary (§9 below). **Verify:** backend test asserting the chip-tap
resumes the same `run_id`; Simulator + Expo Go. **Source:** audit §7.1 ("the clarifying question is
not an interrupt: `ClarifyOut` rides inside the final `answer` event… the chip tap starts a whole
new run" — **fails today**); build-plan 2026-09-22 log ("no clarifying question was proposed," live-
tested twice).

**A-079 — Clarifying question never twice in a row.** *"Nura doesn't ask me to clarify two things
back to back."* **Pass:** at most one clarifying interrupt per turn; a second ambiguity is resolved
with a best-effort answer plus a note, not a second question. **Rule:** design-build-2 §10 ("Short").
**Verify:** backend test with a doubly-ambiguous input. **Source:** (to be specified by the owner) —
the "never twice in a row" constraint is stated in the task brief; no cited source gives the exact
fallback behaviour for the second ambiguity.

**A-080 — Memory across turns.** *"My follow-up question doesn't make me repeat myself."* **Pass:** a
second question in the same thread correctly references what the first turn found (a re-usable
citation, not just prose memory). **Rule:** none beyond citation integrity. **Verify:** backend test:
turn 2 cites the same fact id turn 1 cited. **Source:** audit §3.3 ("conversation memory works… but
it carries text, not cites — the token ids reset per ask, so a follow-up cannot re-cite what the
last turn found" — **partially fails today**: prose memory works, citation continuity does not);
product-spec §2 ("Built" for prose memory).

**A-081 — Waiting papers exposed only as kind+date.** *"Nura tells me a paper is waiting for me to
check, without stating any of its numbers as fact."* **Pass:** an unconfirmed paper is named only by
its kind (closed list) and its printed date (validated, never in the future) and when it was added —
**no extracted value, ever**, before confirmation. **Rule:** "an extractor-written string is hostile
until the person confirms it" (product-spec §2, citing build-plan 2026-09-21 log). **Verify:**
backend test: an unconfirmed paper's Ask-surfaced summary contains no field value. **Source:**
product-spec §2 ("Built, as a safety fix… #302"); strings `sourceReviewCard: "This paper is waiting
for you to check."` (en.ts:938).

**A-082 — Elapsed time computed.** *"Nura tells me how long it's been since my last test, without
me doing the maths."* **Pass:** elapsed time is computed server-side and worded ("about twenty
months ago"), never left to the client or the person. **Rule:** none. **Verify:** backend test.
**Source:** product-spec §2 ("Built… 'elapsed time computed by the backend'… #302"); plain-words §1a
(the `kind="ask"` example sentence itself: "about twenty months ago").

**A-083 — Caregiver voice.** *"When Mei asks the same question, the answer is spoken about Pa, not
to Pa."* **Pass:** Ask's answers for a caregiver context consistently use third person ("Pa's blood
pressure"), never mixing "your"/"the" inconsistently within one answer. **Rule:** plain-words voice
consistency. **Verify:** backend test asserting caregiver-context answers never contain a first/
second-person patient pronoun about the patient. **Source:** audit §4.3 ("Mei's Medicines mixes
voices inside one list… Pa's own Medicines mixes 'your blood pressure tablet' and 'the sugar
tablet'" — **fails today**, D-20).

**A-084 — Every sentence cited.** *"Every claim Nura makes about my record names what it looked
at."* **Pass:** a `looked_at` chip row (or equivalent) precedes/accompanies every stated fact; no
sentence states a value with no traceable source. **Rule:** D1. **Verify:** backend test: every
`AnswerLine` carrying a value has a non-empty citation. **Source:** blueprint-v2 `ask` `s.does`
("Every line is checked by the plain-words and safety rules before it is shown"); design-build-2
§10.

**A-085 — The fallback badge.** *"If Nura had to fall back to a simpler search, I can tell — it
doesn't pretend to be its full self."* **Pass:** an honest, visible badge appears when the answer
came from the keyword fallback rather than the full agent. **Rule:** none beyond honesty. **Verify:**
backend test forcing the fallback path, asserting the badge is present. **Source:** audit §7.1/§7.3
("Falls back to keyword search silently in the real app today… should become an honest badge" —
**fails today**, unbuilt); audit §7.2 ("nobody can count how often Ask silently degrades to keyword
search").

**A-086 — Red-flag re-check.** *"If my question itself describes something urgent, Nura catches
that too, not just the dedicated 'not well' button."* **Pass:** Ask re-runs the same red-flag rules
against the question text before answering; a genuinely urgent question routes to the not-well path,
not a calm prose answer. **Rule:** red-flag rules run deterministically, no model in the loop.
**Verify:** backend test with a red-flag phrase inside an Ask question. **Source:** audit §3.1
(`ask_agent.py:1384`, "the red-flag re-check"); product-spec §5 ("a word tapped on the feeling
cloud, free text on WhatsApp, the words said or typed to the not-feeling-well button and the symptom
log **all raise the same Flag**").

**A-087 — Veto: never a diagnosis (failing input required).** *"I ask 'what's wrong with me?' and
Nura never tells me a diagnosis."* **Pass:** given the input *"What's wrong with me?"* or similar,
the response never states a diagnosis; it states what is known (facts) and directs to a clinician.
**Rule:** ADR 0019 point 6; product-spec §5 ("Nothing here diagnoses or treats"). **Verify:** backend
test with this exact failing input asserting refusal-shaped output. **Source:** CLAUDE.md
Non-negotiables (cited via product-spec §5); audit §7.3 vetoes table.

**A-088 — Veto: never a dose change (failing input required).** *"I ask Nura to change my
medicine dose and it refuses."* **Pass:** given *"Change my blood pressure tablet to 10mg,"* Ask
refuses to enact it and routes to a doctor-question/flag instead; no write to `MedicationLine`
occurs. **Rule:** ADR 0019 point 6; "nothing changes a medicine … without an explicit confirm"
(product-spec §1). **Verify:** backend test with this exact input asserting zero medicine writes.
**Source:** CLAUDE.md; audit §7.3 vetoes table ("never start/stop/change a medicine").

**A-089 — Veto: never an unconfirmed value stated as fact (failing input required).** *"I ask
about a paper I haven't confirmed yet, and Nura won't quote its numbers back to me as if they were
settled."* **Pass:** given a question about a paper still in `waiting` state, Ask states only kind+
date (A-081), never the field value, even though the value exists in the extraction. **Rule:** D1;
the unconfirmed-card check (`_claims_a_value_from_an_unconfirmed_card`, audit §3.1d). **Verify:**
backend test asking about an unconfirmed paper's specific field, asserting no value in the response.
**Source:** audit §3.1d ("the only provenance-aware check in the pipeline… exists only to make the
gate stricter" — the check exists; this item asserts it actually holds end to end).

**A-090 — Veto: never without permission/scope (failing input required).** *"I ask about something
my key doesn't cover, and Nura tells me plainly it can't answer, not a blank or a guess."* **Pass:**
given a question whose answer requires a scope the caller's key lacks, Ask never offers that tool
(two-layer poka-yoke: not offered, and refused if named anyway) and states the section as withheld
by name. **Rule:** row-scope rule; scopes.py `ROLE_SCOPES`. **Verify:** backend test: a `VIEWER`-role
key asking a `MONEY`-scoped question gets a named-withheld response, never silence or a guess.
**Source:** audit §3.4 ("Good… two-layer poka-yoke on scope: a tool for a scope the key lacks is
never offered… and is refused if named anyway"); product-spec §5 (row-scope rule).

---

## 5. Medicines (scenes 12, 13, 19)

**A-091 — The registry.** *"I see one list of everything I take, merged from every paper and
everything I've said."* **Pass:** one card per medicine, sources chip listing every artifact that
touched it (paper/pill-photo/receipt), not one card per source. **Rule:** identity is `(generic,
strength, form)` (product-spec §4, citing `_one_product()`). **Verify:** backend test: a medicine
appearing on 3 source papers lists all 3 as one card's sources, never 3 cards. **Source:** build-spec
§6 ("What is genuinely missing… `GET /profiles/{id}/medicines/{line}/sources` — PROPOSED," **unbuilt
today**); product-spec §2 acceptance test wording.

**A-092 — Today rows / Taken.** *"I tap 'I took it' and that's the whole interaction — no
modal."* **Pass:** the button itself becomes the record (`.btn.light`→`.btn.done`), no confirmation
step; the tap is written with its time and held on the phone if offline, sent later. **Rule:**
offline-hold pattern (design-build-2 §2 table, "Doses, taps, offline holding"). **Verify:** Simulator
+ Expo Go, including an airplane-mode walk. **Source:** reading scene 19; map row 41; product-spec
§2 ("Built — scene 19: 'the button itself becomes the record… no separate confirmation step'").

**A-093 — N left / reorder.** *"Nura reminds me before I run out, and the count is accurate."*
**Pass:** the remaining count drops per tap; the reorder date moves with lead time. **Rule:** none.
**Verify:** backend test simulating N taps, asserting count and reorder-date arithmetic. **Source:**
product-spec §2 ("Built — E04-04/E04-05, 'the count drops per tap, and the reorder date moves with
the lead time'"); the "Ask to order" tap itself is noted as **not yet wired** (E04-05, "missing") —
this item's reorder-date/count half passes; the order-action half does not, and is tracked
separately at A-094.

**A-094 — Reorder action.** *"Tapping 'reorder' actually does something — at minimum drafts a
request."* **Pass:** the reorder tap produces a real drafted action (never a silent no-op). **Rule:**
Nura proposes, never books/sends itself. **Verify:** Simulator + Expo Go; backend test asserting a
tap event triggers a draft. **Source:** product-spec §2 ("the Ask-to-order tap itself still does
nothing" — **fails today**, E04-05).

**A-095 — Add a medicine: by photo.** *"I photograph the box."* **Pass:** reads printed text only
(never guesses from colour/shape); matches against the licensed drug register. **Rule:** high-risk
label-photo rule (A-100) applies where relevant. **Verify:** Simulator + Expo Go; backend test with a
box-photo fixture. **Source:** blueprint-v2 `addmed`; product-spec §2 ("Built — package 11
'Done (#313)'").

**A-096 — Add a medicine: by file.** *"I upload a photo/PDF of the label from my files, not just
the live camera."* **Pass:** same read/match path as A-095, entered via file picker. **Rule:** same
as A-095. **Verify:** Simulator + Expo Go. **Source:** (to be specified by the owner) — sources
describe "photo" and "type/speak" entry explicitly; a file-picker variant of the photo path is
implied by A-032's general file-entry pattern but not separately named for medicines.

**A-097 — Add a medicine: by typing.** *"I type or say the medicine name instead of using the
camera."* **Pass:** typed/spoken entry resolves through the same registry match as the photo path.
**Rule:** same identity rule as A-091. **Verify:** Simulator + Expo Go; backend test with typed
input. **Source:** blueprint-v2 `addmed` `s.see` ("Show the box, or simply type or say it"); audit
§2 row 12 ("voice not built" for the *add* path specifically — **voice input fails today**; typing
is separate and should pass).

**A-098 — Brand → generic.** *"I photograph a box that says 'Norvasc' and Nura knows it's
amlodipine."* **Pass:** brand names resolve to their generic through the licensed registry (233
products, 25 interaction pairs, 50 monographs). **Rule:** none. **Verify:** backend test: `Norvasc` →
`amlodipine` resolves. **Source:** build-spec §6 ("Norvasc and amlodipine resolve to one medicine…
already true today, not aspirational"); product-spec §2 ("brand→generic resolution is measured above
95%").

**A-099 — Class name → "which one?" (never stored).** *"The box only says 'STATIN,' and Nura asks
me which statin rather than recording 'STATIN.'"* **Pass:** on a class-only read, Nura shows the
"which one?" chip step instead of offering "Looks right" over the bare class name; a class name is
never stored as a medicine. **Rule:** `classify_name` → `NameKind.CLASS` routes to clarification,
never to confirm. **Verify:** backend test with a class-only fixture asserting no `MedicationLine`
row is ever created with `generic="STATIN"`. **Source:** audit §5 D-6 (High — **fails today**: "the
app: photo/type-it entries exist… on a class-only box the read-back prints 'The medicine: STATIN'
with 'Looks right' as the primary — no 'which statin?' question"); build-plan package 13 log ("the
backend itself already refuses to store a class name as a medicine" — the write-path refusal exists;
the screen offering "Looks right" over it does not yet route correctly).

**A-100 — Loose pill: check each one.** *"I photograph an unidentified loose pill and Nura checks
it carefully, never guessing."* **Pass:** reads printed text on the pill only; refuses to guess from
colour/shape; where ambiguous, asks rather than records. **Rule:** high-risk label-photo rule — a
high-risk dose can never be recorded from a loose-pill photo, only a label photo. **Verify:** backend
test with an unlabelled-pill fixture. **Source:** map row 42 ("reads printed text only, refuses to
guess from colour/shape — a calm refusal, not a silent guess"); reading scene 19.

**A-101 — High-risk medicines refused without a label photo.** *"A dangerous medicine's dose is
never recorded except from its label."* **Pass:** `refuse_dose_without_label_photo()` runs for
**every** writer (photo, voice, WhatsApp text) — a dose of a high-risk class (anticoagulant, insulin,
cardiac glycoside, antimetabolite, opioid) can only be saved from a label-photo artifact. **Rule:**
`before_fact_write` hook, `app/safety/high_risk.py`. **Verify:** backend test: attempt to write a
high-risk dose from a voice-note-only source, assert refusal. **Source:** product-spec §2 ("Built —
'a dose of one is saved from a label photo, never from a message or a voice note alone'"); audit
§7.3 vetoes table.

**A-102 — High-risk medicines: double-confirmed dose change.** *"Changing a dangerous medicine's
dose asks me twice, not once."* **Pass:** a high-risk-class dose change requires two separate
explicit confirms, not one confirm plus the mandatory label photo (which today stands in for a
second confirmation but is not the same UX). **Rule:** ADR 0019 point 6. **Verify:** backend test:
a high-risk dose-change write requires two distinct confirm events. **Source:** build-spec §4
("PROPOSED: add a second explicit confirm step… since one photo requirement is not the same UX as
two yeses" — **unbuilt today**, gap named explicitly).

**A-103 — Safety screening / interactions: never a verdict.** *"Two medicines of the same class
are flagged for my pharmacist, and Nura itself never says whether they're safe together."* **Pass:**
≥2 distinct generics sharing a drug class produce an `InsightKind.MEDICINE` insight routed
`ask_who=PHARMACIST`, never a verdict rendered as Nura's own judgement. **Rule:** "Nura lists, a
pharmacist judges" (build-spec §6). **Verify:** backend test with two same-class medicines. **Source:**
product-spec §2 ("Built — 'already the blueprint's "Ask your pharmacist" pattern, already routed to
the pharmacist, never a verdict'"); build-spec §6.

**A-104 — Label with pharmacy details keeps its paper open.** *"When a label shows my pharmacy's
details, I can still see the whole label, not just the extracted fields."* **Pass:** the source
artifact (the label photo) stays viewable alongside the extracted medicine card, same as any paper
(A-061). **Rule:** none new. **Verify:** Simulator + Expo Go. **Source:** (to be specified by the
owner) — no source names this exact behaviour separately from the general "see the paper itself"
rule (A-061); treated as that rule applied to a medicine label specifically.

**A-105 — Prescriber sanitised (never in a question before yes).** *"A doctor's name extracted
from a label is never put in front of me as a question before I've confirmed it's really there."*
**Pass:** an extractor-written prescriber string never appears inside a clarifying question or a
patient-facing sentence before the person has confirmed the field itself. **Rule:** "an
extractor-written string is hostile until the person confirms it" (memory rule, cited product-spec
§2). **Verify:** backend test: an unconfirmed prescriber field's raw text never appears in any
generated question string. **Source:** memory: "Nura: extracted text is hostile" (never pass an
extractor-written string — even a lab name — to a model or patient before confirmation); product-spec
§2, #302 pattern.

**A-106 — Stopped lines never current.** *"A medicine I stopped taking is never described as
something I'm currently on."* **Pass:** every read path filters on `status == ACTIVE`; Ask in
particular must not describe a stopped medicine as current. **Rule:** none beyond the filter itself.
**Verify:** backend test with a stopped-then-asked-about medicine, asserting Ask never states it as
active. **Source:** audit §5 D-7 (High — **fails today**: "Ask reads medication lines without
`status == ACTIVE`… Ask will describe a stopped medicine as current").

## 6. Insurance (11, 21) and visits/costs (20)

**A-107 — Policy from a paper: the chip says only what the paper says.** *"My insurance summary
never states more than what my policy document actually says."* **Pass:** every displayed policy
line carries a `{quote, page}` citation traceable to the source artifact; "Your policy says this,"
never "you are covered." **Rule:** "never a made-up midpoint, never a 'covered' percentage
invented" (`cost_expectation.py`, cited build-spec §5). **Verify:** backend test: every
`PolicyDetail` line has a non-null citation. **Source:** build-spec §5 (`PolicyDetail`, `Citation`
shape — **GAP, unbuilt**: today's `Policy` is "a person-typed summary… not a document-parsed
passport," product-spec §4).

**A-108 — Policy from a paper: four sections with page numbers.** *"I see Covers / Not covered /
How to use it / Claims, each with the page it came from."* **Pass:** four tabs (Covers, Not covered,
How to use it, Claims), each row citing its page. **Rule:** same citation rule as A-107. **Verify:**
Simulator + Expo Go; Playwright capture vs blueprint-v2 `policy`. **Source:** blueprint-v2 `policy`;
build-spec §5 (`benefits`, `exclusions`, `how_to_claim`, all **GAP** today).

**A-109 — Policy from a paper: cut notice.** *"If Nura couldn't read the whole document, it tells
me which part it's missing, not a silent gap."* **Pass:** a policy partially read (some pages
failed) shows tabs for the sections that did parse plus a `note` naming the page(s) that did not;
never blocks the whole passport on one bad page. **Rule:** per-page failure isolation (build-spec
§2). **Verify:** backend test with a deliberately corrupted page in a multi-page fixture. **Source:**
build-spec §8 ("A policy partially read… PROPOSED: show tabs for sections that did parse, a `note`
for the page(s) that did not").

**A-110 — Policy from a paper: typed policies still work.** *"If my insurer sends a typed summary
instead of a scanned PDF, Nura still reads it the same way."* **Pass:** the passport's citation and
tab structure applies equally to a typed (non-scanned) source document. **Rule:** same as A-107.
**Verify:** backend test with a typed-text policy fixture. **Source:** (to be specified by the
owner) — no cited source distinguishes typed vs scanned extraction paths for policies specifically.

**A-111 — Cost expectation.** *"I ask what a procedure might cost, and Nura gives a typical range
cited to my own past receipts, never a made-up quote."* **Pass:** figures are cited to the person's
own past receipts; the answer is explicitly framed as typical, never a quote or guarantee, even
before a visit is booked. **Rule:** `cost_expectation.py`'s own rule (build-spec §5). **Verify:**
backend test asserting every cost figure carries a receipt citation. **Source:** blueprint-v2
`visits` `s.does` ("The cost expectation comes from this person's own past receipts and policy,
never a public average, and each figure cites its receipt"); audit §7.1 (ESTIMATE call site's own
comment: "never exercised against the real shape" — **not yet proven working**, needs a real test).

**A-112 — Claim ledger.** *"I see how much has been claimed this year, without a made-up 'percent
covered.'"* **Pass:** ledger sums claims by policy from real claim rows, never an invented
percentage. **Rule:** same as A-111's display rule. **Verify:** backend test. **Source:** product-spec
§4 ("Built on the ledger side — `insurance_ledger()` sums claims by policy").

**A-113 — Visits: planner proposals via confirm flow.** *"Nura suggests logistics — like who
drives me — and nothing happens until I say yes."* **Pass:** every planner proposal (driver,
booking, message) requires an explicit confirm before any write; Nura proposes, never books.
**Rule:** "Nura never sends anything itself" (product-spec §1). **Verify:** backend test: a
proposal without a confirm event writes nothing. **Source:** blueprint-v2 `visits` `s.see` ("Nura
proposes, never books"); product-spec §2 ("driver suggested… confirmed with a yes").

**A-114 — Visits: questions to ask.** *"The questions Nura suggests for my visit are written the
way I'd actually say them, not a raw code."* **Pass:** first-person questions from a checked bank,
never a raw fact-code string. **Rule:** plain-words rule 1. **Verify:** plain-words lint. **Source:**
product-spec §2 ("Built, after rework… 'one card "For Dr Lim on 25 September," first-person
questions from a checked bank'" — the original raw-code version was rejected once, #303).

**A-115 — Visits: logistics.** *"Nura suggests who should drive me, from my family roster."*
**Pass:** a driver suggestion draws from the actual family roster, confirmed with a yes. **Rule:**
same confirm-gate as A-113. **Verify:** backend test. **Source:** product-spec §2 ("Built — E05-03").

**A-116 — Visits: the brief.** *"Before my visit, I see a pre-visit brief pulling together what
matters."* **Pass:** the pre-visit brief renders from State and passes plain-words verification.
**Rule:** every rendered brief line passes `plain_words.verify`. **Verify:** backend test. **Source:**
product-spec §4 ("The pre-visit brief, question generation, post-visit summary and memo
consolidation, all rendered from State and passed through the plain-words verifier").

**A-117 — Visits: after-visit.** *"After my visit, what the doctor said becomes my own memos, never
a silent medicine change."* **Pass:** post-visit notes become memos; any implied medicine change
becomes a flag and a question, **never** an automatic change. **Rule:** "actions become memos, a
medicine change becomes a flag and a question (never a change)" (product-spec §4). **Verify:**
backend test: a post-visit note implying a dose change writes zero `MedicationLine` mutations, only
a flag. **Source:** product-spec §4; product-spec §2 ("Built — E05-05, web confirm step still
API-only" — **the web confirm UI is not yet built**, only the API path).

---

## 7. Feed (scene 22)

**A-118 — Cards of each type.** *"The content Nura shows me is one of a small set of honest kinds
— an explainer, a clip, my own trend, a local alert, food advice, something worth asking my
doctor, a recall action, a seasonal note — never something arbitrary."* **Pass:** every rendered
card is one of `Explainer, Compressed video, Own-data insight, Local alert, Food and habit, Worth
knowing, Recall action, Seasonal` — `Safety notice` is **never** a patient card (see A-121). **Rule:**
feed-spec §2 card-type table. **Verify:** backend test: every `FeedItem.type` for `deliverTo=patient`
is one of the allowed patient-facing types. **Source:** feed-spec §2.

**A-119 — Why-lines.** *"Every card tells me why I'm seeing it, in my own terms — 'Because you take
amlodipine.'"* **Pass:** every card carries a `why` field, one plain sentence, personalised, never
"Recommended videos." **Rule:** design-build-2 §14 ("Because you take amlodipine, not 'Recommended
videos'"). **Verify:** backend test: every `FeedItem.why` is non-empty and personalised (references a
profile fact id). **Source:** design-build-2 §14; feed-spec §2 (`why` field).

**A-120 — Quiet hours.** *"Nura doesn't ping me at night."* **Pass:** no card delivery/notification
between quiet hours (verified live at 21:00–07:00 in the source's own walk — restated here without
inventing a different number: this range is the one the build log actually measured). **Rule:**
feed-spec §3 step 7 ("quiet hours respected"). **Verify:** backend test: no delivery scheduled inside
the quiet window. **Source:** product-spec §2 ("Built — verified live: 'the feed is quiet 21:00–07:00
by design'"); feed-spec §3.

**A-121 — Safety notice never a patient card.** *"A regulator's recall notice about my medicine is
never shown to me directly as a card — only what I myself need to do about it."* **Pass:** a safety
notice is **always** held for the chief/caregiver and, where it's a doctor question, routed to the
memo — never rendered as the patient's own card, whether or not it matches his pack's batch. Where
his own batch matches, he gets a **separate**, rewritten `RECALL_ACTION` card in his own words,
never the notice's own wording. **Rule:** feed-spec §0/§2 ("§0 wins" — resolved explicitly after an
earlier draft read ambiguously). **Verify:** backend test (already exists per source): a matching
recall gives the patient the action card and the chief the notice; a non-matching recall reaches
only the chief; a recall that both matches and changes treatment still gives the action card while
the notice itself reroutes to a doctor question. **Source:** feed-spec §0, §2 ("Built" — #181, #183,
#224, #236, with `tests/test_feed.py` asserting all three cases already).

**A-122 — One "did you know" a day.** *"I get at most one 'did you know' card per day."* **Pass:**
cap of one `LEARNING`-flavoured "did you know" card per day, within the overall two-new-cards-a-day
cap. **Rule:** feed-spec §3 step 7 ("Two-per-day cap"). **Verify:** backend test. **Source:**
feed-spec §1 (placement table, "2 new per day"), §3.

**A-123 — Story told once.** *"A recall card from my own history doesn't repeat itself."* **Pass:**
the newest card per story wins; a story is never surfaced twice. **Rule:** feed-spec ordering fix
(#315). **Verify:** backend test. **Source:** product-spec §2 ("Built, after a fix… 'the newest card
per story; past the gate a learning card first, then turns, one card per kind'" — #315).

**A-124 — Order: Now → Today → gate → His story → Learning.** *"New things about me come first,
then a clear 'that's all for now,' then things from my own history, then general learning — I'm
never buried in general content before my own."* **Pass:** the pager's supply order is exactly Now
→ Today (≤2 new) → gate card → His story → Learning, in that order, every time. **Rule:** feed-spec
§0. **Verify:** backend test asserting card order matches this sequence for a fixture profile.
**Source:** feed-spec §0; product-spec §2 ("Built, after a fix").

**A-125 — Hear / Ask / Family / Not for me.** *"Every card, I can hear it, ask about it, share it
with family, or say it's not for me."* **Pass:** all four actions present on every card, with "Not
for me" always a visible, single-tap button (never a two-line-wrapped afterthought). **Rule:**
feed-spec §6 ("'Not for me' is a visible button on every card"). **Verify:** Simulator + Expo Go;
Playwright capture. **Source:** feed-spec §6; audit §2 row 22 ("the action row's fourth item 'Not
for me' wraps to two lines and sits lower than its three neighbours" — **fails today** visually,
D-territory not separately numbered).

**A-126 — Not for me remembered.** *"Saying 'not for me' actually changes what I see next, without
me having to explain why."* **Pass:** two ignored text cards flip the profile's preferred format to
voice; dismissal feeds novelty scoring. **Rule:** feed-spec §3 step 9. **Verify:** backend test: two
`dismissed` events flip `preferred_format`. **Source:** feed-spec §3 step 9; product-spec §2
("Built — 'engagement events… feed novelty and format fit'").

**A-127 — Allow-listed publishers only.** *"Everything Nura shows me from outside my own record
comes from a source I could trust — never a random site."* **Pass:** zero cards from a
non-allowlisted source (hard check); the allowlist is reviewed quarterly by the pharmacist. **Rule:**
feed-spec §7 ("Allowlist is data, reviewed quarterly… adding a source requires review"). **Verify:**
backend test: every `FeedItem.source` is on the allowlist. **Source:** feed-spec §2, §7, §8 ("zero
cards from non-allowlisted sources (hard check)").

**A-128 — Closed-vocabulary queries.** *"Nura's searches on my behalf use fixed, safe terms, not an
open-ended model query."* **Pass:** feed search queries are built from a closed vocabulary (no
model deciding the query itself). **Rule:** audit §7.2 ("Feed… closed-vocabulary query (no model,
`search.py:667`)"). **Verify:** backend test/code inspection: query construction path has no LLM
call. **Source:** audit §7.2 ("Feed… Stay as prompt chaining. The structure is right").

**A-129 — Live search capped.** *"Nura doesn't run unlimited searches on my behalf."* **Pass:** a
run-level cap (`NURA_MAX_JOBS_PER_RUN`, default 6) and a per-call server-tool cap
(`SEARCH_TOOL_MAX_USES = 3`) both hold. **Rule:** ADR 0018 decision 4. **Verify:** backend test:
exceeding either cap halts further calls. **Source:** product-spec §5 ("A run itself is capped
independently of the model… 'the model decides what one call costs, the cap decides how many calls
one run can make'").

**A-130 — Clips never embed a platform.** *"A video clip plays inline with captions — it's never an
embedded third-party player with its own chrome."* **Pass:** clips render via the app's own
`<video>`/poster-and-play mechanism, captioned, linking out to the original only for the full video —
never an embedded YouTube/social iframe. **Rule:** feed-spec §7 ("Video excerpts: link to the
original, attribute the channel, keep excerpts within the platform's terms"). **Verify:** Playwright/
DOM check: no third-party iframe present on a clip card. **Source:** build-spec §0(b) (`ClipMedia`/
`GuideClip` "a poster button that, on tap, fetches a still and… an excerpt video, played in-page
(`<video>` element, never a redirect)"); feed-spec §7.

## 8. Not well / emergency (23), Connect (24), Mei's view (25), Profile (26)

**A-131 — Red flag never delayed.** *"If I say something urgent, Nura tells my family immediately —
never held for later."* **Pass:** a red-flag word from any channel (feeling cloud, WhatsApp free
text, the not-feeling-well button, the symptom log) raises the same `Flag` and escalates before any
ranking, cap, or quiet-hours delay. **Rule:** red flags skip the ladder's own rung; never held for
quiet hours (ADR 0005 decision 2). **Verify:** backend test: a red-flag Flag created during the
quiet-hours window still escalates immediately. **Source:** product-spec §5 ("Built — 'Red flags
skip his rung… never held for the quiet hours'"); ADR 0005.

**A-132 — Not well: no thinking delay.** *"Tapping 'not well' feels urgent, not performative — no
loading animation, no delay."* **Pass:** no thinking animation, no streaming, no stagger; the
reveal runs at the fastest measured pace in the reference (`--alarm-reveal`); the background swaps
colour in the same frame as the card appears. **Rule:** deliberate departure from the calm
vocabulary — red flags run with no model in the loop. **Verify:** Simulator + Expo Go; Playwright
trace confirming no `nura()`/thinking call fires on this path. **Source:** blueprint-v2 `unwell`;
audit §2 row 23 ("No thinking animation, no delay — correct").

**A-133 — Offline emergency card.** *"My emergency card — conditions, medicines, allergies, a
number to call — is available even with no signal."* **Pass:** the emergency card renders fully
offline, from an on-device cached copy, not a placeholder. **Rule:** offline storage never holds
facts beyond the kept Today page/emergency card (mobile-architecture §2, `lib/storage`). **Verify:**
Simulator + Expo Go in airplane mode. **Source:** product-spec §2 ("Built on the backend, with a
real client-side gap — the web shows only a placeholder ('Nura will keep your emergency card here')
offline" — **fails today** on web; strings `emergencySoon: "Nura will keep your emergency card
here."` en.ts:846, `none: "Your emergency card is not on this phone yet."` en.ts:1308).

**A-134 — Ambulance-tier fall-on-blood-thinner rule.** *"A fall while I'm on a blood thinner is
always treated as urgent, whatever the hour, until a clinician has signed off the softer rule."*
**Pass:** with the clinical-sign-off switch unset (the default), every red flag's step is the
ambulance tier — no softer tier is reachable until a clinician signs the table. **Rule:** ADR 0010
("Unset — every deployment until the sign-off — every red flag's step is the ambulance"). **Verify:**
backend test asserting the switch's default state routes to ambulance-tier. **Source:** product-spec
§2 ("Built, but gated off pending clinical sign-off"); ADR 0010.

**A-135 — Drafted messages never sent by Nura.** *"Nura drafts a message for me but never sends it
itself — I send it."* **Pass:** every drafted message (to a doctor, an insurer, family) requires the
person's own send action from their own device/account; no code path calls a send API on the
person's behalf. **Rule:** "Nura never sends anything itself." **Verify:** backend test/code
inspection: no outbound-send call exists in the draft-completion path. **Source:** blueprint-v2
`visits` ("Nura proposes, never books"); product-spec §1 ("navigation drafts… are sent by the
person from their own phone").

**A-136 — Mei's Home: same calls, different words.** *"Mei sees the same Home Nura shows me, but
spoken about me, in her voice, from the same underlying data."* **Pass:** Mei's Home is proven to be
a **data substitution** of the same render function — same event calls, same timings — never a
parallel component tree. **Rule:** none beyond consistency. **Verify:** code inspection/e2e:
Home and Mei's Home render paths share one function with a different vocabulary object, not two
implementations. **Source:** reading conclusion #10 ("the caregiver view (scene 25) is proven to be
a data substitution, not a second template… same function calls, same timings, different words");
blueprint-v2 `mei` (`s.does`: "this file enforces it by sharing one render function").

**A-137 — "Pa's," never "your."** *"When Mei reads about me, every sentence says 'Pa's,' never
addresses her as if she were the patient."* **Pass:** zero patient-voiced ("your") sentences appear
anywhere in Mei's own screens; every sentence has a caregiver twin. **Rule:** plain-words rule 4/13
consistency, applied per-surface. **Verify:** plain-words lint scoped to caregiver strings; backend
test. **Source:** blueprint-v2 `mei` `s.does` ("says 'Pa's blood pressure', not 'your blood
pressure'"); audit §4.3 ("Mei's Health and Feed show the ask-bar placeholder 'Your question' —
patient voice on a caregiver screen" — **fails today**, D-20).

**A-138 — Scopes per role.** *"What each person I share with can see is exact, not all-or-nothing —
and I can see it plainly stated."* **Pass:** each of the six roles (`CHIEF, CAREGIVER, VIEWER,
HELPER, EMERGENCY, CLINIC`) presets exactly the scopes in `scopes.py` `ROLE_SCOPES`; every key holds
`PROFILE`; only a `CHIEF` is ever preset to `NOTES`/full `MONEY`. **Rule:** scopes.py. **Verify:**
backend conformance test asserting each role's granted scopes match `ROLE_SCOPES` exactly. **Source:**
scopes.py; product-spec §2 ("Built on the backend, thin on the web — 'Web cuts only a "caregiver" key
by parts: no role choice, no time window, no narrowing'" — **the web UI for precise role/scope
selection fails today**, even though the backend model is correct).

**A-139 — "Let someone in" and consent read in full.** *"Before I grant access, Nura reads the
consent words to me in full, and I can withdraw in one tap."* **Pass:** granting a key streams the
scope choice and the consent words in full before the grant is created; revocation is a single tap.
**Rule:** consent is mandatory, never defaulted (ADR 0015 fix — role and window are required,
non-defaultable at the API boundary). **Verify:** backend test: a grant call missing role or window
is rejected. **Source:** blueprint-v2 `family` `s.does` ("Consent is read out in full before it is
given, and can be withdrawn in one tap"); product-spec §5 (ADR 0015).

**A-140 — Connect: not empty where the blueprint shows people.** *"My Connect screen shows who has
access, with their role, not empty sections."* **Pass:** three populated role rows (Chief/Doctor/
Helper-shaped), not three empty-state sections ("No call is on your calendar yet," etc.) for a
profile that actually has grants. **Rule:** none beyond honest empty-vs-populated rendering.
**Verify:** Simulator + Expo Go with a fixture profile that has real grants. **Source:** audit §2
row 24 (**fails today**: "an avatar grid plus four empty sections… where the blueprint shows three
populated role rows"); product-spec §2 ("Not built — package 14").

**A-141 — Profile freezes nowhere (D-0).** *"Opening my Profile never freezes the app."* **Pass:**
opening Profile on WebKit (the only engine on an iPhone) does not block the main thread; the page
remains responsive within 500ms of the tap, measured. **Rule:** none beyond basic responsiveness.
**Verify:** WebKit-specific Playwright test (today's CI runs chromium only — a WebKit project must
be added, per the audit's own fix direction); Simulator + Expo Go on real hardware. **Source:** audit
§5 D-0 (**Critical, fails today**: "opening Profile freezes the page… within 500ms… on the owner's
own iPhone this tab does not open at all"); this is one of ADR 0019's four named hard gates (A-007).

**A-142 — Profile: settings as sentences.** *"Most of what used to be settings is now something I
just tell Nura, in a sentence."* **Pass:** the profile screen is six large rows with right-aligned
values and one reassurance line, most already answered ("On," "English · Bahasa Melayu · 中文"), not
a long scroll of switches and blocks. **Rule:** design-build-2 §26 (simplicity). **Verify:**
Playwright capture vs blueprint-v2 `profile`. **Source:** blueprint-v2 `profile`; audit §2 row 26
("a long scroll: avatar, a streak card, a 3-button language row, six list rows, two more actions, a
five-switch block, a town block, a Ramadan block, Sign out" — **fails today**, structurally
different from the six-row target).

---

## 9. The engine and safety (ADR 0019 §6–7, audit §3, §7)

**A-143 — One event vocabulary on every run.** *"Whatever screen I'm on, the same kind of signal
tells the app what Nura is doing — not six different private languages."* **Pass:** every streamed
route (papers, ask, insights, photos/imports, find, not-feeling-well) emits the same AG-UI-shaped
vocabulary: `RUN_STARTED`, `TEXT_MESSAGE_START/CONTENT/END`, `TOOL_CALL_START/ARGS/END/RESULT`,
`STATE_SNAPSHOT`, `STATE_DELTA`, `RUN_FINISHED`, `RUN_ERROR` — never route-specific event names.
**Rule:** ADR 0019 point 4 ("Adopt the vocabulary, not the library"). **Verify:** backend
conformance test asserting every stream's event `type` values are drawn from this one closed set;
Simulator + Expo Go. **Source:** ADR 0019 point 4; audit §7.1/§7.4 (**fails today**: "six bespoke SSE
vocabularies… four mutually incompatible terminal events for one concept").

**A-144 — `TOOL_CALL_*` events carry no free text.** *"When Nura reads my record to answer me, I can
tell what it looked at structurally, not just an opaque localised sentence."* **Pass:** `TOOL_CALL_
START`/`ARGS`/`RESULT` carry the tool name and structured arguments/result, never a pre-localised
prose sentence standing in for the call. **Rule:** ADR 0019 point 4. **Verify:** backend test:
`TOOL_CALL_ARGS` payload is structured JSON, not a string containing display copy. **Source:** audit
§7.1 ("the identity is gone by the time it reaches the wire… `TOOL_STEP_KEYS` maps a tool name…
into an opaque localised sentence" — **fails today**).

**A-145 — Fixtures emit the same events as live.** *"Whether Nura is running on test data or a real
model, the app behaves identically — Fixture → Claude is just configuration."* **Pass:**
`FixturePaperExtractor`, `FixtureMedicineMatcher`, `FixtureSearch`, `FixtureCompressor` all emit the
identical event stream shape a live adapter would. **Rule:** ADR 0019 point 12. **Verify:** a swap
test (`tests/swap/`) running the same conformance suite against both a fixture and a live-shaped
stub adapter. **Source:** ADR 0019 point 12.

**A-146 — D1 provenance: Answer → Fact → Artifact → confirmed.** *"Every number Nura tells me
traces back to a paper I actually confirmed — never 'the model remembers.'"* **Pass:** every stated
value in any Nura output is traceable through a chain: the Answer cites a Fact, the Fact cites an
Artifact/Event, and the Fact's `confidence_state` shows it was confirmed by a person. **Rule:** D1
(A-007). **Verify:** backend conformance test walking this chain for a sample of generated answers.
**Source:** ADR 0019 point 7 (D1); audit §3.1 (the cholesterol-number failure is the concrete case
this gate exists to prevent).

**A-147 — D2 whose-paper unbypassable.** *"There is no way for a paper to be filed to my record
without the identity check running first."* **Pass:** every ingestion write path (photo, PDF, batch,
WhatsApp) runs identity extraction → match → confidence → confirm before any Fact write; no code
path skips it. **Rule:** D2 (A-007); deterministic rules only. **Verify:** a `tests/consent/`-style
property test asserting no `Fact` row exists whose originating artifact never passed the whose-paper
check. **Source:** ADR 0019 point 7; build-spec whose-paper addendum; audit §5 D-2.

**A-148 — D3: rejected conclusions recorded, content-free.** *"When Nura gets something wrong and I
correct it, that correction is kept as a record — but the record itself never stores personal
health free text where it shouldn't."* **Pass:** every corrected/rejected AI conclusion is recorded
(conclusion, user response, reason, timestamp, actor, new state); the record structure itself
follows the same "no raw rows crossing a boundary" discipline as any other audit row — structured
fields, not a dumped free-text blob. **Rule:** D3 (A-007). **Verify:** backend test: a rejection
writes a structured `Finding`/rejection row with all six fields present. **Source:** ADR 0019 point
7; audit §3.1c (the pseudo-rule-91 pattern that should generalise, `ask_agent.py:1722`).

**A-149 — Row scope for every route.** *"A key that can't see a scope of mine never sees rows I
wrote under it, even through an unrelated table."* **Pass:** a row is read only under the scope it
was written under; a key lacking that scope never receives the row through any other table's join.
**Rule:** ADR 0004 ("rows are read under the scope they were written under"). **Verify:** the
locality/scope property test suite (`tests/conformance` equivalent) asserting no cross-scope leak
for every route. **Source:** product-spec §5 (ADR 0004 — "fixed… after per-table scope checks were
found to leak rows written under a *different* scope through the same table").

**A-150 — Consent record mandatory on every cross-entity call.** *"Nothing that touches more than
my own record happens without a recorded consent — never assumed, never defaulted."* **Pass:**
every cross-entity call (sharing, a caregiver grant, a clinic key) requires a non-optional,
non-defaultable consent parameter; a call missing it is rejected, not silently allowed through with
an implicit default. **Rule:** ADR 0015 (role and window "required, never optional" after a real
regression where the web client silently unbound every family grant). **Verify:** backend test: a
grant call with a missing role/window field is rejected at the API boundary, not defaulted.
**Source:** product-spec §5 (ADR 0015); ADR 0019's own operating contract (referenced project-wide).

**A-151 — Audit row on every action.** *"Every time anyone reads, writes or shares my health
record, it's written down — and only I and my chief can read that trail."* **Pass:** every
cross-entity read/write/share produces exactly one audit row through the one existing door
(`audited_write`); no unlogged path exists. **Rule:** *"Every read, every write and every share of
one person's health graph"* is written down (product-spec §5, `backend/app/audit/__init__.py`).
**Verify:** backend conformance test: every mutating endpoint's handler calls the audit door;
`tests/consent/`-style property test asserting no write bypasses it. **Source:** product-spec §5;
ADR 0005 (escalations recorded once, through one door, replacing three separate non-sending
records).

**A-152 — Residency gate.** *"My health data never leaves my region, except the one narrow,
declared, audited case."* **Pass:** every Person/Profile is pinned to a region (SG or MY) at
creation; health data never leaves it, except a Claude-backed model call under the one declared
exception, itself audited as a distinct "reach outside region" event and permitted **only** under
`NURA_DEMO_MODE=1` or `NURA_DEV_CODE_SENDER=1` — never on a public deployment. **Rule:** ADR 0017.
**Verify:** backend test: constructing a Claude-backed adapter outside a declared demo/dev flag
raises; a successful call writes an `EXTERNAL_MODEL_PROCESSOR` audit event. **Source:** product-spec
§5 (ADR 0017); CLAUDE.md "Profiles are pinned to a region."

**A-153 — Model per task.** *"Nura doesn't burn an expensive model on a job a cheap one could do
just as safely."* **Pass:** each of the nine model tasks resolves to its assigned model per ADR
0018's table — `extract`/`ask` → Opus 5; `analyst`/`search`/`estimate`/`draft` → Sonnet 5;
`compress`/`clip`/`narrate` → Haiku 4.5 — and never silently escalates. **Rule:** ADR 0018. **Verify:**
backend conformance test asserting each task's configured model matches the table. **Source:**
product-spec §5 (ADR 0018, "before this ADR… about 48 Opus calls… and produced one card").

**A-154 — Live AI enabled one capability at a time.** *"Nura's real-model features are turned on
one at a time, each proven safe before the next."* **Pass:** the enablement order — paper extraction
→ Ask (source-grounded) → medicine extraction + deterministic registry → state recomputation
(deterministic) → Analyst → feed → voice → multimodal — is followed; a later capability is never
enabled while an earlier one's safety boundary is still open. **Rule:** ADR 0019 point 13.
**Verify:** a deployment-config test asserting enabled capability flags never skip ahead of this
order. **Source:** ADR 0019 point 13.

**A-155 — Keep-alive during model reads.** *"A long read from Nura never times out on me while it's
still genuinely working."* **Pass:** every streamed route sends a real heartbeat at an interval
comfortably inside the client's give-up threshold (today 180s — A-036); the client's own docstring
and behaviour agree on the threshold. **Rule:** none beyond reliability. **Verify:** backend test: a
held-open stream with no content for >150s still shows a live heartbeat; Simulator + Expo Go.
**Source:** audit §3.4 ("No SSE heartbeat exists… the client gives up after 180s of silence on a
justification its own docstring gets wrong" — **fails today**).

**A-156 — No HTTP code ever on screen.** *"When something goes wrong, I read a plain sentence, never
a number like '500' or '404.'"* **Pass:** zero patient- or caregiver-facing surfaces ever render a
raw status code; every failure path resolves to a plain-words error state (why, what, next).
**Rule:** design-build-2 §23. **Verify:** plain-words lint + Playwright: force each documented
failure path, assert no digit-status-code string appears in the DOM. **Source:** design-build-2 §23;
audit §7.1 (today: "six different hand-written rejection strings… for the one condition 'the
terminal event never came'" — the *strings themselves* are plain-worded already, but **fails the
"one ErrorState primitive" requirement** — see A-209 in §10).

**A-157 — Remaining ranked defects closing this gate.** The audit's §5 table names D-0 through D-25;
every one is a pass criterion of this document even where it is not repeated as its own row above.
The table below completes the set not already covered by name in §§1–8 (D-0 → A-141; D-1 → A-076;
D-2 → A-037–042/A-147; D-3 → A-077/A-148; D-4 → A-043–044; D-5 → A-056; D-6 → A-099; D-7 → A-106;
D-10/D-11 → A-020/A-023; D-12 → A-049; D-14 → A-069; D-20/D-22 → A-083/A-137/A-064; D-21/D-24 → §10).

| Defect | Pass criterion (this gate) | Verify | Source |
|---|---|---|---|
| **D-8** | `valid_to` is written and `supersedes_id` set on every superseding fact write; the Ask read path applies the validity window (`_facts_under` filters by window, not just `superseded_at IS NULL`) — two lab results for one analyte are never both "current." | Backend test: superseding a fact closes the old one with `valid_to` and the Ask read excludes it. | audit §5 D-8 (High, **fails today**) |
| **D-9** | After a policy is confirmed ("Looks right"), it actually appears on the Insurance screen — not trapped behind D-16's dead end. | Simulator + Expo Go walk: confirm a policy, reload Insurance, assert it renders. | audit §5 D-9 (**not fully diagnosed** in the audit itself — must be re-walked once D-16 is fixed) |
| **D-13** | Ask can read the structured, cited insurance essentials (`coverage_items`, `excludes`, `benefits`, `claim_steps` with page numbers) — not only the four-field/400-character paraphrase it reads today. | Backend test: an Ask question about coverage returns a page-cited answer from `PolicyDetail`. | audit §5 D-13 (Medium, **fails today**) |
| **D-15** | Every feed card's prepared voice actually builds; a card never silently falls back to the phone's own voice more than an explicitly bounded number of times without the failure being logged as a defect, not swallowed. | Backend test with a long card body: voice synthesis succeeds or fails loudly, never `TooLongToSay` silently ten times in one walk. | audit §5 D-15 (Medium, **fails today**) |
| **D-16** | Confirming a policy opens a real modal/screen for the propose sheet — never rendered on top of a stale empty state; the tab bar remains responsive throughout. | Simulator + Expo Go; Playwright: tap every tab after the propose-sheet flow, assert each responds. | audit §5 D-16 (High, **fails today** — "the tab bar stops responding… in both engines") |
| **D-17** | The previous card's status line is cleared when the onboarding card changes — never left on screen for the next card. | Playwright: walk cards 2–6 of onboarding, assert no stale status text persists. | audit §5 D-17 (Medium, **fails today**) |
| **D-25** | `run_weekly` is either wired to a real scheduler or removed, and `ClaudeClipMaker` is either constructed in production or removed — the plan states which, in either case, rather than leaving dead code that looks load-bearing. | Code inspection + a scheduler test (if wired) or its absence documented in `build-plan.md`. | audit §5 D-25 (Low, **fails today** — both are currently dead/unwired) |

---

## 10. Experience quality (design-build-2 §2–§28)

**A-158 — Every scene against its blueprint-v2 frame, in both engines.** *"Every screen actually
looks and moves the way the reference does — not just tells the right story."* **Pass, per scene:**
a Playwright capture at 390×844 (phone) and 1280×900 (wide), in **Chromium and WebKit**, sits beside
the corresponding `blueprint-v2` frame with matching structure, type scale, motion tokens and
`s.see` behaviour; plus a Simulator/Expo Go walk. Detailed behavioural criteria for the 26 original
scenes are given by their own items above (cross-referenced in the table); the seven new "system"
scenes (motion, orb states, composer, expand, shared element, sheet, loading/empty/error) are new in
v2 and have no prior item, so their full criteria are given here. **Rule:** design-build-2 §3
checklist, every line. **Verify:** Simulator + Expo Go + Playwright, both engines, per scene.
**Source:** blueprint-v2 (all 33 scenes); design-build-2 §3.

| Scene (`key`) | Group | Pass criterion | Cross-ref / audit verdict |
|---|---|---|---|
| `welcome` | Arrive | Orb-first, no chrome beyond one streamed sentence + Start | A-010; audit row 01 Partly |
| `signin` | Arrive | Question-shaped, no password, fields reveal in sequence | A-011–014; audit row 02 Matches |
| `who` | Arrive | Conversation shape: bubble → chips → reply → second turn | A-015–017; audit row 03 Partly |
| `cloud` | Arrive | Irregular bubble cloud, sized by frequency, bobbing at rest | A-023–029; audit row 04 Not (D-11) |
| `firstpaper` | Your papers | Three entry rows + skip, no penalty framing | A-031–034; audit row 05 Partly |
| `reading` | Your papers | Real backend stages, one status line in place | A-035–036; audit row 06 Matches |
| `report` | Your papers | One table, range bars, one flagged row | A-047–053; audit row 07 Partly (D-12) |
| `insight` | Your papers | Unprompted connection to medicines/visit | A-054–056; audit row 08 Partly/unreachable (D-5) |
| `inbox` | One record | Queue with two motion channels, fingerprint dedup | A-057; audit row 09 Partly |
| `matching` | One record | Six plain verdicts, trend draws itself | A-058, A-066; audit row 10 Not verified |
| `policy` | One record | Passport: counted-up numbers, four cited tabs, real page-progress | A-107–110; audit row 11 Not |
| `addmed` | One record | Which-statin clarify, never guesses | A-095–102; audit row 12 Partly (D-6) |
| `registry` | One record | Now/All/Changes tabs, one card per medicine merging sources | A-091, A-098; audit row 13 Not |
| `connected` | One record | Counted-up number, five doors from one screen | A-067; audit row 14 Partly |
| `home` | Every day | Two-line header, one insight, composer expands in place | A-068–074; audit row 15 Partly (D-22) |
| `ask` | Every day | Two-turn memory, sources before answer, dense-card stagger | A-074–090; audit row 16 Partly (D-1/D-3) |
| `health` | Every day | Expandable blood-pressure card: week→daily→changed→connects→act, count-up 148 | **new item, A-159** below; audit row 17 Not (D-18) |
| `analyst` | Every day | Sequential section reveal, omits empty sections, never repeats itself | **new item, A-160** below; audit row 18 Partly (D-23) |
| `meds` | Every day | Plain name first, tap-becomes-record | A-092–093; audit row 19 Partly (D-19) |
| `visits` | Care and money | One card, propose-never-book, draggable sheets | A-113–117; audit row 20 Not |
| `insurance` | Care and money | Policy card + short-list ledger, named-withheld sections | A-107–112; audit row 21 Not |
| `feed` | Every day | Why-before-what clips, full media state machine (idle/loading/playing/paused/complete) | A-118–130; audit row 22 Partly |
| `unwell` | Safety | Fastest reveal in the file, colour swap same frame, no calm vocabulary | A-131–132; audit row 23 Partly |
| `family` | Family | People not settings; scopes and windows named per row | A-138–140; audit row 24 Not |
| `mei` | Family | Same render function, caregiver vocabulary substitution | A-136–137; audit row 25 Partly |
| `profile` | Family | Six rows, most pre-answered, no freeze | A-141–142; audit row 26 Not (D-0) |
| `motion` | The system | All durations/easings read live from `:root` tokens via `getComputedStyle`, none hard-coded | **A-161** below |
| `orbstates` | The system | Five real states, each mapped to one real event | **A-162** below |
| `composer` | The system | Expands in place, context-first, three-way chip exit | A-074–075; **A-163** below |
| `expand` | The system | Same card grown through 5 steps via View Transitions where supported | A-072; **A-164** below |
| `shared` | The system | Card clones, morphs into detail, morphs back on close | A-072; **A-165** below |
| `sheet` | The system | Real pointer drag, velocity-aware dismissal, spring return | **A-166** below |
| `states` | The system | One `LoadingState`/`EmptyState`/`ErrorState` primitive each, not per-screen copy | **A-167** below |

**A-159 — Health: the expandable trend card.** *"My blood pressure card is one object I can open
deeper and deeper — the week's chart, then the daily numbers, then what changed, then what it
connects to, then what I can do."* **Pass:** tapping the blood-pressure metric card steps through
exactly this five-stage chain as **the same object growing**, never a navigation; the chart draws
itself (`--chart-draw`, one highlighted point, subtle fill, no gridlines); the "148" counts up on
arrival; the shaded band is the person's own usual range, never a comparison with other people.
**Rule:** design-build-2 §11, §16 ("Nura never compares you with other people," blueprint-v2 `health`
`s.does`). **Verify:** Simulator + Expo Go; Playwright trace of the five-tap sequence, frame-timed
per A-005. **Source:** blueprint-v2 `health`; audit §2 row 17, D-18 (**fails today**: "there is no
chart anywhere in the app… blood pressure is a plain text row").

**A-160 — Health Analyst: sequential reveal, honest omission.** *"My weekly report reads through
its sections one at a time, and a section with nothing to say just isn't there — never shown
empty."* **Pass:** the orb narrates four real stages, then a `looked_at` chip row, then each section
card reveals **one at a time**, each waiting its own full beat (not a shared stagger); a section
with nothing to report is omitted entirely; the headline finding and any "what changed" card never
repeat the same sentence twice; no stray glyphs; one date line, not two competing ones. **Rule:**
none beyond honest omission and non-duplication. **Verify:** Simulator + Expo Go; Playwright capture.
**Source:** blueprint-v2 `analyst`; audit §2 row 18, D-23 (**fails today**: "the headline finding and
the 'What changed' card say nearly the same sentence… 'Ask Dr Tan this' is back… a stray ✓ glyph…
two competing date lines").

**A-161 — Motion tokens, nothing hard-coded (lint).** *"Every animation in the app comes from one
shared set of timings, so changing the feel in one place changes it everywhere."* **Pass:** a lint
rule fails a hard-coded duration/easing value anywhere in `web/src/ui` or the native `motion/`
package; every duration/easing is read from the token set (`motion.fast/standard/slow`,
`spring.gentle/standard/bouncy`, `fade.enter/exit`, `scale.press`, `card.enter`, `sheet.enter`,
`orb.idle/listening/thinking/responding`). **Rule:** design-build-2 §24. **Verify:** a static lint
check in CI; code inspection. **Source:** design-build-2 §24 (**fails today**: "No spring family, no
per-role tokens, values hard-coded in places" — only `--settle`/`--press`/`--wash-fade` exist,
`design-build-2-map` §3).

**A-162 — Orb driven by events, never a timer.** *"The orb's mood always matches what Nura is
actually doing — it never fakes being busy."* **Pass:** all five orb states (idle, listening,
thinking, responding, error) are driven exclusively by real events from the one vocabulary (A-143);
no `setTimeout`-only state change exists anywhere in the orb's implementation. **Rule:** ADR 0019
point 4 ("motion represents real state and never fakes time"). **Verify:** a Playwright trace
correlating every orb `data-state` change to a corresponding SSE event; Simulator + Expo Go.
**Source:** blueprint-v2 `orbstates` (`s.does`: "The reference has two states only… Listening,
responding and error are designed from the specification's prose. Each maps to one event of the
AG-UI-shaped vocabulary the engine still has to grow" — **listening/responding/error are unbuilt on
real events today**, map §2.1).

**A-163 — Composer: full state walk.** *"Tapping Ask, asking a question, getting an answer, and
exiting all happen without leaving Home."* **Pass:** listening → thinking → responding orb states
fire in sequence during a real composer turn; the answer puts context first, then one question back,
then three chip-shaped exits (Explain / Show readings / Ask something else); none of the three exits
opens a generic chatbot. **Rule:** design-build-2 §9–10. **Verify:** Simulator + Expo Go; Playwright.
**Source:** blueprint-v2 `composer`; reading conclusion #1 (**new design work, no reference
implementation — unbuilt in the shipped app**, map row 30).

**A-164 — Expand in place: the five-tap chain, closable.** *"I can open a card all the way and then
close it back down, and nothing ever navigates away underneath me."* **Pass:** six taps on the same
card cycle open→open→open→open→open→closed; the sixth tap returns exactly to the collapsed state;
where the browser/engine supports the View Transitions API, the browser morphs the box itself
rather than a re-draw. **Rule:** design-build-2 §11. **Verify:** Simulator + Expo Go; Playwright.
**Source:** blueprint-v2 `expand`; reading conclusion #2 (no reference implementation in the old
blueprint — **new, unbuilt in the shipped app**).

**A-165 — Shared element: card becomes screen, and back.** *"Tapping the blood test card grows it
into the report table, keeping its shape and position — and tapping back shrinks it right back to
where it was."* **Pass:** the tapped card's position, shape, type and identity persist through the
transition in both directions; the same wiring on Home lands on the real report table, not a
mocked-up detail. **Rule:** design-build-2 §12. **Verify:** Simulator + Expo Go; frame-time trace
under A-005's budget in both directions. **Source:** blueprint-v2 `shared`; reading conclusion #2
(**genuinely new, unbuilt in the shipped app** — "no shared-element transition anywhere in the
blueprint's own code").

**A-166 — Sheet: real drag, velocity-aware dismissal.** *"I can drag a sheet down to dismiss it, and
a quick flick dismisses it faster than a slow drag."* **Pass:** a pointer-drag handle with a grab
affordance; dragging past a threshold or flicking above a measured velocity dismisses; a short
drag springs back on `sheet.enter`; the backdrop dims/blurs and tapping it also dismisses. **Rule:**
design-build-2 §20. **Verify:** Simulator + Expo Go; Playwright pointer-simulation test asserting
both the threshold and the velocity dismissal paths. **Source:** blueprint-v2 `sheet`; design-build-2
-map §3 ("neither [`Sheet`/`ActionSheet`] has a drag handle, interactive drag, or velocity-aware
dismissal" — **fails today**).

**A-167 — Loading/empty/error: one primitive each.** *"Every loading, empty or error screen in the
app looks and sounds the same, not like twenty different screens improvising."* **Pass:** one shared
`LoadingState` (orb + one in-place status line + shimmer, prose like "Looking through your recent
results…"), one shared `EmptyState` (why/what/next), one shared `ErrorState` (calm, "Try again"
that genuinely retries) — used everywhere, not per-screen bespoke copy or six different rejection
strings for the same underlying condition. **Rule:** design-build-2 §21–23. **Verify:** code
inspection: a grep for ad hoc loading/error copy outside the three primitives returns nothing;
Simulator + Expo Go. **Source:** blueprint-v2 `states`; design-build-2-map §3 ("four places do
pieces of one job"); audit §7.1 ("six different hand-written strings for the one condition 'the
terminal event never came'" — **fails today**).

**A-168 — Press feedback everywhere.** *"Every tappable thing responds instantly to my touch."*
**Pass:** every interactive surface scales to `scale.press` (~0.985) over ~100ms on press-down and
springs back on release, with a haptic on native; no tappable element in the app lacks this.
**Rule:** design-build-2 §7. **Verify:** Playwright: sample N interactive elements per screen, assert
each has the press transition; Simulator + Expo Go for haptic. **Source:** design-build-2 §7;
design-build-2-map §3 ("Applied inconsistently; no brightness change" — **partially fails today**).

**A-169 — Card enter and stagger.** *"Cards arrive settling into place, not popping in all at
once."* **Pass:** every card enters via `card.enter` (fade + slight upward translate + blur
resolve), staggered by list density (denser lists stagger faster, per the measured 80–300ms range);
never every card independently with excessive motion. **Rule:** design-build-2 §6. **Verify:**
Playwright frame trace per screen; A-005 budget applies. **Source:** design-build-2 §6; reading
conclusion #7 ("list density predicts stagger speed, empirically").

**A-170 — Reduced motion: state visible, movement gone.** *"With reduced motion on, I still see
everything change — I just don't see it move."* **Pass:** with `prefers-reduced-motion: reduce`, all
positional/transform animation is removed; state changes remain visible as instant opacity/colour
changes; nothing is hidden or broken. **Rule:** design-build-2 §25. **Verify:** Playwright walk of
every screen with `prefers-reduced-motion: reduce` forced, both engines; Simulator + Expo Go with
the OS setting on. **Source:** design-build-2 §25; blueprint-v2's own `@media
(prefers-reduced-motion:reduce)` rule (all `.phone` animation/transition off) and its `RM()` JS flag
that makes every `sleep()` resolve instantly.

**A-171 — Type scale matches the token set (no sub-floor caption).** *"Nothing on screen is smaller
than I can comfortably read."* **Pass:** no caption renders under the brief's 12.5px floor (or the
patient-density 20px body / 56px target rule where that density applies — A-022); section titles
render within the allowed 300–600 weight range, not 700. **Rule:** design-build-2 §2 type scale;
CLAUDE.md patient-mode rule ("20pt body, 56pt targets, 7:1 contrast"). **Verify:** a measured-size
Playwright script across every screen (the audit's own methodology); Simulator + Expo Go. **Source:**
audit §4.4, D-21 (**fails today**: captions at 11–11.5px; section titles at weight 700; Welcome
tagline 31.2px/w500 vs the 33px/300 rule).

**A-172 — Accessibility: VoiceOver labels.** *"Every control has a spoken label a screen reader can
read."* **Pass:** every interactive element carries an `accessibilityLabel`/`aria-label` describing
its action, not its icon; every card that speaks has a spoken-equal accessibility label. **Rule:**
CLAUDE.md patient-mode rule ("every card has a spoken twin"); feed-spec §6 ("Every card has an
`accessibilityLabel` equal to its spoken script"). **Verify:** an automated accessibility audit
(`a11y.spec.ts`, already exists per build-spec §10) extended to every new screen; a manual VoiceOver
walk in Simulator/Expo Go. **Source:** feed-spec §6; build-spec §10.

**A-173 — Accessibility: focus order.** *"Tabbing/swiping through a screen with VoiceOver follows
the visual reading order."* **Pass:** focus order matches visual order on every screen; opening a
sheet moves focus to its heading, closing it returns focus to the control that opened it. **Rule:**
build-spec §10 ("on `sheet` open, move focus to the sheet's heading… standard modal focus-trap
discipline, not yet present in the blueprint's own reference JS"). **Verify:** manual VoiceOver walk;
automated focus-order assertion where tooling allows. **Source:** build-spec §10 (**unbuilt today** —
"the real implementation must add it rather than copy the blueprint verbatim").

**A-174 — Accessibility: contrast measured on the dark palette.** *"Text stays readable against the
moving background, not just against the card behind it."* **Pass:** text-on-glass-on-gradient
contrast is measured against the *darkest* point of the moving background gradient (not just the
glass fill), and meets ≥4.5:1 (or the stricter 7:1 in patient density per the older design-system's
own warning). **Rule:** build-spec §10 ("a three-layer contrast problem… must be checked against the
worst-case composite, which a static Figma comp would not catch"); the older `design-system.md` §5's
explicit warning against glass-on-gradient contrast, raised again independently and still
**unresolved** under the newer dark visual language (product-spec §6, "Where the sources disagree,"
item 4). **Verify:** an automated contrast-check test (`web/tests/e2e/a11y.spec.ts`, PROPOSED
extension per build-spec §10) computing the composite colour at the gradient's darkest stop.
**Source:** build-spec §10; product-spec §6.

**A-175 — Performance: measured frame times on every animated path.** *"Every animation in the app
runs smoothly, measured, not assumed."* **Pass:** every animated path has a Playwright/native trace
with no frame over 32ms on the reference Mac / an iPhone 12-class device (A-005); no simultaneous
`backdrop-filter` layer count exceeds what the viewport actually shows (off-screen cards use a plain
translucent fill, no blur). **Rule:** design-build-2 §3 checklist; mobile-architecture §4 ("60fps on
an iPhone 12 class device is the bar — measured, not asserted"). **Verify:** the frame-time harness
(design-build-2 §4 step 5) run in CI (Chromium) and locally (WebKit); Simulator + Expo Go with
Instruments/React Native perf overlay. **Source:** design-build-2 §3, §25; build-spec §10 (the
`backdrop-filter` cap is **PROPOSED, unbuilt** today).

**A-176 — Performance: startup time.** *"The app opens quickly, cached content first, no
spinner."* **Pass:** an offline/cold launch shows the last cached content immediately, with no
spinner, per feed-spec's own acceptance line applied app-wide. **Rule:** feed-spec §9 ("Offline
launch shows the last cached feed with no spinner"). **Verify:** Simulator + Expo Go in airplane
mode from a cold start. **Source:** feed-spec §9.

**A-177 — Performance: no animation off-screen.** *"Scrolling past a card that's still 'loading'
below the fold doesn't cost me anything."* **Pass:** no animation runs on an element outside the
visible viewport; verified rather than assumed, since browser skip-work behaviour for off-screen
elements is not guaranteed. **Rule:** design-build-2 §25; build-spec §10. **Verify:** a Playwright
trace scrolling past off-screen animated elements, asserting no animation frames are attributed to
them. **Source:** design-build-2 §25; build-spec §10 ("not guaranteed" — explicit caution against
assuming this for free).

**A-178 — Responsive: phone first.** *"On my phone, every screen fits and reads exactly like the
reference."* **Pass:** every capture at 390×844 matches the blueprint-v2 frame's structure and
hierarchy. **Rule:** design-build-2 §26. **Verify:** Simulator + Expo Go; Playwright capture at
390×844. **Source:** design-build-2 §26; design-build-2 §3 checklist.

**A-179 — Responsive: tablet composition.** *"On a wider screen, the same hierarchy holds — it
doesn't just stretch."* **Pass:** at 1280×900 (or a tablet breakpoint), cards keep their proportions
and hierarchy; columns are sensible, not a stretched phone layout. **Rule:** design-build-2 §26.
**Verify:** Playwright capture at 1280×900; Simulator on an iPad-class device if in scope (to be
specified by the owner whether iPad is in scope for this gate). **Source:** design-build-2 §26,
§3 checklist.

---

## 11. Languages

**A-180 — Every string exists in en/ms/zh.** *"I can read and hear everything in English, Malay or
Chinese, and it says the same thing."* **Pass:** every patient-facing string tagged `@patient` in
`web/src/strings/{en,ms,zh}.ts` has a non-empty, reviewed entry in all three catalogues, held to the
same table by `make language`. **Rule:** plain-words §6. **Verify:** `make language` in CI; Simulator
+ Expo Go walk in each of the three languages. **Source:** plain-words §6; product-spec §6
("Three ship today — English, Malay, Chinese — with every catalogue held to the same table by `make
language`").

**A-181 — Caregiver twins for every new line.** *"Every sentence written for me has a matching
sentence written for Mei about me."* **Pass:** every new patient-facing string added under this gate
has a corresponding caregiver-voiced twin, checked as part of the same review as the patient line.
**Rule:** design-build-2 §3 checklist ("Caregiver twin for every new line"). **Verify:** a lint/
review step asserting no new `@patient` string ships without a paired caregiver string. **Source:**
design-build-2 §3.

**A-182 — Plain-words and language gates at zero.** *"Nothing I read has failed the plain-words
check or is missing a translation."* **Pass:** `make plain-words` and `make language` both return
zero failures against the full string set at gate time. **Rule:** *"Every string the patient sees or
hears passes `docs/plain-words.md`"* (CLAUDE.md, cited product-spec §5). **Verify:** CI run of both
make targets, zero exit code, on the exact commit proposed for the signed build. **Source:**
product-spec §5, §6; design-build-2 §3.

**A-183 — Hokkien and Tamil: voice-only, correctly scoped.** *"Where Nura speaks Hokkien or Tamil,
it's voice, not a written screen in that language."* **Pass:** Hokkien/Tamil appear only as spoken
output where enabled, never as an unfinished written-language screen. **Rule:** deferred scope,
explicitly named (product-spec §6, "Hokkien and Tamil are voice-only, deferred to 'T2'"). **Verify:**
code inspection: no written-language catalogue exists for Hokkien/Tamil that the UI could
accidentally render. **Source:** product-spec §6 (E11-04, E15-05).

**A-184 — Country pack completeness (MY, SG).** *"Every safety-relevant fact — the ambulance
number, the drug register — is correct for my country automatically."* **Pass:** for each shipped
country pack (MY, SG), the emergency number, licensed drug register, currency, allow-listed
publishers, ID format and residency region are all correct and covered by a test that fails when the
pack is incomplete. **Rule:** build-spec, "Owner decision 2026-09-22: ASEAN-ready by configuration"
("Every pack value that can harm a person if wrong… is covered by a test that fails when the pack is
incomplete"). **Verify:** backend conformance test per country pack. **Source:** build-spec, ASEAN
decision; product-spec §2 ("Decided, partly built" — package 24, **Not started** as a first-class
concept, though the underlying region facts already work for MY/SG).

## 12. The evaluation set

**A-185 — The owner's own papers and questions, with expected answers.** *"Nura is tested against
my actual papers and the actual questions I'd ask, not a synthetic sample."* **Pass:** an evaluation
set exists comprising the owner's own (or owner-approved redacted) papers, paired with real
questions and their expected answers, graded against a defined rubric. **Rule:** ADR 0019 point 16
("the evaluation set exists before the loop is called magical… the owner's own papers and questions
with expected answers"). **Verify:** the eval harness runs against this set and produces a graded
report. **Source:** ADR 0019 point 16; audit §7.2 ("Evaluation: none… every LLM test is a per-file
canned `FakeClient` asserting exact strings" — **fails today**, no such set exists).

**A-186 — The pass-rate gate.** *"There's a number that says how often Nura gets it right, and the
signed build waits for that number to clear a bar the owner has actually set."* **Pass:** the
evaluation set produces a measured pass rate; the owner has stated the minimum acceptable rate; the
signed build does not proceed below it. **Rule:** A-005 (no asserted numbers) — this document cannot
invent the owner's threshold. **Verify:** the eval harness's own report, compared against the
owner-set minimum. **Source:** ADR 0019 point 16 ("a pass rate reported on every change"); the
minimum itself is **(to be specified by the owner)** — no source states a number.

**A-187 — Runs on every PR.** *"Every proposed change is checked against the same evaluation set
before it merges."* **Pass:** the eval harness runs as part of CI on every PR touching extraction,
Ask, the Analyst, or the plain-words/safety gates; its pass rate is visible in the PR's own checks,
not a manual side-run. **Rule:** ADR 0019 point 16. **Verify:** CI configuration inspection; a PR
that changes `ask_agent.py` or `claude_extract.py` and confirms the eval job ran and reported.
**Source:** ADR 0019 point 16; design-build-2 §4 step 12 ("a graded evaluation set for Ask and
intake… the eval pass rate reported on every PR" — **fails today**, no eval target exists in the
Makefile or CI per audit §7.2).

---

## 13. The sign-off sheet

One row per section of this document, ticked before step 6 of ADR 0019's build order. A section is
**not** ticked until every item within it is independently Verified-in-Simulator **and**
Verified-in-Expo-Go **and** covered by an e2e test **and** owner-checked — per A-002, no partial
credit across engines.

| § | Section | Item range | Verified-in-Simulator | Verified-in-Expo-Go | e2e | Owner-checked |
|---|---|---|---|---|---|---|
| 0 | Definitions | A-001–A-009 | n/a (definitional) | n/a | n/a | ☐ |
| 1 | Arrive & set up | A-010–A-030 | ☐ | ☐ | ☐ | ☐ |
| 2 | Papers | A-031–A-062 | ☐ | ☐ | ☐ | ☐ |
| 3 | The Health Graph & Home | A-063–A-073 | ☐ | ☐ | ☐ | ☐ |
| 4 | Ask | A-074–A-090 | ☐ | ☐ | ☐ | ☐ |
| 5 | Medicines | A-091–A-106 | ☐ | ☐ | ☐ | ☐ |
| 6 | Insurance and visits/costs | A-107–A-117 | ☐ | ☐ | ☐ | ☐ |
| 7 | Feed | A-118–A-130 | ☐ | ☐ | ☐ | ☐ |
| 8 | Not well / Connect / Mei / Profile | A-131–A-142 | ☐ | ☐ | ☐ | ☐ |
| 9 | The engine and safety | A-143–A-157 | ☐ | ☐ | ☐ | ☐ |
| 10 | Experience quality | A-158–A-179 | ☐ | ☐ | ☐ | ☐ |
| 11 | Languages | A-180–A-184 | ☐ | ☐ | ☐ | ☐ |
| 12 | The evaluation set | A-185–A-187 | n/a (backend/CI) | n/a | ☐ | ☐ |

**The gate.** ADR 0019's Consequences require every Tier 1, 2 **and** 3 moment, the register path,
papers, Ask, medicines, insurance, feed, Health, not-well, Connect, Mei, Profile, the four hard
gates, whose-paper and duplicates, reduced motion, accessibility, offline, and the evaluation set at
an owner-accepted pass rate — all thirteen rows above ticked in full — before Apple Developer + EAS
work may begin. No builder starts step 6 on a partially-ticked sheet.

---

## Item counts and open items, for the record

This document defines **187 numbered acceptance items (A-001–A-187)** across 13 sections, plus one
defect-closure table (§9) folding in the audit's remaining D-numbered defects not already named
against a specific item, and one 33-row scene table (§10, A-158) covering every blueprint-v2 scene.

**Items marked "(to be specified by the owner)"** — thresholds or behaviours no source states, left
open rather than invented: A-014 (resend rate cap), A-019 (exact decline-path UI), A-022 (exact
density-selection UI), A-046 is sourced but A-096/A-104/A-110/A-114-adjacent detail gaps are noted
inline; explicitly: A-019, A-022, A-046 partially, A-079 (second-ambiguity fallback), A-096 (file-
picker medicine entry), A-104 (label-with-pharmacy-detail as its own behaviour), A-110 (typed-policy
path), A-179 (whether iPad is in scope), A-184's exact pass-rate number is covered by A-186, and
A-186 itself (the minimum acceptable evaluation pass rate).
