# The experience for the person it's for

Everything designed so far is the system. This is what the elderly patient actually meets, and the rule that keeps it from becoming exhaustive: **he never sees features. He sees five moments.**

---

## 1. Who we're designing for, honestly

A 74-year-old in Penang. Reading glasses not always on. Hears a voice better than he reads a line. Taps with a thumb, doesn't swipe, doesn't long-press, doesn't drag. Has never set a password he remembers. Uses WhatsApp every day because his children are on it. Distrusts anything that looks like it's selling. Will abandon anything that makes him feel slow, watched or scolded. Wants to be able to answer his doctor's questions and not be a burden to his children.

That produces six constraints that outrank every feature:

1. **One thing at a time.** One card visible, one action on it. The next card only after the first is done or dismissed.
2. **Same shape every day.** The layout never changes. New content arrives in the same slots; new patterns never do.
3. **Voice both ways.** Every card has a spoken twin; he can talk instead of tap. Captions on everything spoken.
4. **Nothing to resolve.** No error he has to fix, no setting he has to find, no password, no typing. If the system doesn't understand a photo, it asks the caregiver, not him.
5. **Presence, not surveillance.** His children appear as people in the same feed, not as a monitoring dashboard.
6. **Dignity.** Never a red number, never a missed-streak, never "you forgot". The number on his Me tab only goes up.

---

## 2. The five moments

This is the whole app from his side. Nothing else needs to exist for him.

| Moment | When | What he sees | What he does |
|---|---|---|---|
| **Morning** | With breakfast | One card: the tablet, the pill picture, "for your blood pressure". | Taps Taken. Hears "Ash can see this." |
| **A feeling** | After a change, at most once a day | Five plain words under the card. | Taps one, answers one question, or taps Fine today. |
| **A visit** | Three days before, the day of, the day after | What it's for and what to bring; the questions on one card; then what the doctor said, in his words. | Listens. Shows the card to the doctor. |
| **Something for him** | Once or twice a day | One thing made for him: a twenty-second explainer, a note from Mei with a photo, his sugar in one sentence. | Watches, or ignores it. Nothing happens if he ignores it. |
| **Not feeling well** | When needed | One coral button, always in the same place. | Says what's wrong. Gets told what to do now. Family told. |

Medicines, records, family, money, insurance letters, second opinions, navigation: those exist in the system and in his caregiver's app. They reach him only as one of these five moments, or not at all.

---

## 3. Four levels of surface

The app has one design and four amounts of it. The caregiver sets the level; the system suggests moving up only when he shows he's ready, and never moves him up on its own.

**Level 0 — WhatsApp only.** No app installed. The morning card, the feeling words, the visit card and the family notes arrive as messages and voice notes. He replies "OK" or taps a button in the message. This is the right level for an old Android, patchy data, or anyone who won't install anything. It is a complete experience, not a fallback.

**Level 1 — one screen.** The app opens on Today and there is nowhere else to go. Top: time and the one thing. Middle: the feeling words when relevant, then one or two things for him. Bottom: the coral button. A microphone on the top card for questions. No tabs.

**Level 2 — three tabs.** Today, Ask, Me. Ask is the big microphone. Me is the number that only goes up, the emergency card, and his family. This is the reduced app already designed.

**Level 3 — the full app.** Chips on Today for Medicines, Records, Visits, Family. For patients who manage their own care, and for caregivers looking at their own profile.

Most elderly patients should start at Level 0 or 1. The measure of success is not that he climbs; it's that the level he's on keeps working.

---

## 4. What the caregiver holds on his behalf

His surface has settings, and they belong to whoever holds the chief key: level, language and dialect, text size, voice speed, quiet hours, how many things a day, whether the feeling cloud is on, what he's shown from money and insurance (usually nothing). She sees exactly what he sees before it's sent. When the system can't read something he added, it asks her. When he ignores something twice, it goes to her. He is never the one holding the complexity.

---

## 5. The test for anything new

Before any feature reaches the patient's surface, it has to pass all four:

- Can it be one card with one action?
- Does it arrive as one of the five moments?
- Does it work as a voice note on WhatsApp?
- If he ignores it, does nothing bad happen to him?

If any answer is no, it belongs to the caregiver's app, the system, or nowhere.

---

## 6. What this means for the build

The patient app is small. Level 0 is the WhatsApp service and needs no native code. Level 1 is one scrolling screen, the feeling strip, the not-feeling-well flow, the emergency card and the microphone; it should run inside Assistive Access. The rest of the native work — the switcher, the sheets, the caregiver views — is for the person who is not elderly.

So the honest answer to "is it too exhaustive" is: the system is large, and it should be; the patient's experience is five moments, and it must never be more.
