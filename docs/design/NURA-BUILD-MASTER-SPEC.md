# Nura — Build Master Specification

**Status:** Binding implementation brief  
**Product:** Nura  
**Primary platform:** iOS / React Native + Expo  
**Purpose:** Production-quality consumer health application

---

## 0. Executive Build Directive

Nura must be built as a **native-feeling, AI-native consumer health application**, not as a collection of static screens.

The governing interaction model is:

```text
AI understands
      ↓
AI prioritizes
      ↓
AI surfaces
      ↓
user explores
      ↓
AI explains
      ↓
user acts
```

Nura should feel like a **health chief of staff for one person and the family around them**: quiet most days, but highly prepared when something important happens.

The implementation must reproduce the **experience philosophy**, not merely the visible screens.

Optimize for:

1. interaction quality
2. contextual intelligence
3. visual hierarchy
4. motion quality
5. typography and spacing
6. responsiveness
7. accessibility
8. safety and trust
9. technical architecture

The finished product must feel like a premium consumer product designed and engineered by an experienced team — **not an AI-generated app**.

---

# 1. Product Experience

Nura is not:

- a SaaS dashboard
- an enterprise application
- a CRUD application
- a chatbot wrapped in a UI
- a collection of cards
- a conventional health analytics dashboard

Nura is an intelligent companion that understands what matters and brings it to the user.

The user should rarely need to ask:

> “Where do I go to find this?”

Instead, Nura should proactively surface relevant information in context.

**Minimize navigation. Maximize contextual interaction.**

Every experience should answer:

1. What matters to me right now?
2. Why does it matter?
3. What can I do about it?

Use progressive disclosure rather than exposing every available data point.

---

# 2. Product Architecture Principle

Do **not** build Nura as 26 independent screens.

Build one stateful intelligence system that happens to have 26 experiential moments.

```text
                    NURA APP
                       │
              EXPERIENCE LAYER
                       │
                  NURA RUNTIME
                       │
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
     STATE           EVENTS           SAFETY
       │               │                │
       └───────────────┼────────────────┘
                       ↓
                EXISTING BACKEND
                       │
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
     PAPERS         MEDICINES         VISITS
     INSURANCE      FEED              FAMILY
```

The screen is a **projection of application state**, not the source of truth.

A paper arriving should be capable of changing:

- Facts
- State
- Home priority
- Ask Nura context
- Health view
- Visit preparation
- feed/recommendations
- connected medicine context

without duplicating business logic across screens.

---

# 3. Platform & Technology

## Required direction

Use:

- **React Native**
- **Expo**
- **TypeScript**
- **Expo Router**
- **Reanimated 4**
- **React Native Gesture Handler**
- **React Native Skia**
- **Zustand**

Retain the existing FastAPI backend rather than replacing it.

| Layer | Technology | Purpose |
|---|---|---|
| Mobile UI | React Native | Native-feeling product |
| App/build | Expo | Development and release workflow |
| Navigation | Expo Router | App navigation |
| Motion | Reanimated 4 | UI-thread animation |
| Gestures | Gesture Handler | Native-feeling interaction |
| Visual effects | Skia | Orb, ambient lighting, charts, special transitions |
| State | Zustand | Client state |
| Backend | Existing FastAPI | Domain/data/AI services |
| AI runtime | Existing model architecture | Intelligence |
| Build/distribution | EAS later | Physical-device/TestFlight workflow |

### Apple/EAS sequencing

Apple Developer/EAS credentials are **not a prerequisite for the initial build**.

The first development target is the local Expo/iOS Simulator experience.

Only after the core experience is validated should the project move to:

```text
Apple Developer
      ↓
EAS
      ↓
Physical iPhone
      ↓
TestFlight
```

Do not allow signing/distribution setup to block experience development.

---

# 4. Architecture: State First, Screens Second

The interface must be state-driven.

## AI state

```text
IDLE
  ↓
LISTENING
  ↓
THINKING
  ↓
RESPONDING
  ↓
IDLE

ANY STATE → ERROR → IDLE
```

## Card state

