# Design system — dusk-glass, the product's own visual world

**Status: reference, from 23 September 2026.** One of the three documents
`docs/design/mobile-architecture.md` requires before production UI (the other two are
`MOTION_SYSTEM.md` and `docs/design/design-build-2.md` itself, which stands in for `EXPERIENCE_SPEC.md`).
Every screen after Home imports its tokens from here instead of inventing a value.

**Sources, read in full.** The owner's spec `docs/design/design-build-2.md` §1 (§2, §4–§9, §11–§13,
§16–§28 quoted below by number). The reference implementation, `git show
origin/blueprint-v2:docs/design/experience-blueprint-v2.html` — its `:root` block and the CSS for
`.card[data-variant]/[data-tier]`, `.orb[data-state]`, `.sheet`, `.composer`. The Home spike on
`origin/home-spike`: `apps/mobile/components/motion/motionTokens.ts`, `components/cards/NuraCard.tsx`
and its siblings, `components/ambient/*`. `web/src/ui/tokens.css` and `web/src/ui/kit` (what the web
kit calls the same things, for continuity). The older `docs/design-system.md` (the light system that
preceded the dusk retheme; its glass/paper contrast warning in §5 is re-measured below against the
current dark palette, since it turns out to still apply, just not in the way its own words describe).

**A naming caution.** `experience-blueprint-v2.html`'s outer `:root` block carries **two** unrelated
palettes: the phone's own world (`--c`, `--g`, `--gb`, the atmosphere gradient — the actual product,
documented below) and a light/dark **documentation-tool** palette (`--paper`, `--panel`, `--ink`,
`--soft`, `--line`, `--plum`, `--ready`/`--part`/`--todo`/`--blocked`) that colours the scene picker
and status legend around the phone mockup, never the product itself. Every token below is drawn from
the phone's world (`.phone`, `.glass`, `.card`, `.orb`, `.sheet`, `.composer` and their children), not
the documentation chrome. Where the chrome's `--plum` and the product's own accent both exist, they
are unrelated colours with the same variable name in two different `:root` scopes — a fact worth
stating once here because it is easy to conflate them by name alone.

---

## 1. Colour

### 1.1 The dusk-glass world (the product)

Source: `experience-blueprint-v2.html` `.phone` and its atmosphere (`.atmos`), cross-checked against
`web/src/ui/tokens.css`'s `:root` (retokened to match, per that file's own header comment) and
`apps/mobile/components/motion/motionTokens.ts`'s `phoneTokens`.

| Role | v2 value | web `tokens.css` name | mobile spike name | Note |
|---|---|---|---|---|
| Ink / primary text | `#fbf6f0` (`--c`) | `--ink` | `colorsLight`/`colorsDark` not used here — spike hard-codes `'#fbf6f0'` in each component's `StyleSheet` | The one text colour the whole dusk world reads on glass and paper alike |
| Ink soft / secondary text | not a separate v2 token — `.sample`, `.dose small` etc. use `opacity:.7–.86` on `--c` | `--ink-soft`: `rgba(251,246,240,0.86)` | hard-coded per component, e.g. `rgba(251,246,240,0.7)` (segment label), `rgba(251,246,240,0.75)` (subtitle) — **not one shared value**, see §18 finding | v2 expresses "soft" as opacity on the one ink colour, not a second token; the web kit made that a named token, the mobile spike did not yet |
| Glass fill | `rgba(255,255,255,.10)` (`--g`) | `--glass-bg`: `rgba(255, 255, 255, 0.1)` | `NuraCard.tsx` base card: `rgba(255,255,255,0.08)` | **Divergence:** the spike's card fill (8%) is not v2's glass fill (10%) — see §18 |
| Glass border | `rgba(255,255,255,.22)` (`--gb`) | `--glass-border`: `1px solid rgba(255, 255, 255, 0.22)` | `rgba(255,255,255,0.16)` (`NuraCard`), `rgba(255,255,255,0.22)` (`BottomSheet`, `AIComposer` expanded) | **Divergence:** card border in the spike is lighter (16%) than v2's glass border (22%); the sheet and composer match v2 exactly |
| Paper (opaque decision surface) | not a separate v2 token; `.line`, `.dock` glass rows use the same `--g`/`--gb` | `--paper-bg`: `rgba(255,255,255,0.14)`, `--paper-border`: `1px solid rgba(255,255,255,0.22)` | not present as a distinct surface in the spike | v2 has no "paper" concept distinct from glass — the old design-system.md's Glass/Paper duality (§1.1 below) survives only in the web kit's tokens, not in v2 or the spike |
| Accent (plum) | `#b9a3e6` (documentation-chrome focus ring only, **not** used inside `.phone`) | `--plum`: `#e1d5f7` | not defined as a named token; `IntelligenceOrbCanvas.tsx`'s `GRADIENT` uses `#c9a9e8` (the insight/ai-summary card accent, see §10) as its second stop | The web kit's own comment explains the lift from `#b9a3e6` to `#e1d5f7`: tuned to hold ≥4.5:1 as accent text/icon/border on glass over the ground, since `#b9a3e6` was only ever a focus ring on the documentation tool's pale outer page, not an in-app accent — a deliberate adaptation, not an unexplained divergence |
| Good (in range / confirmed) | `#a9d3ae` (`.flag`, `.btn.done`, `.bar u`) | `--good`: `#a9d3ae` | `metric` card accent `#a9d3ae` (`NuraCard.tsx` `ACCENT.metric`), `.action` accent | Exact match |
| Watch (above/attention) | `#f3b562` (`.flag.hi`, reminder/alert accent) | `--watch`: `#f3b562` | `reminder`/`alert` accent `#f3b562` | Exact match |
| Act (the one red, red-flag only) | `#f08a8a` (`.btn.red`) | `--act`: `#f08a8a` | not yet wired in the spike (no "not well" screen built — Home only, `mobile-architecture.md` §5) | Exact match where it exists |
| Ink-on-light (text on a solid cream fill) | `#2b2140` (`.btn.light`, `.seg b`) | `--ink-on-light`: `#2b2140` | `#2b2140` (`InsightCard`/`ExpandableCard` active-segment text) | Exact match |
| Ink-on-tone (text on a solid sage/amber/rose badge) | `#231a12` (`.flag`), `#2a0d12` (`.btn.red`) — **two slightly different dark inks in v2 itself** | `--ink-on-tone`: `#201509` (one value, not two) | `#231a12` (`ExpandableCard.flagText`/`flagHi`) | The web kit collapsed v2's two near-identical dark inks into one; the spike kept v2's original `#231a12` for its flag text — neither is wrong, but they are not the same hex, see §18 |

