import { render } from "preact";
import "./ui/base.css";
import { App } from "./app";
import { registerServiceWorker } from "./offline/register";
import { restoreSession } from "./store/session";

registerServiceWorker();
void restoreSession();
render(<App />, document.getElementById("app")!);
