import { render } from "preact";
import "./ui/base.css";
import "./ui/design.css";
import "./ui/warm.css";
import { App } from "./app";
import { screen } from "./flow";
import { registerServiceWorker } from "./offline/register";
import { installRestoreGuard } from "./restoreGuard";
import { learnDeployment } from "./store/deployment";
import { restored, restoreSession } from "./store/session";
import { DemoBanner } from "./ui/components";

// #142: armed before anything else runs, so a finger already down when the app reopens can
// never register against whatever the restore check lands the screen on a moment later.
installRestoreGuard(document, () => !restored.value || screen.value.name === "loading");
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