**Semantic colours are distinct from the accent, on purpose.** Good (sage, `#a9d3ae`), Watch (amber,
`#f3b562`) and Act (rose, `#f08a8a`) are a separate hue family from the accent purple (`#e1d5f7` /
`#c9a9e8`) so that "this needs your attention" never reads as "this is the AI talking" — the two
purposes never share a colour anywhere in v2, the web kit or the spike.

### 1.2 The atmosphere (ground)

Source: `experience-blueprint-v2.html` `.atmos` (three gradient stops, `background:linear-gradient
(180deg,#4b3c69 0%,#372b52 46%,#1f1731 100%)`) plus two drifting radial blobs and one static one
(`.atmos i.a/.b/.c`).

| Stop | Hex | Position | web `tokens.css` name |
|---|---|---|---|
| Lightest | `#4b3c69` | 0% | `--ground` |
| Mid | `#372b52` | 46% | `--ground-warm` |
| Darkest | `#1f1731` | 100% | `--ground-soft` |

**Divergence, measured.** `tokens.css`'s `--wash-stable` composes these same three stops (and the
same 46% midpoint) as `linear-gradient(160deg, ...)` — the colour stops and the stop position match
v2 exactly, but the **angle does not**: v2's own `.atmos` is `180deg` (straight top-to-bottom), the
web kit's wash is `160deg`. Not invented — both values are read directly from their respective files;
they simply disagree, and nothing in either file explains the 20° difference.

Atmosphere blobs (decorative, behind every screen, never page content):

| Layer | Colour | Opacity | v2 position/size | Motion |
|---|---|---|---|---|
| `.atmos i.a` | `#e7b48f` | .42 | left 150px, top −120px, 380×380 circle, blur 64px | `drift` 16s ease-in-out infinite alternate |
| `.atmos i.b` | `#8f78b3` | .45 | left −140px, top 250px, 420×240, blur 64px | `drift-slow` 20s ease-in-out infinite alternate-reverse |
| `.atmos i.c` | `#15101f` | .55 | left 120px, top 470px, 420×280, blur 64px | **static** — no animation |

