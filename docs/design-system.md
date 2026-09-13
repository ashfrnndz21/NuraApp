# Nura — UI design system

Direction taken from the references: light, soft gradient washes; frosted glass tiles; one big number per screen; a quiet, unhurried tone. This document turns that into a system that also works for a 72-year-old in poor light without his glasses.

---

## 1. The one adaptation

Glassmorphism fails the elderly in one specific way: text on a blurred, translucent surface over a gradient drops contrast to the point where a reading or a dose becomes hard to read. So the system uses two surfaces that share one visual language:

- **Glass** — translucent, blurred, luminous. Carries chrome and secondary information: navigation, chips, context tiles, the caregiver's dense views.
- **Paper** — near-opaque white inside the same rounded silhouette. Carries anything a decision depends on: a dose, a number, a date, a button.

The **Chief** (Ash) sees mostly glass. **Dad** sees mostly paper, framed by glass. Same tokens, same shapes, same washes — different opacity and density. Nothing looks like a different app.

The memorable idea: **the background is the status.** Each screen's gradient wash is tinted by the person's State — stable (lavender to sage), watch (blush to lavender), act (soft coral to lavender). Never an alarm colour, never a red banner. The light shifts; the layout doesn't.

---

## 2. Tokens

### Colour

| Token | Hex | Use |
|---|---|---|
| Mist | `#F5F1F4` | Page base, behind washes |
| Blush | `#F1DCE6` | Wash stop, watch state |
| Lavender | `#DCD5EE` | Wash stop, stable state |
| Sage | `#DCE8DF` | Wash stop, stable state |
| Coral wash | `#F0D6D2` | Wash stop, act state |
| Ink | `#2B2733` | Primary text (plum-black, not pure black) |
| Ink soft | `#6A6377` | Secondary text |
| Plum | `#4E3A78` | The single accent: primary buttons, active tab, links |
| Good | `#3B7A57` | Confirmed, in range |
| Watch | `#B8741A` | Trending, worth attention |
| Act | `#C24A3A` | Needs action today (used on text and dots, never as a fill) |

State washes (160° linear, plus one soft white radial light at top-left):

- Stable: Lavender → Blush → Sage
- Watch: Blush → warm cream `#F3E6E0` → Lavender
- Act: Coral wash → `#F2E0DE` → Lavender

### Glass tile recipe

```
background: rgba(255,255,255,.55)
backdrop-filter: blur(18px) saturate(1.2)
border: 1px solid rgba(255,255,255,.7)
inner top highlight: 0 1px 0 rgba(255,255,255,.8) inset
shadow: 0 8px 24px rgba(60,40,80,.06)
radius: 20px (tile) / 28px (sheet) / 999px (pill)
```

Paper tile: same recipe with `background: rgba(255,255,255,.92)` and no blur. Contrast of Ink on Paper is above 12:1; on Glass over a wash it is roughly 8:1 for Ink and drops for Ink soft — which is why numbers and actions never sit on Glass in Dad mode.

### Type

One family: **Outfit** (fallback: system sans). Weight is the persona dial.

| Role | Chief | Dad |
|---|---|---|
| Display number / state word | 56px, weight 300 | 56px, weight 500 |
| Tile number | 36px, 400 | 40px, 500 |
| Title | 20px, 500 | 24px, 500 |
| Body | 16px, 400, line-height 1.5 | 20px, 400, line-height 1.5 |
| Caption | 13px, 400 | 16px, 400 |
| Button | 16px, 500 | 20px, 500 |

No all-caps. No letter-spaced eyebrows. Sentence case everywhere. Numbers use tabular figures.

### Spacing and shape

8px grid. Tile padding 20px. Gap between tiles 12px. Screen gutter 20px. Radii carry hierarchy: hero sheet 28px, tile 20px, pill 999px, chip 12px. Touch targets 48px minimum, 56px in Dad mode.

### Motion

Motion only answers an action. "Taken" settles the tile and updates the count; a new card slides in once; the wash cross-fades when State changes (1.2s). No entrance animations on load, no hover flourishes. `prefers-reduced-motion` disables everything except opacity changes.

### Iconography

Thin-line icons at 1.5px stroke, 24px; 28px in Dad mode. Icons never carry meaning alone — every icon has a word beside it.

---

## 3. Information architecture

### Dad — four tabs, nothing deeper than two taps

| Tab | What's on it |
|---|---|
| **Today** | Greeting in his language, the one big number (medicines due, or the next visit), paper tiles for each due dose, next visit tile, family note tile, the "I'm not feeling well" pill |
| **Medicines** | List with pill photos, purpose in his words, count and reorder date; "What is this pill?" camera |
| **Ask** | Voice-first. Big microphone. Answers as a card plus a voice note; plays the consult clip when there is one |
| **Visits** | Last visit summary, next visit card with questions, the emergency card behind a long-press on the tab |

