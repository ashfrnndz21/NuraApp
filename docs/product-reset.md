# Product reset — the whole flow, reconsidered

A step back over everything designed so far: what was wrong, what the real model is, and how the app should flow from the moment someone installs it.

---

## 1. What went wrong

**A hardcoded character.** Every screen assumed "Pa" and "Ash". A real person registers as themselves. The patient, the caregiver, the helper and the clinic are relationships to a health record, not kinds of user.

**Caregiver-first setup.** Onboarding started on the caregiver's phone and built the parent's record. Many people will arrive alone: a 58-year-old managing her own diabetes, a son whose father already has the app, a daughter invited by her brother. One door doesn't fit.

**Two apps in one.** "Pa mode" and "Ash mode" were drawn as separate personas. They should be one app, one account, and a switcher between the profiles a person owns or holds keys to. Density and language are settings on the profile, not a different product.

**Front-loaded onboarding.** A fifteen-minute shoebox session on day zero is right for an organised caregiver and wrong for everyone else. First value has to land in three minutes; the record grows from there.

**Screens for every feature.** Fourteen modules became fourteen places to go. The reduced surface (three tabs, one thing, two cards, five chips) is the product. The rest are capabilities that answer a question, arrive as a notification, or open as a sheet.

**Consent at the wrong moment.** Consent was drawn at creation. It belongs at the moment the patient claims the profile, and again whenever a key is cut.

---

## 2. The identity model

Three objects, and nothing else in the product depends on who the user "is".

**Person** — an account. Registers with a phone number or email. Has devices, a language, and a display name. A person owns at most one profile (their own) and can hold any number of keys to other profiles.

**Profile** — a health graph: conditions, medicines, providers, coverage, artefacts, events, facts, State. Exactly one owner. Before the owner has claimed it, a steward holds it on a declared basis.

**Key** — the link between a person and a profile that isn't theirs. A key has a role (chief, caregiver, viewer, helper, emergency, clinic), a scope (which categories), a window (always, thirty days, one day), a basis (owner's recorded consent, LPA, medical letter), and an audit trail the owner can read.

Everything else follows: "Pa" is a profile; "Ash" is a person who owns her own profile and holds a chief key to Pa's; "Siti" is a person with a helper key and no profile of her own; a clinic is a person-less key that expires in seventy-two hours.

---

## 3. Registration

**Phone number first.** One-time code by SMS, or by WhatsApp where that's the number's main channel. In Malaysia and Singapore the phone number is the identity people actually use; it also becomes the address for every WhatsApp surface later.

**Email as the alternative**, with a magic link. Sign in with Apple or Google for people who prefer it. Passkeys once the platform supports them cleanly; no passwords for anyone, ever.

**Data minimisation.** No identity card number at registration. A policy number is asked for only when insurance is set up; an IC number only when a guarantee letter requires it, and then held for that purpose.

