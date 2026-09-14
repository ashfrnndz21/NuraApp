import type { ComponentChildren, JSX } from "preact";
import { t } from "../../strings";
import { Hear } from "../../ui/components";

/** The pieces the onboarding steps share. A backend card carries its State id and its
 *  source line; every card has its spoken twin; decisions sit on paper. */

interface SheetProps {
  title?: string;
  /** Show the title at body size under a caption, or as the big line of the screen. */
  big?: string;
  caption?: string;
  lines?: readonly string[];
  source?: string;
  stateId?: string;
  glass?: boolean;
  settled?: boolean;
  extraClass?: string;
  /** What Hear reads; defaults to the caption-free lines shown. `false` for none. */
  hear?: readonly string[] | false;
  testId?: string;
  children?: ComponentChildren;
}

export function Sheet({ title, big, caption, lines = [], source, stateId, glass, settled, extraClass, hear, testId, children }: SheetProps): JSX.Element {
  const spoken = hear === false ? [] : (hear ?? [title, big, ...lines].filter((line): line is string => Boolean(line)));
  const classes = ["tile", glass ? "glass" : "paper", settled && "settled", extraClass].filter(Boolean).join(" ");
  return (
    <section class={classes} data-testid={testId} data-state-id={stateId}>
      {caption && <p class="caption">{caption}</p>}
      {title && <h2 class="title">{title}</h2>}
      {big && <p class="big-line">{big}</p>}
      {lines.length > 0 && (
        <div class="lines">
          {lines.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      )}
      {children}
      {source && (
        <p class="provenance" data-testid="source">
          {source}
        </p>
      )}
      {spoken.length > 0 && <Hear lines={spoken} />}
    </section>
  );
}

export function StepTitle({ title }: { title: string }): JSX.Element {
  return <h1 class="title hero">{title}</h1>;
}

export function Status({ text, testId }: { text: string | null; testId?: string }): JSX.Element {
  return (
    <p class="status" role="status" aria-live="polite" data-testid={testId}>
      {text ?? ""}
    </p>
  );
}

interface CaptureProps {
  onFile: (file: File) => void;
  busy: boolean;
  /** The words on the camera button: "Take a photo", or the gap card's own action. */
  photoLabel: string;
  plum?: boolean;
  withFile?: boolean;
}

/** The camera, and a file instead. `capture="environment"` asks the phone for the back
 *  camera straight away; the second button opens the picker, where a PDF can be chosen. */
export function Capture({ onFile, busy, photoLabel, plum = true, withFile = true }: CaptureProps): JSX.Element {
  const chosen = (event: Event) => {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (file) onFile(file);
  };
  return (
    <>
      <label class={plum ? "pill plum" : "pill"} data-testid="take-photo" aria-disabled={busy}>
        {photoLabel}
        <input type="file" accept="image/*,application/pdf" capture="environment" disabled={busy} onChange={chosen} data-testid="photo-input" />
      </label>
      {withFile && (
        <label class="pill" data-testid="choose-file" aria-disabled={busy}>
          {t().onboarding.records.file}
          <input type="file" accept="image/*,application/pdf" disabled={busy} onChange={chosen} data-testid="file-input" />
        </label>
      )}
    </>
  );
}