Emergency card is also a lock-screen widget and a printable page.

### Chief — five tabs, dense but calm

| Tab | What's on it |
|---|---|
| **Home** | State hero (most likely state, drivers, sparkline), "What changed since you last looked", appointment radar, reorder queue, gaps |
| **Timeline** | Episodes and appointments as the spine, artefacts hanging off events, filter by body system |
| **Medicines** | Reconciled list with source and confidence, medication story, interactions and polypharmacy talking points, adherence by week |
| **Plan** | Routine builder, care plan with roles and roster, visit prep workspace, push composer with preview |
| **Family** | Grants and roles, helper surface settings, family thread, audit log |

"Ask about Dad" is a persistent pill at the bottom of every Chief screen.

### Helper — WhatsApp only

Today's list with pill photos and "given" replies; a "he is not well" quick reply; nothing else.

### Screen inventory (Stage 1)

Dad: Today, Medicine list, Medicine detail, Ask, Answer card, Visit next, Visit last, Questions card, Emergency card, Not feeling well flow (3 steps), Food snap result, Weekly recap clip. Twelve.

Chief: Home, What changed, State detail, Timeline, Event detail, Medicine list, Medicine story, Interactions and polypharmacy, Adherence, Plan routine, Care plan and roster, Visit prep workspace, Push composer and preview, Reorder queue, Insurance and GL, Cost ledger, Family grants, Helper settings, Family thread, Audit, Onboarding health biography (5 steps), Capture review card. Twenty-two plus onboarding.

---

## 4. Components

**Hero.** Sits directly on the wash, no tile. One label, one large figure or state word, one sentence. Dad: "2 medicines this morning." Chief: "Stable — watch blood pressure."

**State wash.** The screen background, driven by State. Cross-fades on change. Never used as an alert.

**Paper tile (primary).** Opaque. Title, the number or the fact, one sentence, one action. Dad's dose tiles, reading tiles, visit tiles.

**Glass tile (secondary).** Translucent. Context that doesn't need a decision: family note, "questions ready", gaps, chips.

**Card grammar (feed).** One number, one direction (arrow or word), one colour (Good / Watch / Act on the figure only), one action. Provenance line in caption size: "From the pharmacy label, 1 Sep." "Why am I seeing this" behind a tap.

**Pill button.** Full-width in Dad mode. One Plum-filled pill per screen at most; the rest are Paper outlines. "I'm not feeling well" is a soft coral-tinted Paper pill, never a red button.

**Chip.** Glass, 12px radius, for drivers and tags (body systems, sources). Text in Ink, never white-on-colour.

**Sparkline.** 1.5px Ink line, last point marked, range band in 8% Plum. No axes in Dad mode; caption states the direction in words.

**Body-systems map.** A quiet outline figure with soft Plum glows on the systems an insight touches; doubles as a filter on Timeline and feed.

**Memo card.** Paper, the person's own words in quotes, filed date, attached appointment. Rendered identically to both personas.

**Voice note and clip player.** Glass strip with a large play target; transcript below in Dad's body size.

**Capture review card.** After a photo: what was read, confidence per field as a soft underline (solid = confident, dotted = please confirm), one "Looks right" button.

**Empty states.** An invitation in one sentence and one action. "No visits yet. Add the next one from a photo of the appointment card."

**Errors.** What happened and what to do, one sentence. "Couldn't read the label. Try with the label flat and in daylight."

---

## 5. Accessibility rules (non-negotiable in Dad mode)

- Text contrast 7:1 or better; numbers and actions on Paper only.
- Body 20px minimum; respects OS dynamic type up to 200%.
- Targets 56px; one action per tile; no swipes required.
- Every card has a voice-note version; every clip has captions.
- Language set per person: Malay, Mandarin, English at launch; Hokkien and Tamil voice next.
- Works on a five-year-old Android at 360px width, offline for the emergency card and today's list.

---

## 6. Voice and tone

Subtle, plain, unhurried. Sentences, not labels. No exclamation marks, no "great job", no streak language. The patient's own words are quoted back in memo cards. Numbers are explained in one sentence in his terms ("Sugar is better than March"), never in clinical shorthand. The boundary line appears in caption size on every screen that infers.

---

## 7. What the mockup shows

`ui-mockup.html` renders the Today screen (Dad, stable wash), the Home screen (Chief, watch wash) and the token sheet. It is a design reference, not a build; all values are illustrative.