**Device reality.** A person may have no smartphone (WhatsApp-only profile, driven by someone else's setup), an old Android (the app in simple mode, WhatsApp doing most of the work), or share a caregiver's device (profile switcher with a PIN per profile).

**Registration by proxy.** A caregiver can create a profile for someone before that person has registered. The profile is created against the patient's phone number. The patient receives a voice note in their language: "Your daughter set this up for you. Reply OK and it's yours." Replying OK from that number claims the profile; the patient becomes the owner and the caregiver's stewardship converts into a chief key. If the patient has no phone, the steward declares the basis (verbal consent recorded, or a document) and the profile stays stewarded until someone claims it.

---

## 4. The three doors after registration

The first question is "Who is this for?" and there are three honest answers.

| Door | What happens | Where it ends |
|---|---|---|
| **For me** | Creates my own profile. Language, how I like to read, one starting fact (a condition, a medicine photo, or a document). | My Today screen, three minutes in. |
| **For someone I care for** | Creates a profile against their phone number, or finds the existing one. If it exists, I request a key instead of creating a duplicate. Their language and how they read. One starting fact. Claim message sent to them. | Their Today screen, from my phone, with a "set up by you" banner until they claim it. |
| **I was invited** | Opened from a WhatsApp link. Shows exactly what the key covers and who granted it. Accept. | Their profile in my switcher, scoped to the key. |

Deduplication is by phone number. Two siblings cannot create two "Pa" profiles; the second one is offered a key to the first.

---

## 5. The first three minutes

Minimum context: a name, a language, and one fact from a photo. That's enough to render a Today screen with one real card. The system then grows the record by asking for one thing at a time, when it's convenient: "Next time you're at the cupboard, snap the medicine bag." "Is there a discharge letter from February?" "Who is the heart doctor?"

The full health-biography session stays as an option — "I have the papers, let's do it all now" — for the organised caregiver. It is never the gate.

Setup is rendering, not filing. Each fact added changes what the Today screen shows; the person sees the app become theirs as they go.

---

## 6. One app, many profiles

**The switcher.** At the top of every screen: the profiles this person can see. "Me" if they own one, then names for each key they hold. Switching changes the whole screen: the wash, the language, the density, the tabs.

**Density is a setting.** Simple mode (large text, one action per card, voice-first, no gestures) is a profile setting chosen by the owner or the steward. When the owner opens their own profile they get their setting. When a caregiver opens it through a key they get the caregiver view, which is denser and shows sources.

**Three tabs, always.** Today, Ask, and a third tab that is "Me" for the owner and the person's name for a key holder. Under the third tab: the proud number, the emergency card, medicines, records, visits, family, money, language — as a list of sheets, never as tabs.

**WhatsApp mirrors Today** for any profile whose owner or steward turned it on. The helper role is WhatsApp only.

**Assistive Access.** Simple mode is designed to work inside Apple's Assistive Access and Android's equivalent, so a patient with cognitive or vision needs gets a phone that only shows this app in a big grid.

---

## 7. The journey, end to end

| Moment | The person | The system | Channel |
|---|---|---|---|
| Install and register | Enters a phone number, gets a code | Creates a Person | App |
| Who is this for | Picks a door | Creates, finds or requests a Profile or Key | App |
| First three minutes | Name, language, one photo | Renders the first Today card; queues the first search jobs | App |
| Claim (proxy case) | The patient replies OK | Transfers ownership; converts steward to chief key; records consent | WhatsApp |
| Day 1 | Taps Taken on the one thing | Confirms to the family; starts the count | App or WhatsApp |
| Week 1 | Snaps the bag, a letter, a meal; asks a question | Reconciles medicines; explainers appear; feed learns his format | App, WhatsApp |
| Adding family | Cuts a key: role, scope, window; patient consents | Invites by WhatsApp; audit begins | App, WhatsApp |
| Before a visit | Reads the brief; adds a question | Coverage check, logistics, questions card; feed in visit mode | App, widget, Live Activity |
| The visit | Records with consent | Transcript, summary, proposals, memo | App |
| After a discharge | Snaps the discharge letter | Reconciles medicines; thirty-day watch; escalation to the roster | App, WhatsApp |
| Reorder | Taps "ask to order" or "I have more" | Drafts the pharmacy message; recount photo | App, WhatsApp |
| Ongoing | Opens Today; ignores what isn't for them | State recomputes; feed reranks; format adapts | All |
| Capacity changes | Chief attaches an LPA or letter | Steward basis updated; keys reviewed | App |
| Handover or death | Chief runs the handover | Ownership transfers or profile is sealed; keys expire; export offered | App |
| Leaving | Export or delete | FHIR bundle and PDFs; full deletion in region | App |

---

## 8. Architecture

**Objects.** Person, Profile, Key, Consent, Artifact, Event, Fact (with provenance), State, Card, Job, AuditEntry.

**Services.**
- Identity and keys — registration, OTP, claim and stewardship, key issuance, scope enforcement on every read.
- Ingestion — photo, PDF, handwriting, voice, WhatsApp inbound, device readings; extraction with confidence; review cards.
- Memory — episodic, semantic, working; profile-scoped encryption; in-region storage.
- State — recomputed on every new fact; the single input to everything downstream.
- Reasoning — correlation, flags with provenance, medication checks on a licensed database, visit preparation, memo consolidation.
- Search and jobs — ask about the profile, find in the world, act with confirmation; self-search jobs scheduled from State; allowlisted sources.
- Delivery — feed ranking, card grammar, voice notes, clips, format feedback.
- Channels — app, WhatsApp, share links, widgets and Live Activities, printable pages.
- Consent and audit — every read logged; owner-visible; key windows enforced.

**Boundaries.** Scope enforcement lives in one place, below every service, so a caregiver's question and a clinic's share link go through the same check. Nothing renders without a State. Nothing infers without provenance.

**Platform.** Native mobile for the owner and caregiver experiences (SwiftUI first; Android to follow or a cross-platform shell if the patient cohort is mostly Android, which in Penang it will be). WhatsApp via the Business API from the server. Backend on managed agent infrastructure with the memory primitives mapped to the three stores.

---

## 9. What v1 is

Registration by phone or email; the three doors; proxy setup and claim; the switcher; simple and caregiver density; Today with one thing, two cards, five chips; Ask over the record; Add from photo, PDF, screenshot and WhatsApp; medicines from the bag photo with Taken and reorder; the visit loop; keys with consent and audit; the emergency card; not-feeling-well; WhatsApp mirror; the helper list.

Not v1: care navigation, clips, cost expectation, polypharmacy review, discharge watch, insurance letter tracking. These are the next two tiers and they hang off a record v1 has already built.

---

## 10. Open questions

- Whether a stewarded, unclaimed profile should ever receive nudges directly, or only through the steward.
- Whether email-only registration is worth supporting at launch in MY/SG, or whether phone-first is enough.
- How the clinic key is issued: by the chief from the visit workspace, or by the owner scanning a code at the counter.
- Whether the switcher should show more than three profiles before it needs its own screen.
- Which basis is acceptable for stewardship when the patient cannot consent and there is no LPA.
