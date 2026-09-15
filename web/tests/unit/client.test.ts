import { afterEach, describe, expect, it, vi } from "vitest";
import { api, Refused } from "../../src/api/client";

/** A "no" is always a refusal the screen can say, whatever the body it came in. */

afterEach(() => vi.unstubAllGlobals());

function answering(status: number, body: string, type = "text/plain") {
  vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8124" } });
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status, headers: { "Content-Type": type } })));
}

describe("a refusal", () => {
  it("is the backend's refusal by its name when the body carries one", async () => {
    answering(413, JSON.stringify({ refusal: "PhotoTooLarge" }), "application/json");
    await expect(api("/profiles/p/photos", { method: "POST", body: {} })).rejects.toMatchObject({ refusal: "PhotoTooLarge", status: 413 });
  });

  it("is TooLarge when a layer in front of the app answers 413 with a page that is not JSON", async () => {
    answering(413, "<html><body>Request Entity Too Large</body></html>", "text/html");
    const failure = await api("/profiles/p/photos", { method: "POST", body: {} }).catch((each: unknown) => each);
    expect(failure).toBeInstanceOf(Refused);
    expect(failure).toMatchObject({ refusal: "TooLarge", status: 413 });
  });

  it("is HttpError for any other bare no, and never a crash on the body", async () => {
    answering(502, "Bad Gateway");
    await expect(api("/me")).rejects.toMatchObject({ refusal: "HttpError", status: 502 });
  });
});
