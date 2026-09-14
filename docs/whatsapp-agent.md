# The WhatsApp agent

How to put the assistant inside WhatsApp so it understands what's happening there, without pretending it can read what it can't.

---

## 1. What the agent can see

WhatsApp gives a business three windows into a person's world, and nothing more:

- **A one-to-one chat** between a person and the agent's number: everything sent there.
- **A group the agent's number is a member of**: everything posted there. Group membership through the Business Platform is newer and still rolling out; confirm availability in Malaysia and Singapore before promising it, and design the fallback below.
- **Forwards**: anything a person chooses to send on to the agent.

It cannot see a person's other chats. The unofficial route, linking the agent as a "companion device" to someone's own account through automation libraries, reads everything on that account; it breaks WhatsApp's terms, gets numbers banned without notice, and would be indefensible for a health product under PDPA. Don't build on it.

So "the context of everything happening on WhatsApp" is achieved by putting the health conversation where the agent is: one family group, and a private thread with each person.

---

## 2. The setup

**One business number** per country, verified with Meta, through a business solution provider (Twilio, 360dialog, Gupshup). Display name "Nura"; profile explains in one line what it keeps.

**A private thread with each key holder.** The sender's phone number is their identity, so scope enforcement is automatic: Mei's number resolves to Mei's key, and the agent answers her inside it. The patient's own thread is his Level 0 app: the morning card, the feeling words, the visit card, the family notes.

**A dedicated family health group.** "Pa's health", created by the chief, with the agent's number as a member and a pinned message: *"The assistant reads this group. It keeps only health information about Pa. Start a message with 'ignore' to keep it out."* Everything the family already says to each other about his health lands here, and the agent turns it into the record.

**Fallback if groups aren't supported yet:** the family keeps its own group and forwards to the agent's number; the agent replies in the private thread of whoever forwarded.

---

## 3. Platform rules that shape the design

- **The 24-hour window.** The agent can reply freely for 24 hours after a person's last message. Outside that, it can only send pre-approved templates. So the morning card, the visit card and the nudges are templates with variable slots, approved once; replies to anything a person says are free-form.
- **Opt-in.** Each person must have agreed to receive messages; the invite link and the claim flow are where that consent is captured.
- **Conversation pricing** by category (utility, marketing, authentication, service). Almost everything here is utility or service; nothing is marketing.
- **Media.** Photos, PDFs and voice notes arrive as media IDs to download within a time limit; the ingestion pipeline pulls them immediately.
- **Interactive messages.** Buttons and lists are supported and make "Taken", "Given", "OK" one tap.

---

## 4. What happens in the group

Every message is classified on arrival into one of four kinds, and only two are kept.

| Kind | Example | What the agent does |
|---|---|---|
| **Document** | A photo of a receipt, a PDF result, a screenshot | Ingests through the normal review card; replies in-thread: "Kidney check, 9 Sep, filed. Potassium a bit high, added for Thursday." |
| **Health event** | "Took Pa to Dr Tan, he said stop the aspirin and come back in 2 weeks" | Extracts the event and any medicine change as a *proposal*, and asks the poster to confirm: "Did I get this right? Aspirin stopped, follow-up in two weeks." A tap confirms. |
| **Coordination** | "I can drive Thursday" | Updates the roster if it maps to a task; otherwise ignored |
| **Everything else** | Photos of the grandkids, jokes, plans | Not stored, not indexed, not summarised |

The agent posts in the group only when it has something to give back: a filed document, a confirmation request, a red flag, the Sunday clip, and a short digest when asked ("@assistant what happened this week"). It never posts nudges to the group; those go to the person's private thread.

---

## 5. Conversation design, by person

**Pa (private thread).** Voice notes in his language in both directions. He can speak: "When did I last see Dr Tan?" or send a photo of a pill. Cards arrive as a short line plus a button. Two ignored messages and the next goes to the roster, not to him.

**Ash, the chief.** Anything: "Has his potassium ever been high?", "Draft the reorder for the sugar tablets", "Send Pa the kidney explainer as a voice note", "Who has keys?" The agent answers with provenance and confirms before acting.

**Mei, caregiver.** Same, inside her scope. Asking for something outside it gets the same polite, visible refusal as in the app.

**Siti, helper.** Bahasa Indonesia. A list at 7 am with pill descriptions and two buttons per dose; "Pak tidak sehat" opens the not-feeling-well flow on the family's side.

**The clinic.** Not on WhatsApp. The doctor gets a link.

---

## 6. Architecture

Inbound webhook from the provider → media fetched and stored under the profile → sender resolved to a Person and their keys → group resolved to its profile → classifier → ingestion or agent turn.

The agent turn runs on the same runtime as the app: the profile's memory within the sender's scope, the State, the tools (ask, find, act, reorder, questions). Free-form replies go out through the send API; anything proactive goes out as a template with slots, scheduled by the delivery layer under the same caps as the app.

Every inbound message that is kept becomes an artefact with provenance ("Mei, family group, Tue 14:02"). Every outbound message is logged with the State it was rendered from. Everything the agent kept from a group is visible to the profile owner in the audit, the same as any read.

---

## 7. Guardrails

- The agent keeps health information about the profile owner only. Other people's health mentions in the group ("Mum's knee is bad too") are not stored unless Mum has her own profile and the poster holds a key to it.
- "ignore" at the start of a message is honoured absolutely — except that red-flag words are read first, before "ignore" and before the WhatsApp agreement: "ignore that, he fell" is still a fall. From anyone who holds a key on the profile, a red-flag word raises the flag; on a profile whose patient has not agreed to WhatsApp the flag is raised on the word alone (the message is not kept), escalated through the family's app rather than to anyone's WhatsApp, and the sender gets one fixed line. An unknown number still gets only its fixed reply and leaves no trace.
- Nothing from a group changes the record without the poster's confirmation tap, except a document that goes through the review card.
- Red flags posted by anyone ("he's very breathless") trigger the escalation ladder immediately (E11-06: the roster first, never capped, never quiet) and the agent says so in the thread, naming only the people the ladder actually reached.
- The boundary line is in the agent's profile and in its first reply to any new person.
- Retention for unclassified media: deleted within days.

---

## 8. Build steps

1. Choose the provider, register the business, verify the number, write and submit the templates (morning card, visit card, reorder, nudge, digest, red flag). Two to four weeks of lead time.
2. Webhook, media pipeline, identity resolution, and the classifier. This reuses the capture layer entirely.
3. Private threads first: the patient's Level 0 experience and the chief's ask-and-act.
4. The family group, if supported in your markets; otherwise forwarding with in-thread replies.
5. Confirmation flow for health events, the weekly digest, and the audit view.

---

## 9. In one line

Put the health conversation where the agent is, one group and one thread per person, keep only what is about the patient and only with the poster's tap, and the agent will know what's happening on WhatsApp without ever reading anyone's WhatsApp.
