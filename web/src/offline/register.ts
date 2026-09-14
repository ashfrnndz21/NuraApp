/** Register the service worker from the built app. In dev Vite serves the source and the
 *  worker is not built, so nothing is registered there; the offline behaviour is proven
 *  against the build the backend serves at /app (see playwright.config.ts). */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return;
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  const url = `${import.meta.env.BASE_URL}sw.js`;
  navigator.serviceWorker.register(url, { scope: import.meta.env.BASE_URL }).catch(() => {
    /* the app works without it; it just does not open offline */
  });
}

/** iOS Safari, not yet added to the home screen: the moment to say how. */
export function wantsHomeScreenHint(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) && !/CriOS|FxiOS/.test(ua);
  const standalone = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !standalone;
}
