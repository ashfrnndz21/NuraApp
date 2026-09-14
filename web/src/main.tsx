import { render } from "preact";
import "./ui/base.css";
import { App } from "./app";
import { registerServiceWorker } from "./offline/register";
import { restoreSpeed } from "./player/voice";
import { restoreSession } from "./store/session";

registerServiceWorker();
void restoreSession();
void restoreSpeed();
render(<App />, document.getElementById("app")!);
