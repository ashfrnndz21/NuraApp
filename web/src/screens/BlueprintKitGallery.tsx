import { useState } from "preact/hooks";
import type { JSX } from "preact";
import { ActionSheet, ConnectionRow, Flag, Glass, Orb, RangeBar, Reveal, RevealGroup, SoftText, StatusLine, ThreeStateButton } from "../ui/kit";

/** `#/blueprint-kit` — a review gallery of the dusk-glass kit (web/src/ui/kit), for the P1 PR's
 *  reviewer, dev and demo builds only (gated in `main.tsx`, never linked from the real app). Every
 *  string and figure on this page is gallery fixture data, invented for the demonstration — never
 *  a real person's papers, never something the real app would say. */

const STATUSES = ["Reading your medicines", "Checking your visits", "Looking at your history"];

function OrbSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-orb-h">
      <h2 id="gallery-orb-h">Orb</h2>
      <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
        <Orb size="lg" testId="gallery-orb-lg" />
        <Orb testId="gallery-orb-sm" />
        <Orb thinking testId="gallery-orb-thinking" />
      </div>
    </section>
  );
}

function StatusLineSection(): JSX.Element {
  const [at, setAt] = useState(0);
  return (
    <section aria-labelledby="gallery-status-h">
      <h2 id="gallery-status-h">StatusLine</h2>
      <p>
        <StatusLine text={STATUSES[at % STATUSES.length]!} testId="gallery-status" />
      </p>
      <button type="button" class="btn" onClick={() => setAt((n) => n + 1)} data-testid="gallery-status-next">
        Next status
      </button>
    </section>
  );
}

const STREAM_FULL = "Your health, in *plain* words.";
const STREAM_STEPS = ["Your", "Your health,", "Your health, in", "Your health, in *plain*", "Your health, in *plain* words."];

function SoftTextSection(): JSX.Element {
  const [step, setStep] = useState(0);
  const text = STREAM_STEPS[step] ?? STREAM_FULL;
  const previousText = step > 0 ? (STREAM_STEPS[step - 1] ?? "") : "";
  return (
    <section aria-labelledby="gallery-softtext-h">
      <h2 id="gallery-softtext-h">SoftText</h2>
      <SoftText as="p" text={text} previousText={previousText} testId="gallery-softtext" />
      <button type="button" class="btn" disabled={step >= STREAM_STEPS.length - 1} onClick={() => setStep((n) => Math.min(n + 1, STREAM_STEPS.length - 1))} data-testid="gallery-softtext-next">
        Stream more
      </button>
    </section>
  );
}

function RevealSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-reveal-h">
      <h2 id="gallery-reveal-h">Reveal / RevealGroup</h2>
      <RevealGroup testId="gallery-reveal-group">
        {[
          <Glass key="a" shape="row">
            <p>First row</p>
          </Glass>,
          <Glass key="b" shape="row">
            <p>Second row</p>
          </Glass>,
          <Glass key="c" shape="row">
            <p>Third row</p>
          </Glass>,
        ]}
      </RevealGroup>
      <Reveal testId="gallery-reveal-single">
        <p>One piece of structure, on its own.</p>
      </Reveal>
    </section>
  );
}

function GlassSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-glass-h">
      <h2 id="gallery-glass-h">Glass</h2>
      <Glass testId="gallery-glass-card">
        <p>A card, 26px radius.</p>
      </Glass>
      <Glass shape="row" testId="gallery-glass-row">
        <p>A row, 18px radius.</p>
      </Glass>
    </section>
  );
}

function RangeBarSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-range-h">
      <h2 id="gallery-range-h">RangeBar</h2>
      <RangeBar bandStart={0} bandWidth={65} markerAt={76} tone="attention" label="Total cholesterol, 6.1 mmol/L, below 5.2" testId="gallery-range-attention" />
      <RangeBar bandStart={40} bandWidth={20} markerAt={44} tone="ok" label="Good cholesterol, 1.1 mmol/L, above 1.0" testId="gallery-range-ok" />
    </section>
  );
}

function FlagSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-flag-h">
      <h2 id="gallery-flag-h">Flag</h2>
      <div style={{ display: "flex", gap: "8px" }}>
        <Flag state="ok" testId="gallery-flag-ok">
          In range
        </Flag>
        <Flag state="attention" testId="gallery-flag-attention">
          Above
        </Flag>
        <Flag state="question" testId="gallery-flag-question">
          Ask your doctor
        </Flag>
      </div>
    </section>
  );
}

function ConnectionRowSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-connection-h">
      <h2 id="gallery-connection-h">ConnectionRow</h2>
      <ConnectionRow name="Dr Tan" line="Cardiologist · Gleneagles" onClick={() => {}} testId="gallery-connection-clickable" />
      <ConnectionRow name="Mei" line="Daughter" testId="gallery-connection-plain" />
    </section>
  );
}

function ThreeStateButtonSection(): JSX.Element {
  return (
    <section aria-labelledby="gallery-tsb-h">
      <h2 id="gallery-tsb-h">ThreeStateButton</h2>
      <ThreeStateButton
        label="Copy"
        busyLabel="Copying…"
        doneLabel="Copied"
        onAct={() => new Promise((resolve) => setTimeout(resolve, 250))}
        testId="gallery-tsb"
      />
    </section>
  );
}

/** One composed sample "conversation" (fixture data only): a status line, a SoftText headline,
 *  a RevealGroup of rows with RangeBar and Flag, actions, and an ActionSheet. */
function SampleConversation(): JSX.Element {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(true);
  return (
    <section aria-labelledby="gallery-sample-h">
      <h2 id="gallery-sample-h">Sample conversation</h2>
      <p class="caption">Sample person and sample papers — fixture data, inside this gallery only.</p>
      {busy && <StatusLine text="Reading page 4 of 12" testId="gallery-sample-status" />}
      {/* Never a judgement on a value — only ever compared with the range printed on the paper
       *  (CLAUDE.md: no diagnosis, nothing beyond what the paper itself says). "Above"/"In range"
       *  (the Flag chips below) are the backend's own words for that comparison; this headline
       *  says the same thing the same way, not "high"/"low"/"normal"/"abnormal". */}
      <SoftText as="h3" text="One reading is outside the range on the *paper.*" testId="gallery-sample-headline" />
      <RevealGroup testId="gallery-sample-rows">
        {[
          <Glass key="chol" shape="row">
            <RangeBar bandStart={0} bandWidth={65} markerAt={76} tone="attention" label="Total cholesterol, 6.1 mmol/L, below 5.2" />
            <Flag state="attention">Above</Flag>
          </Glass>,
          <Glass key="hdl" shape="row">
            <RangeBar bandStart={40} bandWidth={20} markerAt={44} tone="ok" label="Good cholesterol, 1.1 mmol/L, above 1.0" />
            <Flag state="ok">In range</Flag>
          </Glass>,
        ]}
      </RevealGroup>
      <div class="action-sheet-actions">
        <button type="button" class="btn light" onClick={() => setBusy(false)} data-testid="gallery-sample-finish">
          Finish reading
        </button>
        <button type="button" class="btn" onClick={() => setOpen(true)} data-testid="gallery-open-sheet">
          Ask a question
        </button>
      </div>
      <ActionSheet
        open={open}
        title="Ask about your cholesterol"
        sub="A fixture sheet, for the gallery only"
        notNowLabel="Not now"
        onClose={() => setOpen(false)}
        cta={{ label: "Add to my questions", busyLabel: "Adding…", doneLabel: "Added", onAct: () => new Promise((resolve) => setTimeout(resolve, 400)) }}
        testId="gallery-sample-sheet"
      >
        <p>Nura keeps a note for your next visit, in your own words.</p>
      </ActionSheet>
    </section>
  );
}

export function BlueprintKitGallery(): JSX.Element {
  return (
    <main class="atmosphere-page" style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "28px", color: "var(--ink)" }} data-testid="blueprint-kit-gallery">
      <h1>Blueprint kit</h1>
      <p class="caption">Every component in web/src/ui/kit, in its states, on the atmosphere. Review only — never linked from the app.</p>
      <OrbSection />
      <StatusLineSection />
      <SoftTextSection />
      <RevealSection />
      <GlassSection />
      <RangeBarSection />
      <FlagSection />
      <ConnectionRowSection />
      <ThreeStateButtonSection />
      <SampleConversation />
    </main>
  );
}
