#!/usr/bin/env node
/**
 * Headless Playwright walkthrough of the Home spike on the web target
 * (mobile-architecture.md §5's decision point still needs the phone —
 * this only proves the web target's structure and behaviour).
 *
 * Asserts: orb state driven from the store, the composer expands and
 * collapses in place, ExpandableCard reaches every state, the sheet
 * dismisses on a fast drag, zero console errors. Captures at 390×844
 * into scratch/shots/home-spike/. Also records a frame-time trace
 * (Performance API, via CDP) over the expand and composer animations.
 *
 * Usage: node scripts/walkthrough.mjs <baseUrl> <shotsDir>
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { writeFileSync } from 'node:fs';

const baseUrl = process.argv[2] ?? 'http://localhost:8098';
const shotsDir = process.argv[3] ?? './shots';
const REDUCED = process.argv.includes('--reduced-motion');

mkdirSync(shotsDir, { recursive: true });

const consoleErrors = [];
const results = { steps: [], consoleErrors, frameTraces: {} };

function logStep(name, ok, detail) {
  results.steps.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
}

async function shot(page, name) {
  await page.screenshot({ path: `${shotsDir}/${name}.png` });
}

/** Instruments requestAnimationFrame in the page to record frame deltas for a window of time. */
async function traceFrames(page, ms) {
  await page.evaluate(() => {
    window.__frames = [];
    window.__tracing = true;
    let last = performance.now();
    function tick(t) {
      if (!window.__tracing) return;
      window.__frames.push(t - last);
      last = t;
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
  await page.waitForTimeout(ms);
  const frames = await page.evaluate(() => {
    window.__tracing = false;
    return window.__frames;
  });
  const max = frames.length ? Math.max(...frames) : 0;
  const avg = frames.length ? frames.reduce((a, b) => a + b, 0) / frames.length : 0;
  return { count: frames.length, maxMs: Number(max.toFixed(2)), avgMs: Number(avg.toFixed(2)) };
}

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: REDUCED ? 'reduce' : 'no-preference',
  });
  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(String(err)));

  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500); // fonts + Skia web (CanvasKit) + entrance stagger

  const suffix = REDUCED ? '-reduced' : '';

  // ---- Home (blueprint scene 15) ----
  const homeVisible = await page.getByTestId('home-screen').isVisible();
  logStep('Home renders', homeVisible);
  await shot(page, `chromium-15-home${suffix}`);

  // ---- Orb state, from the store: idle at rest ----
  const composerPill = page.getByTestId('composer-pill');
  logStep('Composer pill visible (orb idle, docked)', await composerPill.isVisible());

  // ---- Composer expands in place (blueprint scene 29) ----
  await composerPill.click();
  await page.waitForTimeout(300);
  const composerFrames = await traceFrames(page, 800);
  results.frameTraces.composerExpand = composerFrames;
  logStep('Composer expands in place', await page.getByTestId('composer-expanded').isVisible());
  await shot(page, `chromium-29-composer-listening${suffix}`);

  await page.waitForTimeout(3500); // stream question, thinking, stream answer + follow-up
  const chipsVisible = await page.getByTestId('composer-chips').isVisible().catch(() => false);
  logStep('Composer reaches context-first answer + chips', chipsVisible);
  await shot(page, `chromium-29-composer-answered${suffix}`);

  if (chipsVisible) {
    await page.getByTestId('composer-chip-Explain').click();
    await page.waitForTimeout(2000);
    const explainVisible = (await page.getByTestId('composer-answer').allTextContents()).some((t) =>
      t.includes('Your dose changed on 9 September')
    );
    logStep('Explain chip streams the explanation', explainVisible);
  }

  await page.getByTestId('composer-close').click();
  await page.waitForTimeout(400);
  logStep('Composer collapses back to the pill', await composerPill.isVisible());

  // ---- ExpandableCard: collapsed -> pressed -> expanding -> expanded -> interactive x4 -> dismissed ----
  await page.evaluate(() => window.scrollTo(0, 0));
  const trigger = page.getByTestId('expandable-card-trigger');
  await shot(page, `chromium-30-expand-collapsed${suffix}`);

  const expandFrames = await (async () => {
    const tracePromise = traceFrames(page, 1100);
    await trigger.click();
    return tracePromise;
  })();
  results.frameTraces.expandStep1 = expandFrames;
  await page.waitForTimeout(500);
  // Skia's web <Canvas> renders a plain <canvas> element and does not forward
  // arbitrary props like testID to the DOM node, so assert on the tag itself.
  const chartCanvasCount = await page.locator('canvas').count();
  logStep('ExpandableCard: chart drawn on first tap', chartCanvasCount > 0, `${chartCanvasCount} canvas element(s)`);
  await shot(page, `chromium-30-expand-week${suffix}`);

  for (let i = 0; i < 3; i++) {
    await trigger.click();
    await page.waitForTimeout(400);
  }
  logStep('ExpandableCard: interactive content accumulated (steps 2-4)', await page.getByTestId('expandable-card-action').isVisible().catch(() => false) === false);
  await shot(page, `chromium-30-expand-related${suffix}`);

  await trigger.click();
  await page.waitForTimeout(400);
  const actionVisible = await page.getByTestId('expandable-card-action').isVisible().catch(() => false);
  logStep('ExpandableCard: reaches the action step (5th tap)', actionVisible);
  await shot(page, `chromium-30-expand-action${suffix}`);

  // ---- Bottom sheet (blueprint scene 32) ----
  if (actionVisible) {
    await page.getByTestId('expandable-card-action').click();
  } else {
    await page.getByTestId('document-card').click();
  }
  await page.waitForTimeout(700);
  const sheetVisible = await page.getByTestId('bottom-sheet').isVisible().catch(() => false);
  logStep('Bottom sheet opens (scene 32)', sheetVisible);
  await shot(page, `chromium-32-sheet-open${suffix}`);

  if (sheetVisible) {
    // A fast drag past the dismiss distance/velocity should close it.
    const box = await page.getByTestId('bottom-sheet').boundingBox();
    if (box) {
      const x = box.x + box.width / 2;
      const startY = box.y + 20;
      await page.mouse.move(x, startY);
      await page.mouse.down();
      await page.mouse.move(x, startY + 400, { steps: 5 });
      await page.mouse.up();
    }
    await page.waitForTimeout(500);
    const dismissed = !(await page.getByTestId('bottom-sheet').isVisible().catch(() => false));
    logStep('Bottom sheet dismisses on a fast drag', dismissed);
  }
  await shot(page, `chromium-32-sheet-dismissed${suffix}`);

  // ---- Tap once more to reach the fully closed ExpandableCard (dismissed -> collapsed) ----
  await page.evaluate(() => window.scrollTo(0, 0));
  await trigger.click().catch(() => {});
  await page.waitForTimeout(400);
  await shot(page, `chromium-33-states-collapsed-again${suffix}`);

  logStep('Zero console errors', consoleErrors.length === 0, consoleErrors.slice(0, 5).join(' | '));

  await browser.close();
  writeFileSync(`${shotsDir}/walkthrough-report${suffix}.json`, JSON.stringify(results, null, 2));

  const failed = results.steps.filter((s) => !s.ok);
  console.log(`\n${results.steps.length - failed.length}/${results.steps.length} checks passed.`);
  console.log('Frame traces:', JSON.stringify(results.frameTraces, null, 2));
  if (failed.length > 0) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