```text
COLLAPSED
  ↓
PRESSED
  ↓
EXPANDING
  ↓
EXPANDED
  ↓
INTERACTIVE
  ↓
DISMISSED
```

Loading/error states must be explicit.

## Media state

```text
IDLE
 ↓
LOADING
 ↓
PLAYING
 ↕
PAUSED
 ↓
COMPLETE
```

Transitions between states must be explicit and driven by real events.

---

# 5. Nura Run / Event Runtime

The AI runtime must be event-driven.

Use a consistent event vocabulary:

```text
RUN_STARTED
RUN_FINISHED
RUN_ERROR

TEXT_MESSAGE_START
TEXT_MESSAGE_CONTENT
TEXT_MESSAGE_END

TOOL_CALL_START
TOOL_CALL_ARGS
TOOL_CALL_END
TOOL_CALL_RESULT

STATE_SNAPSHOT
STATE_DELTA
```

The UI must not care whether intelligence came from:

- a live model
- a deterministic service
- a fixture
- search
- a database
- an extraction service

It consumes the same event model.

A conceptual Nura run:

```text
runNura(intent, subject, context)
        ↓
RUN_STARTED
        ↓
tool calls / reasoning
        ↓
STATE_DELTA
        ↓
TEXT_MESSAGE_CONTENT
        ↓
RUN_FINISHED
```

This runtime drives:

- orb state
- loading state
- response rendering
- card state
- state changes
- contextual actions

---

# 6. AI vs Deterministic Logic

AI must not become the authority for safety-critical or permission-sensitive decisions.

## Deterministic system owns

- consent
- permissions
- scopes
- identity matching
- paper ownership
- confirmation status
- confidence thresholds
- source validity
- medicine safety gates
- escalation
- audit
- data residency
- silent-change prevention

## AI owns / assists with

- extraction
- summarization
- explanation
- conversational language
- contextual interpretation
- personalization candidates
- content compression
- narrated analysis
- question generation

**Rules decide. Models assist.**

No model-written pharmacology should silently alter treatment.

---

# 7. Health Data Model

Retain the existing backend concepts:

- Artifacts
- Events
- Facts
- Providers/Appointments
- Policies
- Medicine lines
- Feed items
- Consent
- Audit
- State
- Patterns

Facts should have:

- validity window
- confidence
- source
- confirmation state

Facts are immutable except through supersession.

Review cards may hold proposed/unconfirmed values, but **unconfirmed values must never be presented as confirmed facts**.

Every read/write/share action should be auditable.

---

# 8. Safety & Trust Requirements

These are product requirements, not optional polish.

## Hard vetoes

Nura must not:

- start/stop/change medicine treatment
- state an unconfirmed value as fact
- silently change treatment
- accept a paper without checking whose paper it is
- bypass consent/scopes
- hide the source of a factual health claim

## Paper identity

Before extracted health facts enter the confirmed record:

```text
paper
 ↓
identity extraction
 ↓
match against intended person
 ↓
confidence/review
 ↓
"Is this Pa's report?"
 ↓
user confirmation
 ↓
confirmed Fact
```

A wrong birth year/sex/person must never silently overwrite profile data or influence reference ranges, emergency information, or screening context.

## Ask Nura source grounding

When Nura states a factual health value:

```text
Answer
  ↓
confirmed Fact
  ↓
source Artifact
  ↓
source/provenance shown
```

Never rely on conversational memory alone.

## Audit

Record:

- actor
- action
- object
- timestamp
- source/context where relevant
- consent/scopes where relevant
- user rejection/modification of AI conclusions

---

# 9. Consent, Roles & Residency

Consent must be:

- recorded
- versioned
- revocable

Relevant scopes:

```text
RECORDS
MEDICINES
READINGS
VISITS
FAMILY
MONEY
EMERGENCY
ASK
```

A row must only be readable under the scope written for it.

Support:

- owner
- chief
- caregiver
- scoped grants
- “only me”
- family thread
- duty roster
- audit trail

Health data residency must remain region-aware.

Country-pack direction:

- Singapore
- Malaysia
- future ASEAN packs

Country configuration should determine:

