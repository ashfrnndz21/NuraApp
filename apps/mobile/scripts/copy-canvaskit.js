#!/usr/bin/env node
/**
 * The web target renders Skia through CanvasKit (WASM), which
 * `LoadSkiaWeb()` (see `app/_layout.tsx`) fetches from `/canvaskit.wasm`
 * at runtime. Expo web serves `public/` at the site root, so this copies
 * the binary there on every install rather than checking an 8 MB binary
 * into git. Native (Expo Go) needs none of this.
 */
const fs = require('fs');
const path = require('path');

const src = path.join(__dirname, '..', 'node_modules', 'canvaskit-wasm', 'bin', 'full', 'canvaskit.wasm');
const destDir = path.join(__dirname, '..', 'public');
const dest = path.join(destDir, 'canvaskit.wasm');

if (!fs.existsSync(src)) {
  console.warn('copy-canvaskit: canvaskit-wasm not installed yet, skipping (web target only).');
  process.exit(0);
}
fs.mkdirSync(destDir, { recursive: true });
fs.copyFileSync(src, dest);
console.log('copy-canvaskit: public/canvaskit.wasm ready.');