**Divergence, measured.** `apps/mobile/components/ambient/AmbientBackgroundCanvas.tsx` draws only
layers **a** and **b** (`aCenter`/`bCenter`, both present with matching colours/opacities from
`phoneTokens`); layer **c** (`#15101f` at .55, the static deep anchor blob) is not drawn anywhere in
the spike's Skia canvas. The AI-state brightness modulation (`BRIGHTNESS_BY_STATE`) and scroll
parallax are new work beyond v2 (v2's blobs never respond to AI state or scroll), consistent with
`mobile-architecture.md`'s brief for `AmbientBackground` ("Skia field that answers scroll and
AIState").

---

## 2. Type scale

Source: `experience-blueprint-v2.html` `<style>` (Figtree 300–600, Instrument Serif italic for the one
accent word) and `apps/mobile/components/text/EditorialHeadline.tsx`. Family: **Figtree** everywhere
except the one italicised accent word, which is **Instrument Serif** (italic only — never a whole
heading), matching `web/src/ui/tokens.css`'s own comment ("the blueprint's `.big`/`.head` are Figtree
300, never a whole heading in serif").

| Role | v2 selector | Size | Weight | Line-height | Notes |
|---|---|---|---|---|---|
| Editorial headline | `.big` | 33px | 300 | 1.08 | Home's top sentence; one `*accent*` word |
| Headline accent word | `.ser` | 1.12em of parent (≈37px at 33px) | 400 italic | inherits | Instrument Serif italic; `EditorialHeadline.tsx` reproduces the exact `size * 1.12` ratio |
| Conversation head | `.head` | 25px | 300 | 1.17 | The AI's own turn heading inside `nura()` |
| Card title (primary/base) | `.card h3` | 18px | 400 | inherits | `InsightCard`/`ExpandableCard` title match this exactly (18px/400 in the spike) |
| Card title (secondary tier) | `.card[data-tier="secondary"] h3` | 16px | 400 | inherits | |
| Card title (tertiary tier) | `.card[data-tier="tertiary"] h3` | 15px | 500 | inherits, opacity .82 | |
| Body | `.body` | 15.5px | 400 | 1.45 | The AI's own response paragraphs |
| Card body (primary/base) | `.card p` | 14.5px | 400 | 1.45 | |
| Card body (secondary tier) | `.card[data-tier="secondary"] p` | 14px | 400 | inherits | |
| Card body (tertiary tier) | `.card[data-tier="tertiary"] p` | 15.5px | 300 | 1.35 | |
| Caption / note | `.note` | 12.5px | 400, opacity .78 | 1.4 | The floor — no caption below 12.5px (`design-build-2.md` §3 checklist) |
| Chip | `.chip` | 14px | 400 | — | `.chip.sm` (compact) is 12.5px |
| Metric number | `.val` | 20px | 600, tabular-nums | 1 | |
| Large metric number (expandable card) | `ExpandableCard.tsx` `styles.value` | 30px | 600 | — | Blood pressure's "148" — larger than `.val`'s generic 20px because it is the card's own headline figure, not a row value |
| Date badge number | `.date b` | 22px | 600 | 1 | |
| Date badge unit | `.date small` | 11.5px | 400, opacity .85 | — | |
| Kicker / eyebrow | `.kick` | 14.5px | 400, opacity .85 | — | "Today" above the headline |
| Reminder row label | `.line` | 17.5px | 300 | — | |
| Bottom-nav tab label | `.tab` | 11.5px | 400 (600 when `aria-current`) | — | See §18 — the web kit's `--text-tab` (13/16px) is larger than this |
| Sheet title | `.sheet h3` | 19px | 400 | — | |
| Sheet body | `.sheet p` | 17.5px | 300 | 1.36 | |

**Tabular numerals.** Every number that changes or is compared — `.val`, `.dvals`, the count-up
figures, the metric value — carries `font-variant-numeric: tabular-nums` (v2's `.val` rule; the web
kit's `--numeric: tabular-nums` token; the spike's `ExpandableCard.tsx` `styles.value` sets
`fontVariantNumeric` implicitly through React Native's numeric text handling on `Text`). No number in
the app is ever proportional-width.

---

## 3. Radius

Source: `experience-blueprint-v2.html` `.card[data-tier]`, `.sheet`, `.row`, `.line`, `.chip`, `.date`,
`.poster`; `apps/mobile/components/cards/NuraCard.tsx`'s `RADIUS` map; `web/src/ui/tokens.css`.

| Surface | v2 value | web token | mobile spike |
|---|---|---|---|
| Card, primary tier | 28px | `--radius-card`: 27px | `RADIUS.primary`: 28px |
| Card, secondary tier | 22px | — (not tiered in the web token set) | `RADIUS.secondary`: 22px |
| Card, tertiary tier | 16px | — | `RADIUS.tertiary`: 16px |
| Card, unspecified/base | 26px | `--radius-tile`: 26px | — |
| Sheet | 30px (top corners only) | `--radius-sheet`: 30px | `BottomSheet.tsx`: 28px top corners |
| Row / list row | 18px | `--radius-row`: 18px | — |
| Reminder line | 24px | — | `ReminderCard.tsx`: 24px |
| Date badge | 14px | — | — |
| Chip / pill | 999px | `--radius-chip`/`--radius-pill`: 999px | `AIComposer.tsx` chip: 999px |
| Media poster | 22px | — | `MediaCard.tsx` poster: **18px** |

**Divergences, measured.** (1) The web kit's `--radius-card` (27px) is not v2's primary-tier card
radius (28px) — one pixel off, unexplained in either file. (2) `BottomSheet.tsx`'s top-corner radius
(28px) is not v2's sheet radius (30px) or the web token's `--radius-sheet` (30px) — both disagree with
the spike by 2px. (3) `MediaCard.tsx`'s poster radius (18px) is not v2's poster radius (22px) — the
largest of the three radius divergences, on a highly visible surface (the media card's own poster
image). None of these are large enough to look broken side by side with the reference, but none of
them is "the same value read from one place" either, which is what `mobile-architecture.md` and
`design-build-2.md` §24 both ask for.

---

## 4. Spacing

Source: `web/src/ui/tokens.css` (the only place an explicit spacing *scale* is declared — v2 itself
uses ad hoc pixel values per rule, not a named scale) cross-checked against v2's actual paddings.

| Token | Value | v2 usage it approximates |
|---|---|---|
| `--space-1` | 8px | `.card` internal gap (`.card{gap:12px}` — not an exact match, see below) |
| `--space-2` (tile gap) | 12px | `.card` gap: 12px (base tier) — **exact match** |
| `--space-3` (tile padding / screen gutter) | 20px | `.scr{padding:26px 20px 14px}` — the **screen's horizontal gutter matches exactly** (20px); card padding does **not** match this token — v2's own primary-tier card padding is 18px, secondary 14px, tertiary "4px 2px", none of which is 20px |
| `--space-4` | 32px | not attested anywhere in v2's phone CSS |
| `--space-half` | 4px | tertiary-tier card padding's vertical component (`4px 2px`) |

**Finding.** `--space-3` is documented as serving two different v2 roles (tile padding *and* screen
gutter) but only actually matches one of them (the screen gutter, 20px). Card padding is tier-specific
in v2 (18/14/4) and never 20px at any tier — a caller reaching for `--space-3` to pad a card is reading
the wrong token; `NuraCard.tsx`'s own `PADDING` map (18/14/4, matching v2 exactly) is the correct
source for card interior padding, not the generic spacing scale.

---

## 5. Blur / backdrop

Source: `experience-blueprint-v2.html` `.glass{backdrop-filter:blur(18px)}`, `.sheet{backdrop-filter:
blur(24px)}`, `.composer .ask{backdrop-filter:blur(22px)}`.

| Surface | v2 blur | web token | mobile spike |
|---|---|---|---|
| Card / glass tile | 18px | `--glass-blur`: `blur(18px)` | `NuraCard.tsx`: `BlurView intensity={22}` (native only; web falls back to no blur, `Platform.OS !== 'web'` guard) |
| Sheet | 24px | — (no dedicated sheet-blur token) | `BottomSheet.tsx`: `BlurView intensity={28}` |
| Composer (expanded) | 22px | — | `AIComposer.tsx`: `BlurView intensity={30}` |
| Chip | not declared distinctly in v2's `.chip` rule | `--chip-blur`: `blur(12px)` | not present |

**A unit mismatch, not a value comparison.** Expo's `BlurView intensity` is a 0–100 scale with no
declared px-equivalent to CSS `backdrop-filter: blur()`; the three `intensity` values above (22, 28,
30) cannot be checked against v2's px values (18, 24, 22) by number, only by the same *ordering* — and
the ordering does hold (card < sheet, composer close to sheet), which is the one thing that can
honestly be said to carry over. `--chip-blur` (12px) has no source in v2 at all — v2's `.chip` rule
sets no `backdrop-filter`; it is the web kit's own addition, not extracted from the reference.

---

## 6. Borders

Every glass surface in v2 carries a **1px** border at `rgba(255,255,255,.22)` (`--gb`) — cards
(`.glass` recipe, inherited by `.card`'s base), the sheet (`border-top:1px solid var(--gb)`), the
composer (`border:1px solid var(--gb)`), chips (`border:1px solid var(--gb)`). The one exception:
alert-variant cards carry a warmer border, `rgba(243,181,98,.55)` (`.card[data-variant="alert"]`),
so a card that needs attention is visually distinct from a card that doesn't, at the border alone,
before any text is read. Tertiary-tier cards have **no** border (`border:0`) — they are type on the
ground, not a surface (`design-build-2.md` §5: "not all identical"). The web kit's `--glass-border`
(`1px solid rgba(255,255,255,0.22)`) and `--paper-border` (same) match v2 exactly. The spike's
`NuraCard.tsx` uses a lighter border (`rgba(255,255,255,0.16)`) for its base/non-alert cards — a
divergence already noted in §1.1's colour table.

---

## 7. Shadows as depth

**v2 uses none, on cards.** `design-build-2.md` §2: "soft depth rather than hard shadows." No `.card`
rule in `experience-blueprint-v2.html` declares a `box-shadow`; depth comes entirely from the
translucent glass fill, the border and the backdrop blur against the moving atmosphere behind it. The
only `box-shadow` in the whole file belongs to the phone bezel itself (`.phone{box-shadow:0 0 0 9px
#0f0b17,0 0 0 10px #3a3049,0 30px 60px rgba(30,15,60,.35)}`) — a device frame, not a card.

**The web kit adds one anyway.** `web/src/ui/tokens.css` declares `--tile-shadow`/`--card-shadow: 0
20px 44px rgba(15, 10, 24, 0.32)`, with no v2 source. This is not necessarily wrong for a browser
context where translucency-only depth can read flatter without the phone bezel's own containing frame
— but it is an addition, not an extraction, and should be named as one rather than presented as "the
v2 card shadow."

**The orb's glow is its own, separate depth language** — see §11.

---

## 8. Iconography rules

Source: `experience-blueprint-v2.html`'s `ic()`/`I` icon helpers (inline SVG, `viewBox="0 0 24 24"`,
`stroke="currentColor"`, `stroke-width="1.6"`, `stroke-linecap`/`stroke-linejoin="round"`,
`aria-hidden="true"`, default render size 22px) and `docs/design-system.md` §2 ("Icons never carry
meaning alone — every icon has a word beside it"), a rule the newer spec does not restate but does not
contradict either — v2's own icons are consistently paired with a label (`accessibilityLabel` on the
parent control, never the icon alone).

| Property | v2 value | web token |
|---|---|---|
| Stroke width | 1.6px | `--icon-stroke`: **1.5px** |
| Default render size | 22px | `--icon-size`: 24px (caregiver density) / 28px (patient density) |
| `aria-hidden` | always, on the icon itself | — (React Native equivalent: `accessible={false}` on the icon, label on the parent) |

**Divergence, measured.** v2's own inline SVGs are drawn at `stroke-width="1.6"`; `--icon-stroke` says
1.5px. A one-tenth-pixel difference is invisible at render size, but it is a value that does not
match its stated source, the exact class of drift `design-build-2.md` §24 ("nothing hard-coded")
exists to prevent.

---

## 9. The card system

Source: `experience-blueprint-v2.html` `.card[data-variant]`/`[data-tier]` (spec §5) and
`apps/mobile/components/cards/NuraCard.tsx` (`CardVariant`, `CardTier`, `ACCENT`, `RADIUS`, `PADDING`).

**One card, nine variants, three tiers** (`design-build-2.md` §5): insight, reminder, media, metric,
recommendation, document, ai-summary, action, alert — never a different component per kind of content,
only a different `data-variant`/`variant` prop.

### 9.1 Tiers

| Tier | Radius | Padding | Title size/weight | Body size | Surface |
|---|---|---|---|---|---|
| Primary | 28px | 18px | 18px/400 | 14.5px | glass, blurred, bordered |
| Secondary | 22px | 14px, gap 10px | 16px/400 | 14px | glass, blurred, bordered |
| Tertiary | 16px | 4px 2px, gap 6px | 15px/500, opacity .82 | 15.5px/300, line-height 1.35 | **none** — `background:none;border:0;backdrop-filter:none` — type directly on the ground |

### 9.2 Variants (accent colour, from `--vac` in v2 / `ACCENT` in the spike — exact match)

| Variant | Accent (`--vac`) | Dot shown? | Notes |
|---|---|---|---|
| insight | `#c9a9e8` | yes | Home's primary story card |
| reminder | `#f3b562` | yes | one-line, uses the `.line` row shape, not the general card padding |
| media | `#9fd0ff` | **no** (`.card[data-variant="media"] h3::before{display:none}`) | own padding override: `10px`, gap `10px` |
| metric | `#a9d3ae` | yes | the expandable blood-pressure card's own variant |
| recommendation | `#e7b48f` | yes | |
| document | `#fbe3cf` | yes | |
| ai-summary | `#c9a9e8` | **no** (same `display:none` rule as media) | shares insight's accent hue |
| action | `#a9d3ae` | yes | shares metric's accent hue |
| alert | `#f3b562` | yes | **also** gets the warmer border override (§6) — the one variant whose border, not just its dot, carries the semantic colour |

**The accent dot itself** is a 6×6px circle, `box-shadow:0 0 9px var(--vac)` — the card's glow,
proportional to how much attention the variant deserves; alert and reminder (amber) read slightly
warmer than insight/ai-summary/metric (violet/sage) at a glance, before any text is read.

### 9.3 Motion (see `MOTION_SYSTEM.md` for full token values)

Entry: fade 0→1 + 12px upward translate, on `card.enter` (520ms, spring-gentle), staggered by list
density. Press: scale to 0.985 over 100ms (linear), release on `press-out` (260ms, spring-bouncy), a
4% white brightening overlay while held (`NuraCard.tsx`'s `brighten` shared value — this brightening
step is **not** present anywhere in v2's own CSS, which only scales and dims via a linear-gradient
overlay on `:active`; the 4%-brighten-on-press behaviour is new work in the spike, consistent with
spec §7's prose ("surface slightly brighter") but not literally reproduced from v2's rule).

---

## 10. The orb

Source: `experience-blueprint-v2.html` `.orb[data-state]` (spec §8) and
`apps/mobile/components/ambient/IntelligenceOrbCanvas.tsx`.

### 10.1 Size variants

| Size | v2 class | px | Blur (v2 `filter:blur()`) |
|---|---|---|---|
| Small | base `.orb` | 36px | 5px |
| Medium | `.orb.md` | 74px | 9px |
| Large | `.orb.lg` | 128px | 15px |

The spike's `OrbSize`/`SIZE_PX` (`sm`/`md`/`lg` → 36/74/128) matches v2's three sizes exactly.

### 10.2 Glow, per state (v2 `box-shadow`; the spike's Skia `glowOpacity`)

| State | v2 outer glow | v2 inner glow | Spike `glowOpacity` |
|---|---|---|---|
| idle | `0 0 14px rgba(201,169,232,.55)` | `inset 0 0 8px rgba(255,255,255,.5)` | 0.35 |
| listening | `0 0 22px rgba(201,169,232,.8)` | `inset 0 0 8px rgba(255,255,255,.6)` | 0.55 |
| thinking | (no distinct box-shadow rule — inherits idle's) | — | 0.55 |
| responding | `0 0 20px rgba(201,169,232,.75)` | `inset 0 0 8px rgba(255,255,255,.6)` | 0.55 |
| error | `0 0 9px rgba(170,158,186,.3)` (desaturated, dimmer than idle) | `inset 0 0 8px rgba(255,255,255,.28)` | 0.18 |
| large (any state) | `0 0 46px rgba(201,169,232,.55)` | `inset 0 0 22px rgba(255,255,255,.5)` | scales with size in the Skia implementation |

**Gradient.** Six-stop conic sweep in v2: `#fbe3cf,#c9a9e8,#6f4fc4,#f0b48f,#9fd0ff,#fbe3cf` — the
spike's `GRADIENT` constant reproduces this exactly. Error state substitutes a desaturated grey ramp
(`GRADIENT_ERROR`, spike-only — v2 achieves its error look via `filter:blur(5px) saturate(.2)` on the
same colour gradient rather than swapping the gradient itself; the spike's approach reads calmer and
is a legitimate reinterpretation, not a bug, but it is worth naming as a different technique for the
same spec line, "subdued, never aggressive red," §8).

**Spin duration = state duration** (`--orb-idle:7s`, `--orb-listening:3.4s`, `--orb-thinking:2.2s`,
`--orb-responding:4.2s` — full values and every other motion token are in `MOTION_SYSTEM.md`).

---

## 11. Bottom navigation

Source: `experience-blueprint-v2.html` `.tabs`/`.tab` (spec §17); `design-build-2-map.md` row "Bottom
navigation (§17) — Matches" (the kit's `TabBar` already satisfies the spec).

| Property | v2 value |
|---|---|
| Layout | `justify-content:space-between`, no background chrome of its own |
| Tab min size | 62px min-width, 46px min-height |
| Label size | 11.5px |
| Inactive opacity | .6 |
| Active state | opacity 1, font-weight 600, `aria-current="true"` |

"Visually quiet, subtle but obvious active state… content is the hero; navigation is infrastructure"
(§17) — no fill, no pill, no icon-only rendering; the active tab is only ever opacity + weight.

---

## 12. Sheets

Source: `experience-blueprint-v2.html` `.sheet`/`.scrim`/`.grab`/`.drag` (spec §20);
`apps/mobile/components/sheets/BottomSheet.tsx`.

| Property | v2 value | Spike value |
|---|---|---|
| Radius (top corners) | 30px | 28px (see §3 divergence) |
| Background | `rgba(27,20,44,.9)` | `rgba(30,24,44,0.97)` — close but not identical |
| Border (top) | `1px solid var(--gb)` (`rgba(255,255,255,.22)`) | matches |
| Backdrop blur | 24px | `BlurView intensity={28}` (unit mismatch, §5) |
| Backdrop dim | `rgba(15,11,23,.52)` | web: `rgba(21,16,31,0.55)` — close but not identical |
| Min height | 340px | not fixed — sizes to content |
| Max height | 78% of phone | not fixed |
| Entry | `sheet-enter`: 550ms, spring-standard | `springs.standard` (physical params tuned to match, `springs.ts`) |
| Grab handle | 44×5px, `rgba(255,255,255,.3)`, radius 3px | 40×4px, `rgba(255,255,255,0.28)`, radius 2px |
| Dismiss | drag past distance or velocity, backdrop tap | `DISMISS_DISTANCE = 110`, `DISMISS_VELOCITY = 800` (px/s) — **no source in v2**, which has no numeric drag thresholds in its CSS (drag physics live in the reference's absent/unbuilt JS — `design-build-2-map.md`'s own finding: "no shared-element transition exists anywhere in the blueprint's own code… the composer never expands in place in the blueprint" applies equally to sheet drag: v2's sheet **opens/closes** via CSS transform but has no drag handler at all to measure a threshold from) |

The two dismiss constants (110px, 800px/s) are therefore the spike's own tuned values, not values
read from any source — flagged here rather than presented as extracted, per this document's own rule.

---

## 13. Chips / pills

Source: `experience-blueprint-v2.html` `.chip`/`.chip.sm`/`.chip.on`; `apps/mobile/components/ai/
AIComposer.tsx` (`styles.chip`).

| Property | v2 | Spike |
|---|---|---|
| Radius | 999px | 999px |
| Min height | 42px | 42px |
| Padding | 9px 15px | 15px horizontal, 9px vertical |
| Background | `rgba(255,255,255,.14)` | `rgba(255,255,255,0.14)` |
| Border | `1px solid var(--gb)` | `1px solid rgba(255,255,255,0.22)` |
| Text size | 14px (12.5px for `.sm`) | 14px |
| Active (`.on`) | filled `--c`, `#2b2140` text, weight 600 | not built (composer chips are exit-only, never toggled) |
| Disabled | not a v2 concept | `chipsDisabled`: opacity 0.5 (spike-only, prevents double-fire during the fixture stream) |

---

## 14. Empty / loading / error — the three shared shapes

Source: `experience-blueprint-v2.html` `loadingState()`, `emptyState()`, `errorState()` (lines
334–336, spec §21–23) — this is the shape `A-167` (`docs/design/end-to-end-acceptance.md`) requires as
**one primitive each**, not per-screen copy.

| Primitive | Card shape | Contents | Motion |
|---|---|---|---|
| `LoadingState` | `data-variant="ai-summary" data-tier="secondary"` | orb (`thinking`) + one status line that swaps in place (never a stack) + two shimmer bars (82% and 64% width) | status line cross-fades old→new text every `2 × motion-slow` (1120ms) while lines remain; shimmer sweeps continuously on `--sweep` (1.5s) |
| `EmptyState` | `data-variant="metric" data-tier="primary"` | one title line (19px/300), one why line (opacity .8), one light-filled CTA button | none — appears with the card's own `card.enter` |
| `ErrorState` | `data-variant="alert" data-tier="primary"` | orb (`error`) + title + why line + light-filled CTA ("Try again") | none beyond `card.enter`; the orb's own error glow (§10.2) carries the calm-not-alarming read |

**The wording rule, carried from both specs.** `design-build-2.md` §21: "Never 'Loading…'" — always a
specific, honest sentence ("Looking through your recent results…"). §22: why → what → next
("We don't have any blood pressure readings yet." → "Add your first reading"). §23: never an HTTP
code ("We couldn't reach your clinic records right now." + Try again). The older `docs/design-
system.md` §6 ("Errors… What happened and what to do, one sentence") and §4 ("Empty states: an
invitation in one sentence and one action") state the identical rule in the light system's words —
this is the one piece of the old system that survives the retheme completely unchanged.

---

## 15. Accessibility — measured contrast

**Method.** WCAG 2 relative-luminance formula, computed from the token hex/rgba values above (never
asserted). Text-on-glass is measured as the *composite* colour (text blended over the glass fill,
which is itself blended over the atmosphere), per `docs/design/end-to-end-acceptance.md` **A-174**:
*"text-on-glass-on-gradient contrast is measured against the darkest point of the moving background
gradient (not just the glass fill)."*

**A correction to A-174's own wording.** A-174 says to test against the atmosphere's *darkest* stop.
For **light text on a dark ground** (this palette — cream `#fbf6f0` ink on a violet-to-near-black
atmosphere) that is backwards: contrast *falls* as the background gets *lighter*, because the gap
between text-luminance and background-luminance narrows. The measured worst case for every pair below
is therefore the atmosphere's **lightest** stop (`--ground`, `#4b3c69`), not its darkest
(`--ground-soft`, `#1f1731`) — the opposite instruction would have produced falsely reassuring numbers
against the wrong stop. (A-174's phrasing reads as carried over from the old, light-theme
design-system.md, where dark ink on a *light* wash genuinely was safest measured against the wash's
darkest stop — correct there, incorrect here after the retheme.) Every number below is measured
against `#4b3c69`, the true worst case for this palette; the darkest-stop numbers are given alongside
for reference.

| Pair | Surface | At `#4b3c69` (worst case) | At `#1f1731` (A-174's literal instruction) | AA 4.5:1 | Patient-density 7:1 |
|---|---|---|---|---|---|
| Ink (`#fbf6f0`) on Glass (10% white) | card/chip/sheet text | **6.81:1** | 11.99:1 | pass | **fail** |
| Ink-soft (86% `#fbf6f0`) on Glass | secondary/caption text on a card | **5.55:1** | 9.31:1 | pass | **fail** |
| Ink on Paper (14% white) | patient-density card fill, `--card-bg` | **6.07:1** | 10.44:1 | pass | **fail** |
| Ink-soft on Paper | secondary text on a patient-density card | **5.00:1** | 8.20:1 | pass | **fail** |
| Plum accent (`#e1d5f7`) on Glass | accent text/icon/border | **5.25:1** | 9.24:1 | pass | fail (not required — accent/UI text, not body copy) |
| Ink-on-tone (`#201509`) on Watch (`#f3b562`) | amber badge/flag text | **9.89:1** | — (solid fill, ground-independent) | pass | pass |
| Ink-on-tone on Good (`#a9d3ae`) | sage badge text | **10.76:1** | — | pass | pass |
| Ink-on-tone on Act (`#f08a8a`) | rose badge text | **7.43:1** | — | pass | pass |
| Ink-on-light (`#2b2140`) on cream fill | filled CTA button text | **14.02:1** | — | pass | pass |

**What fails, and why it matters.** Four pairs clear the WCAG AA floor (4.5:1) with real margin but
fall short of the older `docs/design-system.md` §5's stricter patient-density rule ("text contrast
7:1 or better; numbers and actions on Paper only" — the exact warning the task asked to re-check
against). The most significant is **Ink on Paper at 6.07:1**: `web/src/ui/tokens.css`'s own comment on
patient density claims this pairing "holds 7:1 on paper in his density," promoting `--ink-quiet` to
the full-opacity `--ink` specifically to reach that bar — but measured against the atmosphere's actual
lightest stop, it falls short by nearly a full point. The promotion helps (it is the difference
between 5.00:1 and 6.07:1, comparing the Ink-soft-on-Paper row to the Ink-on-Paper row) but does not,
by itself, deliver the 7:1 the comment promises. This is a genuine, measured gap in an otherwise
carefully-reasoned token set, not a difference of opinion about the target.

**No pair fails ordinary AA.** Every pair in the table clears 4.5:1, several by a wide margin. The
badge/flag pairs (solid fills, ground-independent) all clear 7:1 as well, since a solid badge never
sits directly on the moving atmosphere.

**What this means for a caller.** Any screen holding patient density (`data-density="patient"`) that
sets body text or a number in `--ink-quiet` on a Paper surface near the top of a screen (where the
atmosphere is at its lightest stop) is reading at ~6.1:1, not 7:1. Two honest paths forward, left to
the owner to choose rather than decided here: raise `--ink-quiet` further (there is no headroom left
in `--ink` itself, since it is already the maximum-luminance token — the fix would need to sit under
the text, not above it, e.g. a slightly-darker/less-translucent Paper fill near the top of the
screen), or accept 6.1:1 as the patient-density floor and update the claim in `tokens.css`'s own
comment to match what is actually measured.

---

## 16. Responsive rules

Source: `design-build-2.md` §26 ("Mobile first. Tablet/desktop widen intelligently, keep card
proportions, larger editorial compositions, sensible columns, same hierarchy and interaction
philosophy") and `docs/design/end-to-end-acceptance.md` **A-178**/**A-179**.

| Breakpoint | What holds | What changes |
|---|---|---|
| Phone (390×844, the reference frame) | Full hierarchy, one column, card proportions exactly as `experience-blueprint-v2.html` | — |
| Tablet (1280×900, the reference wide capture) | Same card proportions, same variant/tier system, same interaction philosophy (expand-in-place, sheets, composer) | Column count and editorial composition may widen — **A-179 leaves the exact tablet layout to be specified by the owner**; nothing in v2, the spike or the acceptance doc states a column count or a named breakpoint between phone and the 1280×900 capture |

**Not yet decided.** Whether an iPad-class device is in scope for the acceptance gate at all is
explicitly open (`end-to-end-acceptance.md` A-179: "to be specified by the owner whether iPad is in
scope"). This document does not invent a tablet column count or a named intermediate breakpoint where
none of its sources state one.

---

## 17. Token name mapping — web → v2 → mobile

Every colour/radius/blur token that exists in more than one place, side by side. A row with only two
columns filled means the third has no equivalent yet — not an oversight to silently fill in here.

| Role | v2 (`experience-blueprint-v2.html`) | web `tokens.css` | `apps/mobile` (spike) |
|---|---|---|---|
| Primary text | `--c` `#fbf6f0` | `--ink` `#fbf6f0` | `'#fbf6f0'` (hard-coded per component) |
| Secondary text | opacity .7–.86 on `--c` | `--ink-soft` `rgba(251,246,240,.86)` | `rgba(251,246,240,0.7–0.86)` (varies per component, §1.1) |
| Glass fill | `--g` `rgba(255,255,255,.10)` | `--glass-bg` `rgba(255,255,255,.10)` | `rgba(255,255,255,0.08)` (NuraCard, divergent) |
| Glass border | `--gb` `rgba(255,255,255,.22)` | `--glass-border` `rgba(255,255,255,.22)` | `rgba(255,255,255,0.16)` (NuraCard, divergent) / `.22` (Sheet, Composer, matching) |
| Accent | `#b9a3e6` (chrome only — not in `.phone`) | `--plum` `#e1d5f7` | not named; orb gradient's `#c9a9e8` stands in as the card accent for insight/ai-summary |
| Good | `#a9d3ae` | `--good` `#a9d3ae` | `ACCENT.metric`/`ACCENT.action` `#a9d3ae` |
| Watch | `#f3b562` | `--watch` `#f3b562` | `ACCENT.reminder`/`ACCENT.alert` `#f3b562` |
| Act | `#f08a8a` | `--act` `#f08a8a` | not yet used (Home spike only) |
| Ink-on-light | `#2b2140` | `--ink-on-light` `#2b2140` | `#2b2140` |
| Ink-on-tone | `#231a12` / `#2a0d12` (two values) | `--ink-on-tone` `#201509` (one value) | `#231a12` |
| Card radius, primary | 28px | `--radius-card` 27px | `RADIUS.primary` 28px |
| Sheet radius | 30px | `--radius-sheet` 30px | 28px (BottomSheet) |
| Chip/pill radius | 999px | `--radius-chip`/`--radius-pill` 999px | 999px |
| Glass blur | 18px | `--glass-blur` blur(18px) | `BlurView intensity={22}` (unit mismatch) |
| Motion — card enter | 520ms, spring-gentle | not tokenised in `tokens.css` (only `--settle` 220ms exists, a different value/purpose) | `cardEnter` 520 (motionTokens.ts, exact match) |
| Motion — press | 100ms in / 260ms out | `--press` 90ms (one direction only, no spring-bouncy release token) | `pressIn` 100 / `pressOut` 260 (exact match) |

**The headline finding of this table:** the **mobile spike's motion tokens match v2 exactly, value for
value** (`motionTokens.ts`'s own docstring: "copied verbatim from the `:root` block… same names, same
values"); the **colour and radius tokens carry small, real drifts** in several places (glass fill
8% vs 10%, card border 16% vs 22%, sheet/card radius off by 2px each, media poster radius off by 4px).
The **web kit's tokens are a deliberate re-theme** (its own header comment says so) and is not held to
matching v2 pixel-for-pixel the way the spike's motion tokens are — its divergences are documented
adaptations (the accent lift, the paper/glass duality), not drift.
