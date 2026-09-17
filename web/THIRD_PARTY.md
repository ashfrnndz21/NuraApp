# Third-party material in the web client

Everything here is self-hosted or bundled: no font CDN, icon CDN or image host is ever asked for anything.

| What | Where | Licence | Source |
|---|---|---|---|
| Outfit (sans, body text) | `public/fonts/outfit-*.woff2` | SIL Open Font License 1.1, `public/fonts/OFL.txt` | github.com/Outfitio/Outfit-Fonts |
| Fraunces (serif, wordmark and large headings) | `public/fonts/fraunces-*.woff2` | SIL Open Font License 1.1, `public/fonts/OFL-Fraunces.txt` | github.com/undercasetype/Fraunces, the variable `opsz`+`wght` files as packaged by `@fontsource-variable/fraunces` 5.3.0 |
| Lucide icons (the shapes only; the `<svg>` is ours) | `lucide` 1.46.0, `src/ui/kit/icons.tsx` | ISC (some shapes MIT, from Feather), `node_modules/lucide/LICENSE` | lucide.dev |

The illustrations in `src/ui/illustrations/` are drawn for Nura in this repository and are not third-party material.
