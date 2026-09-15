import { render } from "preact";
import "../ui/base.css";
import { learnDeployment } from "../store/deployment";
import { deviceLanguage, language } from "../strings";
import { DemoBanner } from "../ui/components";
import { ReviewApp } from "./ReviewApp";

/** The staff page (E22-04): its own entry, never linked from the patient app, no service
 *  worker, nothing kept on the device but the staff token for this tab. */
language.value = deviceLanguage(typeof navigator === "undefined" ? [] : (navigator.languages ?? [navigator.language]));
document.documentElement.lang = language.value;
// On a demo deployment (ADR 0008) the banner is first here too, as on every patient screen.
void learnDeployment();
render(
  <>
    <DemoBanner />
    <ReviewApp />
  </>,
  document.getElementById("app")!,
);