- emergency number
- drug register
- currency
- publishers
- ID format
- privacy wording
- residency region

---

# 10. Visual Language

The binding visual direction is:

- deep indigo/violet environment
- subtle purple-to-warm gradients
- soft radial lighting
- translucent surfaces
- glass-like cards
- large rounded corners
- very soft borders
- low-contrast separation
- generous whitespace
- large editorial typography
- restrained iconography
- subtle glow
- soft depth rather than hard shadows

Emotional qualities:

- premium
- calm
- intelligent
- human
- cinematic
- modern
- slightly futuristic
- trustworthy

Avoid:

- conventional Material Design appearance
- dense dashboards
- excessive borders
- rectangular tables as the primary visual language
- bright saturated buttons
- excessive icons
- aggressive gradients
- excessive glassmorphism
- excessive animation
- “AI gimmick” effects

Visual hierarchy always beats decoration.

---

# 11. Typography

The current product direction uses:

- **Figtree**
- **Instrument Serif** for selective italic/accent treatment

Use typography to establish hierarchy rather than relying on boxes, borders, or icons.

Large headlines should communicate the insight, not the name of the feature.

Prefer:

> “Four numbers to raise with your doctor.”

over:

> “Health Metrics”

---

# 12. Ambient AI Orb

The orb is a persistent visual identity for Nura.

It is **not a character**.

It represents ambient intelligence.

## Orb states

### IDLE

- subtle breathing
- low-frequency glow
- tiny scale oscillation

### LISTENING

- slightly brighter
- expanding halo
- subtle pulse

### THINKING

- more dynamic movement
- internal gradient shifts
- halo expands/contracts

### RESPONDING

- brighter glow
- subtle wave/pulse
- settles back into idle

### ERROR

- subdued change
- no aggressive red unless the safety state genuinely requires it

The orb should feel present without demanding attention.

Skia may be used for the orb and ambient visual field.

---

# 13. Home Experience

Home is a **personalized briefing**, not a dashboard.

Conceptual structure:

```text
Greeting
   ↓
Primary story
   ↓
Primary insight
   ↓
Reminder / secondary action
   ↓
Personalized feed
   ↓
Ask Nura
```

The primary story should feel editorial:

> “Four numbers to raise with your doctor.”

The primary insight card contains:

- contextual label
- date/context
- concise insight
- explanation
- primary CTA

Secondary cards should communicate one thing each.

Home should be **recomposed from current Nura State**, not hard-coded.

---

# 14. Card System

Create one composable Card system with variants:

- insight
- reminder
- video/content
- metric
- recommendation
- document
- AI summary
- action
- alert

Use hierarchy:

### Primary

Large and visually dominant.

### Secondary

Smaller and quieter.

### Tertiary

Minimal surface with stronger typography.

Cards should have:

- large radius
- translucent background
- subtle border
- backdrop blur where supported
- internal spacing
- clear typography

Do not make every card visually identical.

---

# 15. Card Interaction

Cards should feel physical.

## Enter

- fade in
- slight upward translation
- spring/eased movement
- subtle stagger

Conceptual timing:

```text
Primary:   400–600ms
Secondary: 300–450ms
Stagger:    40–100ms
```

Do not animate every card independently with excessive motion.

## Press

```text
scale 1.0 → 0.985
80–120ms
```

Subtly increase surface brightness and provide tactile feedback.

Release with controlled spring physics.

No large bounce.

---

# 16. Progressive Disclosure

Nura must reveal information progressively.

Example:

```text
Blood pressure
148 / 92 today
Above your usual
```

Tap:

```text
weekly chart
 ↓
daily values
 ↓
trend explanation
 ↓
context
 ↓
related information
 ↓
suggested action
```

The user should feel like the **same object is unfolding**, not that they navigated to an unrelated screen.

Where technically appropriate, use shared-element-like transitions.

Do not default to:

```text
fade out → new screen
```

Prefer:

```text
card expands → detail emerges
```

---

# 17. AI Composer

The composer is contextual.

Default:

> “Ask Nura anything”

with:

- microphone
- speak affordance

The composer should expand in place:

```text
compact pill
      ↓
expanded conversational composer
```

