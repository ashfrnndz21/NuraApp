# Third-party material in the web client

Everything here is self-hosted or bundled: no font CDN, icon CDN or image host is ever asked for anything.

| What | Where | Licence | Source |
|---|---|---|---|
| Outfit (sans, body text) | `public/fonts/outfit-*.woff2` | SIL Open Font License 1.1, `public/fonts/OFL.txt` | github.com/Outfitio/Outfit-Fonts |
| Newsreader (serif, wordmark and large headings, as on the approved board) | `public/fonts/newsreader-*.woff2` | SIL Open Font License 1.1, `public/fonts/OFL-Newsreader.txt` | github.com/productiontype/Newsreader, the variable `opsz`+`wght` files as packaged by `@fontsource-variable/newsreader` 5.3.0 |
| Lucide icons (the shapes only; the `<svg>` is ours) | `lucide` 1.46.0, `src/ui/kit/icons.tsx` | ISC (some shapes MIT, from Feather), `node_modules/lucide/LICENSE` | lucide.dev |

The illustrations in `src/ui/illustrations/` are drawn for Nura in this repository and are not third-party material.
