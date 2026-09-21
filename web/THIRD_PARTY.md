# Third-party material in the web client

Everything here is self-hosted or bundled: no font CDN, icon CDN or image host is ever asked for anything.

| What | Where | Licence | Source |
|---|---|---|---|
| Figtree (sans, body text and every heading — the dusk-glass redesign, docs/design/experience-blueprint.html) | `public/fonts/figtree-*.woff2` | SIL Open Font License 1.1, `public/fonts/OFL-Figtree.txt` | github.com/erikdkennedy/figtree |
| Instrument Serif Italic (the one accent word a headline may carry, `SoftText`'s `*word*`) | `public/fonts/instrument-serif-italic-*.woff2` | SIL Open Font License 1.1, `public/fonts/OFL-InstrumentSerif.txt` | github.com/Instrument/instrument-serif |
| Lucide icons (the shapes only; the `<svg>` is ours) | `lucide` 1.46.0, `src/ui/kit/icons.tsx` | ISC (some shapes MIT, from Feather), `node_modules/lucide/LICENSE` | lucide.dev |

The illustrations in `src/ui/illustrations/` are drawn for Nura in this repository and are not third-party material.
