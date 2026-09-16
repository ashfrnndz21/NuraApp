import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

/** The design review's screenshots (D1): the same app, server and clock as the end-to-end
 *  suite, a different folder. Not a gate — `npm run shots` writes pictures for a person to look
 *  at, into NURA_DESIGN_SHOTS. */
export default defineConfig({ ...base, testDir: "tests/visual", reporter: "list", timeout: 180_000 });
