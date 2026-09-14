/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";

/** Where the app lives on its origin: the backend serves `web/dist` at `/app` (see
 *  `backend/app/channels/api/__init__.py`), and the dev server keeps the same base so the
 *  service worker's scope and every asset path are the same in both. */
export const BASE = "/app/";

/** The API is at `/api` on the same origin. In dev, Vite proxies it to `make dev`. */
const API_TARGET = process.env.NURA_API ?? "http://127.0.0.1:8000";

/** `/` on the dev server goes to the app, so http://127.0.0.1:5173 is enough to type. */
function redirectRootToApp(): Plugin {
  return {
    name: "nura-redirect-root",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === "/" || req.url === "") {
          res.statusCode = 302;
          res.setHeader("Location", BASE);
          res.end();
          return;
        }
        next();
      });
    },
  };
}

/** The service worker is built as its own entry, `sw.js`, and told what the shell is: this
 *  plugin fills `__PRECACHE__` in it with every file the build emitted, so the first visit
 *  caches the whole shell and the app opens offline from then on. */
function precacheManifest(): Plugin {
  return {
    name: "nura-precache-manifest",
    generateBundle(_options, bundle) {
      const files = Object.keys(bundle)
        .filter((name) => name !== "sw.js")
        .map((name) => BASE + name);
      const sw = bundle["sw.js"];
      if (sw && sw.type === "chunk") {
        sw.code = sw.code.replaceAll("__PRECACHE__", JSON.stringify(files));
      }
    },
  };
}

export default defineConfig({
  base: BASE,
  plugins: [redirectRootToApp(), precacheManifest()],
  esbuild: { jsx: "automatic", jsxImportSource: "preact" },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: API_TARGET, changeOrigin: false } },
  },
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      input: { main: "index.html", sw: "src/sw/sw.ts" },
      output: {
        entryFileNames: (chunk) => (chunk.name === "sw" ? "sw.js" : "assets/[name]-[hash].js"),
        // The worker imports nothing, so nothing is shared with it; keep it that way.
        manualChunks: undefined,
      },
    },
  },
  test: {
    environment: "node",
    include: ["tests/unit/**/*.test.ts"],
  },
});
