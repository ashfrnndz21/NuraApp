/// <reference lib="webworker" />
import "./push"; // the Web Push handler, its own module (ADR 0001)
/** Nura's service worker: keeps the shell, never the health data.
 *
 *  On install it caches every file the build emitted (`__PRECACHE__` is filled in by the
 *  Vite plugin in vite.config.ts) plus the app's start URL, so the app opens offline from
 *  the first visit on. Anything under /api is the person's health data and goes to the
 *  network only; the app keeps its own last Today page in IndexedDB. The worker imports
 *  nothing, so it is one plain script. */

declare const __PRECACHE__: string[] | undefined;

const sw = self as unknown as ServiceWorkerGlobalScope;
const BASE = new URL(sw.registration.scope).pathname; // "/app/"
const SHELL: string[] = typeof __PRECACHE__ === "undefined" ? [] : __PRECACHE__;
const START = [BASE, `${BASE}index.html`, `${BASE}manifest.webmanifest`];
const VERSION = hash(SHELL.join("|"));
const CACHE = `nura-shell-${VERSION}`;

function hash(text: string): string {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0).toString(16);
}

sw.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      await cache.addAll([...new Set([...START, ...SHELL])]);
      await sw.skipWaiting();
    }),
  );
});

sw.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name))))
      .then(() => sw.clients.claim()),
  );
});

sw.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== sw.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // health data: network only, never cached here
  if (!url.pathname.startsWith(BASE)) return;

  if (request.mode === "navigate") {
    // The page itself: the network when it is there, the cached shell when it is not.
    event.respondWith(
      fetch(request)
        .then((response) => {
          void caches.open(CACHE).then((cache) => cache.put(`${BASE}index.html`, response.clone()));
          return response;
        })
        .catch(async () => (await caches.match(`${BASE}index.html`)) ?? Response.error()),
    );
    return;
  }

  // Assets are content-hashed: cache first, then the network, and keep what came back.
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ??
        fetch(request).then((response) => {
          if (response.ok) void caches.open(CACHE).then((cache) => cache.put(request, response.clone()));
          return response;
        }),
    ),
  );
});
