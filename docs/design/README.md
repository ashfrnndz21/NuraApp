# Design references

**The acceptance reference is `experience-blueprint.html`** (approved by the owner on 2026-09-18: "yes this is exactly it").
Open it in a browser. It is a working phone walking the whole journey, with, beside every scene, what the person sees,
what Nura is really doing, and the build status of each piece.

The interaction language it fixes, from the owner's reference recording:

1. One living orb is the assistant: large at a greeting, small beside a conversation, never still.
2. Thinking is ONE status line that changes in place with a light sweep. It is never an accumulating checklist.
   Every status line is a stage the backend really reports; nothing is invented and no delay is added.
3. Text arrives word by word, blurred to sharp. It is not a hard typewriter.
4. Structure assembles after the words: headline, then tabs, then rows one by one, then actions last.
5. Every answer ends in actions. An action slides a sheet up, a draft streams into it, and the button goes through
   three states (Copy, Copying, Copied). Nura never sends anything itself.
6. The safety line appears once per screen, not on every card. "Not feeling well" is the one place the calm breaks:
   no animation, no delay.
7. On the web the app always presents inside a phone frame above 600px; on a phone it is full-bleed.

Keep Nura's own type scale and contrast: body text at 15px or larger and 4.5:1. The references this came from use
small low-contrast type that would fail the older adults Nura is for.

Never show an invented price for a real hospital; the blueprint leaves those figures as bracketed blanks on purpose.

`full-experience.html`, `nura-concept-board.html`, `onboarding-mock.html` and `prototype-reference.html` are earlier
references, kept for history. Where they disagree with the blueprint, the blueprint wins.