Do not automatically turn every interaction into a full-screen chatbot.

---

# 18. Conversational Experience

Nura is not a generic chatbot.

Weak:

> “What is my blood pressure?”

> “Your blood pressure is 148/92.”

Preferred pattern:

> “Your blood pressure has been slightly higher than usual this week.”

Then:

```text
[Explain]
[Show my readings]
[Ask something else]
```

Nura should:

- summarize
- explain
- ask clarifying questions
- recommend next actions
- surface relevant information
- connect related information

Keep responses concise.

---

# 19. Contextual Media / Feed

Personalized clips are editorial content, not generic recommendations.

Every media card should answer:

> **Why am I seeing this?**

Example:

> “Because you take amlodipine.”

Metadata can include:

- source
- duration
- relevant context

Feed ordering should respect the current product rules:

```text
Now
→ Today
→ gate
→ His story
→ Learning
```

Quiet hours:

```text
21:00–07:00
```

No treatment-changing recommendations.

Maximum two new cards/day.

“Not for me” should be remembered.

---

# 20. Health Experience

Health is a deeper information experience, while retaining the same visual language.

Information order:

```text
Insight
 ↓
meaning
 ↓
trend
 ↓
raw data
```

Example:

> “Your week, looked at closely.”

Then:

> “Ready since Monday. Two things changed.”

Then:

- blood pressure trend
- papers
- letters
- prescriptions

Charts must be editorial and minimal.

Avoid:

- dense dashboard charts
- excessive gridlines
- legends everywhere
- multiple colors
- technical axes unless necessary

Prefer:

- thin lines
- one highlighted point
- subtle filled region
- contextual annotations
- large primary number
- plain-language interpretation

---

# 21. Medicines

Medicine UX must be safety-first.

Capabilities include:

- add medicine by photo
- typed entry
- future voice entry
- registry lookup
- class disambiguation
- one-tap “I took it”
- duplicate class detection
- pharmacist sheet
- refill/reorder workflow

If only a medicine class is known:

> “Which statin?”

Do not silently choose.

High-risk medicine doses must come from the label/photo layer.

High-risk classes include:

- anticoagulant
- insulin
- cardiac glycoside
- antimetabolite
- opioid

No model-written pharmacology.

Pharmacist/clinical review remains authoritative.

---

# 22. Papers / Ingestion

The paper journey is a flagship experience.

Required journey:

```text
Add a paper
 ↓
photo/file/multiple files/no papers
 ↓
Nura reads it
 ↓
real extraction stages
 ↓
headline
 ↓
summary rows
 ↓
report table
 ↓
range/context
 ↓
uncertain field review
 ↓
whose paper?
 ↓
confirmation
 ↓
Facts
 ↓
connections to medicines/visits/state
```

Waiting/unconfirmed papers must never have their values presented as facts.

Batch ingestion should provide:

- shared status
- per-paper status
- per-paper uncertainty
- duplicate detection
- identity check

---

# 23. Visits

Visits should produce:

- first-person questions
- driver from family roster
- pre-visit brief
- post-visit memo
- medicine-change question/flag
- follow-up actions

Nura must **never silently change treatment** after a visit.

Unbooked procedure cost estimation is a separate capability and should not block the core visit experience.

---

# 24. Insurance

Insurance should evolve into a structured policy passport.

Target experience:

```text
Policy
 ↓
coverage
 ↓
claims
 ↓
relevant policy lines
 ↓
source
 ↓
action
```

Claims ledger should remain separate and auditable.

The insurer should be available on the emergency card where appropriate.

---

# 25. Not Feeling Well / Emergency

This is a special interaction state.

When the user says they are not feeling well:

- do not show a thinking delay
- do not make the user wait for animation
- switch immediately into urgent context
- preserve the same app frame where possible
- use the red-flag escalation ladder

Red flags bypass quiet hours.

Emergency card must remain available.

Until clinical sign-off exists for the blood-thinner + fall scenario, use the safe ambulance escalation path rather than inventing a more nuanced clinical decision.

---

# 26. Connect / Family

Connect must support:

