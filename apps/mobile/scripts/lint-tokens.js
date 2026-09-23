#!/usr/bin/env node
/**
 * FIX BEFORE MERGE (independent review of PR #332): "read phoneTokens/
 * typography everywhere; extend lint-motion (or a sibling lint-tokens)
 * to fail on hex literals and fontSize literals outside design/."
 *
 * Scans app/ (the golden-path screens this checkpoint owns) for a raw
 * hex colour literal or a numeric `fontSize:` — both must be read from
 * `design/colors.ts` / `design/typography.ts` instead. Scoped to app/
 * only, not components/ (the Home-spike's own pre-existing components
 * carry the same debt in far greater volume — components/cards/
 * NuraCard.tsx's ACCENT map, MediaCard, ReminderCard, InsightCard,
 * BottomSheet and others all hard-code hex today; bringing every one of
 * them under this lint is real, larger work this pass does not do, and
 * widening SCAN_DIRS below without doing it first would just make
 * `make lint` fail everywhere at once).
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['app'].map((d) => path.join(ROOT, d));
const EXEMPT_FILES = new Set([
  path.join(ROOT, 'design/colors.ts'),
  path.join(ROOT, 'design/typography.ts'),
  path.join(ROOT, 'design/tokens.ts'),
]);

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;
const FONT_SIZE_RE = /fontSize\s*:\s*\d+(\.\d+)?/g;

const files = [];
function walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(tsx?|jsx?)$/.test(entry.name)) files.push(full);
  }
}
SCAN_DIRS.forEach(walk);

let violations = 0;
for (const file of files) {
  if (EXEMPT_FILES.has(file)) continue;
  const src = fs.readFileSync(file, 'utf8');
  const lines = src.split('\n');
  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('//') || trimmed.startsWith('*')) return; // comments/doc lines
    for (const re of [HEX_RE, FONT_SIZE_RE]) {
      re.lastIndex = 0;
      const m = re.exec(line);
      if (m) {
        console.error(`${path.relative(ROOT, file)}:${i + 1}  ${m[0]}  ${line.trim()}`);
        violations++;
      }
    }
  });
}

if (violations > 0) {
  console.error(
    `\n${violations} literal hex colour / fontSize found in app/ outside design/. Read from design/colors.ts / design/typography.ts instead.`
  );
  process.exit(1);
} else {
  console.log(`lint-tokens: clean (${files.length} files scanned in app/).`);
}
