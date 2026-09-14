import { render } from "preact";
import "./ui/base.css";
import { App } from "./app";
import { setMockTransport } from "./api/client";
import { registerServiceWorker } from "./offline/register";
import { restoreSession } from "./store/session";

/** `VITE_API_MOCK=1` (dev only, `make web-mock`) answers E01's onboarding routes from
 *  `src/api/mock/` until the backend lands; everything else still goes to the API. Vite
 *  replaces the variable at build time, so a normal build drops this branch and the mock
 *  module with it. */
async function installMock(): Promise<void> {
  if (import.meta.env.VITE_API_MOCK !== "1") return;
  const { mockTransport } = await import("./api/mock");
  setMockTransport(mockTransport);
  (window as unknown as { __NURA_API_MOCK__?: boolean }).__NURA_API_MOCK__ = true;
}

void installMock().then(() => {
  registerServiceWorker();
  void restoreSession();
  render(<App />, document.getElementById("app")!);
});