- scoped access
- role badges
- “Let someone in”
- “See it as Mei”
- family roles
- caregiver access
- audit trail

Mei's Home must use the **same Home template**, recomposed from caregiver context.

Do not create a separate parallel caregiver application.

---

# 27. Navigation

Use five quiet tabs:

```text
Home
Health
Connect
Services
Profile
```

Navigation is infrastructure.

Content is the hero.

Active state should be subtle but obvious.

Avoid oversized navigation.

---

# 28. Bottom Sheets

Prefer sheets over conventional modal dialogs.

Sheets should have:

- drag handle
- spring entrance
- rounded top corners
- backdrop dim/blur
- interactive drag
- velocity-aware dismissal

The sheet should feel physically connected to the underlying content.

---

# 29. Loading / Empty / Error

Never show generic technical language.

### Loading

Instead of:

> Loading...

Use:

> Looking through your recent results...

or:

> Connecting the dots...

or:

> Preparing your weekly summary...

### Empty

Explain:

1. WHY
2. WHAT
3. NEXT ACTION

Example:

> “We don't have any blood pressure readings yet.”

> “Add your first reading.”

### Error

Never expose HTTP/internal implementation errors.

Prefer:

> “We couldn't reach your clinic records right now.”

> [Try again]

---

# 30. Motion System

Create a centralized motion system.

Do not hardcode arbitrary animation values throughout the application.

Conceptual tokens:

```text
motion.fast
motion.standard
motion.slow

spring.gentle
spring.standard
spring.bouncy

fade.enter
fade.exit

scale.press

card.enter
sheet.enter

orb.idle
orb.listening
orb.thinking
orb.responding
```

Every animation must serve one of:

```text
STATE
FEEDBACK
HIERARCHY
ORIENTATION
```

Never animate purely for decoration.

---

# 31. Performance

Target a smooth **60fps** experience.

Avoid:

- unnecessary re-renders
- excessive view complexity
- giant blur layers everywhere
- expensive animation of large surfaces
- continuously running animations when not visible

Animations should run efficiently and preferably on the UI thread where appropriate.

Respect reduced motion.

When reduced motion is enabled:

- remove unnecessary movement
- preserve state changes
- use opacity/color changes where possible

---

# 32. Accessibility

Accessibility is a product requirement.

Maintain:

- strong contrast
- large enough body text
- large touch targets
- no interaction dependent solely on horizontal gestures
- no autoplay as a requirement
- accessible labels for interactive elements
- spoken equivalents for important cards/content
- reduced-motion support

The older-patient experience must remain usable even when the richer cinematic layer is present.

Do not sacrifice comprehension for aesthetics.

---

# 33. Responsive Behaviour

Mobile is primary.

Do not shrink a desktop dashboard into mobile.

For tablet/desktop:

- widen content intelligently
- preserve card proportions
- use larger editorial compositions
- introduce multi-column layouts where appropriate
- preserve the same hierarchy and interaction philosophy

The emotional experience must remain consistent.

---

# 34. Component Architecture

Create reusable primitives:

```text
AppShell
AmbientBackground
BottomNavigation
AIOrb
AIComposer
EditorialHeadline
InsightCard
ReminderCard
MediaCard
MetricCard
TrendCard
DocumentCard
ExpandableCard
BottomSheet
ContextualAction
LoadingState
EmptyState
ErrorState
MotionProvider
NuraSource
NuraAction
NuraAlert
```

Do not duplicate similar UI components.

Build composable primitives.

---

# 35. Suggested Project Structure

```text
/app
  /(tabs)
    home.tsx
    health.tsx
    connect.tsx
    services.tsx
    profile.tsx

  /paper
  /ask
  /medicines
  /visits
  /insurance

/components
  /ambient
  /cards
  /ai
  /motion
  /sheets
  /charts
  /media
  /navigation

/features
  /home
  /papers
  /ask
  /health
  /medicines
  /visits
  /insurance
  /feed
  /connect
  /profile

/lib
  /api
  /ai
  /state
  /safety
  /consent
  /analytics
  /storage

/domain
  /facts
  /artifacts
  /medicines
  /visits
  /policies
  /feed
  /family

/design
  tokens.ts
  motion.ts
  typography.ts
  colors.ts
```

