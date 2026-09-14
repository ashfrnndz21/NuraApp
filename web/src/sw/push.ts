/// <reference lib="webworker" />
/** The push handler of Nura's service worker (Web Push, ADR 0001). A push carries one line —
 *  "Nura has something for you.", in his language — and an id; this shows that line and
 *  nothing else, and a tap opens the app at the card the id names, which the app then reads
 *  from its region. No health word is ever in a push. Its own module, imported by sw.ts, so
 *  the offline work there and this do not meet. */

const worker = self as unknown as ServiceWorkerGlobalScope;

interface PushPayload {
  text?: unknown;
  id?: unknown;
}

/** Only for a push that cannot be read; the backend always sends the line in his language. */
const FALLBACK = "Nura has something for you.";

worker.addEventListener("push", (event) => {
  let payload: PushPayload = {};
  try {
    payload = (event.data?.json() ?? {}) as PushPayload;
  } catch {
    payload = {};
  }
  const text = typeof payload.text === "string" && payload.text ? payload.text : FALLBACK;
  const id = typeof payload.id === "string" ? payload.id : "";
  event.waitUntil(worker.registration.showNotification("Nura", { body: text, tag: id || "nura", data: { id } }));
});

worker.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const id = (event.notification.data as { id?: string } | null)?.id ?? "";
  const base = new URL(worker.registration.scope).pathname;
  const target = id ? `${base}?card=${encodeURIComponent(id)}` : base;
  event.waitUntil(
    (async () => {
      const open = await worker.clients.matchAll({ type: "window", includeUncontrolled: true });
      const first = open[0] as WindowClient | undefined;
      if (first) {
        await first.focus();
        if (id) await first.navigate(target).catch(() => undefined);
        return;
      }
      await worker.clients.openWindow(target);
    })(),
  );
});

export {};
