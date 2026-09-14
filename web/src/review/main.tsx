import { render } from "preact";
import "../ui/base.css";
import { deviceLanguage, language } from "../strings";
import { ReviewApp } from "./ReviewApp";

/** The staff page (E22-04): its own entry, never linked from the patient app, no service
 *  worker, nothing kept on the device but the staff token for this tab. */
language.value = deviceLanguage(typeof navigator === "undefined" ? [] : (navigator.languages ?? [navigator.language]));
document.documentElement.lang = language.value;
render(<ReviewApp />, document.getElementById("app")!);
