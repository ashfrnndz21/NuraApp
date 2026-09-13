# Read-only connectors: WhatsApp, email and the rest

The idea is right: most of a family's health context already exists in messages, inboxes and camera rolls. The question is what can actually be read, and what should be.

---

## 1. What is technically possible

| Source | Read access | Reality |
|---|---|---|
| **Email** (Gmail, Outlook, IMAP) | Yes, read-only scopes exist | The richest source: lab results as PDFs, appointment confirmations, insurer letters, pharmacy invoices, hospital portal notifications. Gmail's restricted scope requires Google's OAuth verification and an annual third-party security assessment; budget three months. |
| **Photos** (camera roll) | Yes, on device | Documents, screenshots of portals, medicine boxes are already in there. On-device document detection means nothing leaves the phone until a person confirms. |
| **Calendar** | Yes, read-only | Appointments, often with the clinic name. Trivial to add, high value for the spine. |
| **Health** (HealthKit, Health Connect) | Yes, read per data type | Readings from cuffs and scales already flowing. |
| **SMS** | Android only, with permission; never on iOS | Malaysian clinics and labs send appointment and result-ready SMS. Useful on the patient's Android; unavailable on iPhone by design. |
| **WhatsApp personal chats** | No | There is no API to read a person's chats. Messages are end-to-end encrypted and the local database is not accessible on iOS. |
| **WhatsApp via the Business API** | Only what is sent to the app's number | Forwards, replies and, where the API supports it, messages in a group the app's number belongs to. Group support in the Business API is recent and limited; verify before promising it. |
| **WhatsApp chat export** | Yes, user-initiated | WhatsApp can export a single chat as a text file with media. A family can export the "Pa's health" group once as a source for the biography session. |
| **Hospital and insurer portals** | Rarely | No consumer APIs in SG or MY today. Screenshots and PDF downloads are the route. |

So: email, photos, calendar and Health can be read. WhatsApp cannot be read; it can only be sent to, forwarded from, exported once, or joined as a group member where the platform allows.

---

## 2. The design: read for documents and events, never for people

A health app reading someone's inbox is a serious thing. The design has to make it obviously safe to the family, to a regulator, and to Google's reviewers.

**Purpose-bound.** The connector reads for one purpose: health documents and health events. Lab results, letters, invoices, confirmations, receipts. It does not read to understand mood, relationships, or anything about anyone other than the profile owner.

**Source allowlists, not full access.** On connection, the system does not ingest the inbox. It scans two years of senders and shows a short list: "These look like health senders: Gleneagles, Pathlab, AIA, Guardian Pharmacy, Dr Tan's clinic. Which may I read?" Only approved senders are read, now and in future. Everything else is never fetched.

**Show before store.** Each candidate item is shown as a capture review card, the same one used for photos: what it is, what was extracted, one Looks-right tap. Nothing enters the record silently.

**Attachments first.** The value is almost entirely in PDFs and images. Message bodies are read only from approved senders and only to date and classify the attachment.

**Third parties stay out.** A family group export contains other people's messages. The importer keeps only messages that carry a document, a reading, or a health event about the profile owner, and drops the rest before storage. Other people's names are not indexed.

**Per-profile, per-connector consent.** Connected by the owner or the chief, in the owner's name, revocable in one tap, with every ingestion in the audit trail. Disconnecting removes the connector's future access and leaves the facts already confirmed.

**Nothing trains anything.** Connected data is used to build this person's record only.

---

## 3. What each connector actually yields

**Email.** Results and reports (the trend layer), appointment confirmations and reminders (the spine), insurer letters and renewals (coverage), pharmacy and clinic invoices (the ledger and the count), portal notifications ("a new result is available", which prompts a screenshot). This is the single biggest reduction in the household's data-entry burden after the bag photo.

**Photos.** A one-time on-device scan for documents, medicine boxes and portal screenshots from the last two years, shown as a grid to confirm. Then an optional watch for new documents, again on device, again confirmed one by one.

**Calendar.** Every event that matches a provider in the directory or a health keyword becomes a candidate appointment on the spine. New events are suggested, never auto-added.

**SMS (Android patient phone).** Clinic reminders and "result ready" messages from allowlisted numbers become appointment and prompt events.

**WhatsApp.** Three patterns, in order of preference: the family forwards to the app's number (already designed); the app's number is added to a dedicated family health group where the platform supports it, and reads only what is posted there; a one-time export of that group as a biography source, filtered as above. The patient's own personal chats are never touched.

---

## 4. What is never read

Personal chats. Messages between family members that carry no health document or event. Financial email beyond health invoices. Anything from a sender not on the allowlist. Anyone's data other than the profile owner's. Sentiment, tone or wellbeing inferred from how people write.

The line to hold: the connectors make the record complete; they do not make the app a listener.

---

## 5. Compliance work this creates

- Google OAuth app verification and a third-party security assessment for Gmail restricted scopes; Microsoft app registration for Graph mail scopes. Start in week one; both gate launch.
- A separate consent screen per connector, in the owner's language, with the allowlist visible, and a PDPA record of it.
- Data map entries for each connector; retention rules for fetched-but-unconfirmed items (deleted within days).
- App Store privacy labels updated for email and photos access; Apple will ask why a health app reads mail, and the allowlist design is the answer.

---

## 6. Build order

1. Photos on-device scan and Calendar. Cheap, private, high yield, no external review.
2. Email with sender allowlists, starting with Outlook and IMAP while Google verification runs.
3. WhatsApp forwarding hardened, then a dedicated family group via the Business API if supported.
4. Android SMS on the patient's phone.
5. Chat export import as a biography source.

Each connector adds to the same capture layer and lands in the same review card, so the person's experience never changes: something was found, here is what it says, tap if it's right.