Exact folder names may evolve, but separation of UI, domain, state, AI, and API responsibilities must remain.

---

# 36. Realistic Mock Data

Initially use realistic fixtures.

Never use:

- Lorem ipsum
- John Doe
- meaningless placeholder numbers
- generic fake content

Use believable Nura personas and domain data, including:

- **Pa** — patient/profile owner
- **Mei** — caregiver/chief

Separate:

```text
UI
domain models
mock/fixture data
API layer
```

Real APIs must be replaceable without rewriting UI components.

---

# 37. 26-Scene Experience Blueprint

The final experience should cover:

1. Welcome
2. Sign in
3. Who is this for
4. What is part of your health
5. Add a paper
6. Nura reads it
7. The report table
8. What it means for you
9. Many papers at once
10. What changed in your record
11. Policy passport
12. Add a medicine
13. Medicine registry
14. Everything connected
15. Home
16. Ask Nura
17. Health
18. Health Analyst
19. Medicines
20. Visits and costs
21. Insurance
22. For you
23. Not feeling well
24. Connect
25. Mei's Home
26. Profile

These are **experiences**, not necessarily one-screen-per-scene navigation.

---

# 38. Build Order

Do not implement all 26 scenes shallowly.

## Phase 0 — Foundation

1. Expo/React Native project
2. TypeScript
3. Router
4. Reanimated
5. Gesture Handler
6. Skia
7. Zustand
8. design tokens
9. motion system
10. state/event architecture

## Phase 1 — Home Spike

Build only:

- App shell
- ambient background
- orb
- headline
- primary insight card
- reminder
- feed card
- composer
- expandable card
- bottom sheet

Run this on the iOS Simulator first.

The Home spike determines whether the chosen native stack delivers the required experience.

## Phase 2 — Golden Path

Build deeply:

```text
Welcome
 ↓
Who is this for
 ↓
Add paper
 ↓
Nura reads it
 ↓
Report table
 ↓
What it means
 ↓
Home
 ↓
Ask Nura
```

This is the first complete vertical slice.

## Phase 3 — Core Health OS

Add:

- Medicines
- Visits
- Insurance
- Health
- Connect
- Mei

## Phase 4 — Advanced Intelligence

Add:

- Analyst
- many-paper queue
- matching engine
- policy passport
- everything connected
- personalized feed

## Phase 5 — Safety & Polish

Resolve safety, accessibility, performance, error states, auditability, and real-device testing.

---

# 39. Critical Defects Must Be Resolved Before Scale

The existing product audit identifies four critical areas.

### D0 — Startup/performance

Profile/startup must not freeze the runtime or create unacceptable startup latency.

### D1 — Ask source grounding

Confirmed paper values must be correctly stated and source-grounded.

### D2 — Paper ownership

A paper must not be allowed to silently overwrite the wrong person's profile or facts.

### D3 — Conclusion/audit integrity

When a user rejects or modifies an AI conclusion, the system must preserve an auditable record rather than simply dropping the state.

These are release gates.

---

# 40. Existing Backend Capabilities to Preserve

Do not unnecessarily rebuild existing capabilities.

Existing architecture includes:

- FastAPI
- SQLAlchemy
- Alembic
- UTC-aware timestamps
- ports/adapters
- identity/keys
- consent
- audit
- ingestion
- memory
- state
- reasoning
- visits
- insurance
- medicines
- feed
- recommendation
- safety
- family

The mobile app should become a better experience layer over these capabilities.

---

# 41. AI Model Responsibilities

Starting allocation:

```text
Opus 5
  extraction
  Ask

Sonnet 5
  analyst
  search
  estimate
  draft

Haiku 4.5
  compression
  clip
  narration
```

Run caps and search limits must remain enforced.

Model calls must be audited.

Fixture adapters can be used initially, but fixture behaviour must follow the same event contracts as live AI.

---

# 42. Fixture-to-Live Strategy

Do not build fake UI flows that will later need to be rewritten.

Instead:

