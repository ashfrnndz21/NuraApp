# Design direction: warm, visual, Eldora-style

**Status: the owner's direction, set on 2026-09-17. It supersedes the visual parts of
`docs/design-system.md`, `docs/ui-mockup.html` and `docs/ui-mockup-v2.html` where they
disagree. Tokens, accessibility, plain words and every safety rule still bind.**

## Why this exists

The owner tested the app after the D1 design pass (#194) and said it is still *dull*:
no visuals, no imagery, nothing that makes it feel warm or alive. They supplied two
reference designs, and asked that the app look **"visually stunning"** like the second.

The references are screenshots the builders cannot see, so this document describes them
precisely. Treat it as the specification.

## The owner's two decisions

1. **Keep Nura's plum brand, take Eldora's style.** The plum heart logo and plum accent stay.
   Everything else comes from Reference B: warm soft backgrounds, pastel-tinted cards,
   illustrations, the icon grid, rounded cards, generous spacing.
2. **Warm illustrations, not photographs.** One consistent drawn style throughout. Family
   members show their own uploaded photo, or their initials if they have none. No stock photos.

## Reference B: Eldora (the primary reference)

A companion app for seniors and their families. Four phone screens and a row of value tiles.

**The overall feel.** Warm, calm, generous, human. A warm off-white/cream page background.
Cards sit on it with very soft pastel tints and very soft shadows, large radii (about 20–24px),
and plenty of air between them. Nothing is cramped. Illustrations appear on nearly every screen
and do real emotional work: they make the app feel like it is on the person's side.

**1. Welcome.** A large warm image fills the upper half. Over it: a small heart logo, the product
name in a **serif** wordmark, a two-line serif tagline ("Care that connects. Support that
empowers."), and a one-line sub-heading. Below, three small rounded tiles side by side, each an
icon in a soft circle with a one-word title and a short caption (Support / Connect / Empower).
At the bottom, one full-width, solid, dark-accent "Get Started" button, and a quiet text link
"Already have an account? Sign in". For Nura, the image is a **warm illustration**, not a photo.

**2. Home.** Top bar: a menu icon, the serif wordmark centred, a bell icon. Then a greeting in
large type, "Good morning, Anita 👋", with "How are you feeling today?" beneath, and a **warm
illustration** of an elderly couple to the right of the greeting. Then a **"Daily Wellness"** card
in a soft pastel tint: a title, one line of encouragement, a small solid "Check in" button, and a
friendly round emoji-style face on the right. Then a section heading **"What would you like to
do?"** above a **3×2 grid of square tiles**. Each tile has a soft pastel-tinted background of its
own colour, a line icon in the accent colour, a bold one-word label and a small caption:
Health / Track & monitor; Medication / Reminders; Connect / Family & Friends; Activities / Stay
engaged; Care Services / Professional help; Resources / Guides & support. Then **"Upcoming"** with
a "View all" link, and a peach-tinted card holding a calendar icon and a doctor's appointment
with date, time and place.

**3. Health.** A back arrow, a centred title, a calendar icon. A peach-tinted **Health Overview**
card: a large circular progress ring with a big number in the middle and a label under it, and
beside it a vertical list of four small metric rows, each an icon in its own tinted rounded
square, a label and a value (Steps 4,230/6,000; Heart Rate 72 bpm; Sleep 6h 45m; Water 5/8
cups). Then **Health Insights** with "View all", and a card with a bold headline ("Great job
staying active!"), a line of detail, and an **illustration** (a sneaker) on the right. Then
**Medication Reminder**: a card with a bell icon, the medicine, the instruction and the time on the
right. Then **Today's Tip**: a card with a line of advice and an **illustration** (trees in a park).

**4. Connect.** A back arrow, a centred title, a plus. **Family & Friends** with "View all" and a
horizontal row of **round avatars**, each with a name and a relationship beneath (Emma /
Daughter, James / Son, Sophia / Granddaughter), ending in a dashed "+ Add More" circle. An
**Upcoming Call** card with a video-call illustration and a small "Join" button. A
**Community** row of three tinted tiles with illustrations. **Messages**: a list of rows, each a
round avatar, a name, one line of message, and a time on the right.

**Bottom navigation, on every screen.** Five items, each a line icon above a small label, the
active one in the accent colour.

**Value tiles** (marketing, below the phones): Privacy First, AI Companion, Future Ready, Health
Trends, Easy to Use — each an illustrated icon in a soft circle with a bold title and a caption.

## Reference A: a health dashboard (the secondary reference)

A white and soft-green dashboard. Take from it: **big, bold numbers** as the hero of a card
(a blood pressure of "114/85" in large type on a solid green card); a pair of cards side by side,
one solid-colour and one pale; round **arrow buttons** in the corner of a card to open it; a pill
badge ("Good") that says how a reading sits; and a **bar chart** of the week. Its greeting ("How's
everything going today?") and its round search bar are the same warm, direct tone as Reference B.

## Translating this into Nura

**Palette.** Keep the tokens in `web/src/ui/tokens.css`: `--plum` #4e3a78 is the accent, the
solid-button colour and the active-nav colour. Move the page ground warmer — toward the cream
end (`--cream` #f3e6e0, `--mist` #f5f1f4) rather than lavender. Use the existing pastels as the
**card tints** that give each tile its own colour, the way Eldora's grid does: `--blush`,
`--lavender`, `--sage`, `--coral-wash`, `--cream`. Green (`--good`) stays for good and healthy
signals, like Reference A's green card. Add new tints to `tokens.css` if needed; do not scatter raw
colour values.

**Type.** Add a **serif** display face for the wordmark and large headings, as Eldora does, paired
with the existing sans for body text. Big, bold numbers for readings, as in Reference A.

**Illustration system.** One consistent style: soft flat shapes, warm, rounded, using the palette,
friendly without being childish. Needed at least for: the welcome screen, the Home greeting
(an older person or couple), empty states, the daily check-in, insight cards, tips, and the call
and family screens. Build them as **SVG components** in one place (`web/src/ui/illustrations/`) so
they theme with the tokens and stay crisp at any size. Every illustration is decorative: empty
`alt`, `aria-hidden`, and it never carries information a screen reader would miss.

**Avatars.** A family member's own uploaded photo when they have one; otherwise their initials on
a tinted circle. Never a stock face.

## What Nura must not copy

These parts of the references would break Nura's own rules. Keep the look, change the substance.

- **No invented health score.** Eldora's ring shows a "Wellness Score 85 — Good". Nura does not
  make up a number that judges someone's health, and "Nura does not decide what is wrong" is a
  line it says to patients. Use the ring for **something real and his own**: doses taken this week
  (12 of 14), or days he checked in. A number he can check against what he did.
- **No verdict badges on readings** unless the reading's own reference range backs them, and
  never a colour that implies a clinical judgement Nura has not made. Reference A's "Good" pill is
  fine only where a real range says so.
- **No metrics Nura does not have.** Steps, heart rate, sleep and water are Eldora's. Show what
  Nura actually holds: his medicines and doses, his readings, his visits, his papers, his feelings.
- **No emoji as the only carrier of meaning.** The waving hand and the smiling face are
  decoration; the words must stand on their own for a screen reader and at 200% text.
- **Density still decides type and targets, never the tabs** (#194). The five tabs stay the same
  for the owner and every key-holder.

## What does not change

Accessibility (contrast, 200% text with nothing drawn over a line, reduced motion, the axe
checks), `make plain-words` and `make language` in all three languages, the caregiver-voice rule
(a caregiver's screen never speaks in the patient's voice), and every safety and consent rule.
**A beautiful screen that fails any of these is not done.**
