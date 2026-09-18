import type { JSX } from "preact";
import type { NavigationDraftOut } from "../api/types";
import type { Strings } from "../strings";
import { Sheet } from "../ui/kit";

/** Care navigation with drafted messages (T3): "Draft a message" opens this sheet with the
 *  draft for one need (`POST /profiles/{id}/navigation/drafts/{need_id}`) — never sent by
 *  Nura. He or his chief edits it here, then sends it themselves: by text message or
 *  WhatsApp, from a link built from the provider's own phone, or by "Copy" when there is
 *  none on file. A pure body — the fetch, the editable text and "Copied" are its caller's
 *  state, so this is one prop away from a test, the same as `CareBody`/`ClipMedia`. */
export function NavigationDraftSheet({
  s,
  open,
  draft,
  loading,
  error,
  text,
  onTextChange,
  copied,
  onCopy,
  onClose,
}: {
  s: Strings;
  open: boolean;
  draft: NavigationDraftOut | null;
  loading: boolean;
  error: boolean;
  text: string;
  onTextChange: (value: string) => void;
  copied: boolean;
  onCopy: () => void;
  onClose: () => void;
}): JSX.Element {
  return (
    <Sheet title={s.navigation.sheetTitle} open={open} onClose={onClose} closeLabel={s.shell.close} testId="navigation-draft-sheet">
      {error && <p data-testid="navigation-draft-error">{s.navigation.error}</p>}
      {loading && !error && <p data-testid="navigation-draft-loading">{s.navigation.loading}</p>}
      {draft && (
        <>
          <textarea
            class="navigation-draft-text"
            value={text}
            onInput={(event) => onTextChange((event.target as HTMLTextAreaElement).value)}
            data-testid="navigation-draft-text"
          />
          <nav class="place-rows" aria-label={s.navigation.sheetTitle}>
            <button type="button" class="place-row" onClick={onCopy} data-testid="navigation-draft-copy">
              {s.navigation.copy}
            </button>
            {draft.links.map((link) => (
              <a key={link.href} class="place-row" href={link.href} data-testid={`navigation-draft-link-${link.kind}`}>
                {link.kind === "sms" ? s.navigation.sendBySms : s.navigation.sendByWhatsApp}
              </a>
            ))}
          </nav>
          {copied && <p data-testid="navigation-draft-copied">{s.navigation.copied}</p>}
          {draft.copy_only && <p data-testid="navigation-draft-copy-only">{s.navigation.copyOnly}</p>}
        </>
      )}
    </Sheet>
  );
}