```text
UI
 ↓
Nura Runtime
 ↓
Adapter
 ├── Fixture implementation
 └── Live implementation
```

The UI must behave identically regardless of which adapter supplies the result.

This allows experience development before all live AI services are enabled.

---

# 43. Development Workflow

Claude Code or another coding agent should **not** be instructed:

> “Build the entire app.”

Use staged implementation.

### Step 1
Read this document and existing repository architecture.

### Step 2
Produce an interaction map.

### Step 3
Produce component architecture.

### Step 4
Implement design tokens.

### Step 5
Implement motion tokens/state machine.

### Step 6
Implement the app shell.

### Step 7
Implement Home.

### Step 8
Implement expandable interactions.

### Step 9
Implement AI runtime/composer.

### Step 10
Implement Paper golden path.

### Step 11
Connect backend.

### Step 12
Implement secondary experiences.

### Step 13
Run visual/accessibility/performance review.

### Step 14
Only then proceed toward physical-device/TestFlight distribution.

At every stage, the coding agent must preserve this specification and must not replace intended contextual interactions with conventional screens simply because they are easier to implement.

---

# 44. What Must Never Happen

Do not:

- turn Home into a dashboard
- make Ask Nura a generic chatbot
- create dozens of bespoke card components
- use navigation where an expanding card or sheet is appropriate
- use loading spinners with no contextual explanation
- expose raw technical errors
- let AI invent health facts
- let AI silently change treatment
- skip paper identity verification
- show unconfirmed health values as facts
- hardcode animation values everywhere
- overuse blur/glass
- animate everything
- prioritize visual effects over comprehension
- build 20 shallow screens before one excellent vertical slice
- replace real backend behaviour with fake UI-only behaviour
- sacrifice accessibility for cinematic design

---

# 45. Quality Gate

Before accepting any experience, ask:

### Product
- Does it reduce effort?
- Does Nura understand context?
- Does it surface what matters?
- Is the next action obvious?

### Interaction
- Does the object feel continuous?
- Does tapping expand the thing tapped?
- Are transitions contextual?
- Is navigation minimized?

### Motion
- Does motion communicate state?
- Does it feel controlled?
- Does it settle naturally?
- Is there unnecessary animation?

### Visual
- Is hierarchy immediately clear?
- Does it feel premium and calm?
- Is typography doing the work?
- Is the interface visually quiet where it should be?

### Intelligence
- Why is Nura showing this?
- Is the answer grounded in a source?
- Does the experience remember relevant context?
- Is uncertainty visible?

### Safety
- Could an unconfirmed fact be mistaken as confirmed?
- Could the wrong person's data enter the record?
- Could AI accidentally change treatment?
- Is the audit trail preserved?

### Accessibility
- Can an older user understand it?
- Are touch targets sufficient?
- Is contrast sufficient?
- Does reduced motion work?
- Is important content available non-visually?

### Performance
- Does it remain smooth?
- Are expensive effects constrained?
- Are offscreen animations stopped?
- Are unnecessary re-renders avoided?

---

# 46. Final Product Principle

Nura should feel:

```text
CALM
  ↓
INTELLIGENT
  ↓
PERSONAL
  ↓
CONTEXTUAL
  ↓
RESPONSIVE
  ↓
ALIVE
```

The user should feel:

> **The product is working for me.**

Not:

> **I am working the product.**

Before implementing any feature, ask:

> **Can this be made more contextual, more effortless, more understandable, or more human?**

If yes, implement that experience rather than defaulting to a conventional UI pattern.

---

# 47. Final Engineering Directive

Build **deeply, not broadly**.

The first milestone is not “26 screens complete.”

The first milestone is:

```text
Nura opens
   ↓
Nura feels alive
   ↓
Nura understands Pa
   ↓
Pa adds a paper
   ↓
Nura reads it
   ↓
Nura verifies it
   ↓
Nura explains what matters
   ↓
Home recomposes
   ↓
Pa asks Nura
   ↓
Nura answers from confirmed source data
   ↓
Pa can act
```

If this loop feels exceptional, the architecture is working.

Everything else should build outward from this loop.
