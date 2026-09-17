import { render } from "preact";
import "./ui/base.css";
import "./ui/design.css";
import "./ui/warm.css";
import { App } from "./app";
import { registerServiceWorker } from "./offline/register";
import { learnDeployment } from "./store/deployment";
import { restoreSession } from "./store/session";
import { DemoBanner } from "./ui/components";

registerServiceWorker();
void restoreSession();
void learnDeployment();
render(
  <>
    <DemoBanner />
    <App />
  </>,
  document.getElementById("app")!,
);
