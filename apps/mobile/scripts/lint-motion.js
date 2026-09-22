#!/usr/bin/env node
/**
 * "A lint fails any literal duration in components" (spike brief) /
 * "Centralised tokens, nothing hard-coded" (design-build-2.md §24).
 *
 * Scans components/, app/, features/, lib/ and design/ for numeric
 * literals passed as an animation duration/delay — the second argument of
 * withTiming, withDelay, withRepeat's iteration count is fine but its
 * config isn't, Animated.timing's `duration:` field, and raw setTimeout
 * calls used to fake a wait. Every one of those must read from
 * `design/motion.ts` (section 35, the single source of truth) — or
 * `components/motion/motionTokens.ts`/`springs.ts`/`transitions.ts`,
 * which re-export/are built from it.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SCAN_DIRS = ['components', 'app', 'features', 'lib', 'design'].map((d) => path.join(ROOT, d));
const EXEMPT_FILES = new Set([
  path.join(ROOT, 'design/motion.ts'),
  path.join(ROOT, 'components/motion/motionTokens.ts'),
  path.join(ROOT, 'components/motion/springs.ts'),
  path.join(ROOT, 'components/motion/transitions.ts'),
]);

const VIOLATION_PATTERNS = [
  { name: 'duration: <number>', re: /duration\s*:\s*\d+(?!\s*[)\w])/g },
  { name: 'withTiming(_, <number>', re: /withTiming\([^,]+,\s*\d+\s*[,)]/g },
  { name: 'withDelay(<number>', re: /withDelay\(\s*\d+/g },
  { name: 'setTimeout(_, <number>) outside lib/ai', re: /setTimeout\([^,]+,\s*\d{2,}\s*\)/g },
];

/** @type {string[]} */
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
    // A line that itself imports/re-exports from motionTokens etc. is fine to mention numbers.
    if (/from ['"].*motion(Tokens|s)?['"]/.test(line)) return;
    for (const { name, re } of VIOLATION_PATTERNS) {
      re.lastIndex = 0;
      if (re.test(line)) {
        console.error(`${path.relative(ROOT, file)}:${i + 1}  literal ${name} — ${line.trim()}`);
        violations++;
      }
    }
  });
}

if (violations > 0) {
  console.error(`\n${violations} literal duration(s) found outside components/motion/. Read from motionTokens.ts / springs.ts / transitions.ts instead.`);
  process.exit(1);
} else {
  console.log(`lint-motion: clean (${files.length} files scanned).`);
}
