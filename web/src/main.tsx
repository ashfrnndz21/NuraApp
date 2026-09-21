import { render } from "preact";
import type { JSX } from "preact";
import "./ui/base.css";
import "./ui/design.css";
import "./ui/warm.css";
import "./ui/onboarding.css";
import { App } from "./app";
import { screen } from "./flow";
import { isBlueprintKitRoute } from "./gallery";
import { registerServiceWorker } from "./offline/register";
import { installRestoreGuard } from "./restoreGuard";
import { BlueprintKitGallery } from "./screens/BlueprintKitGallery";
import { demo, dev, learnDeployment } from "./store/deployment";
import { restored, restoreSession } from "./store/session";
import { DemoBanner } from "./ui/components";

// #142: armed before anything else runs, so a finger already down when the app reopens can
// never register against whatever the restore check lands the screen on a moment later.
installRestoreGuard(document, () => !restored.value || screen.value.name === "loading");
registerServiceWorker();
void restoreSession();
void learnDeployment();

/** `#/blueprint-kit` (P1 of the redesign): a review gallery of the dusk-glass kit, dev/demo only
 *  — `learnDeployment()` above sets `demo`/`dev` asynchronously, so this re-evaluates once they
 *  land (a plain signal read inside a component re-renders it, the same way every other screen
 *  here reacts to a store signal). Never linked from the app; if the hash is set but this is
 *  neither a demo nor a dev deployment, the real app renders underneath it instead. */
function Root(): JSX.Element {
  if (isBlueprintKitRoute() && (demo.value || dev.value)) return <BlueprintKitGallery />;
  return (
    <>
      <DemoBanner />
      <App />
    </>
  );
}

render(<Root />, document.getElementById("app")!);
