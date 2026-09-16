import { describe, expect, it } from "vitest";
import { cueAt, parseVtt } from "../../src/feed/captions";

/** The backend's captions for a clip (`app.delivery.feed.clips.captions`), as it writes them. */
const VTT = [
  "WEBVTT",
  "Language: en",
  "",
  "1",
  "00:00:00.000 --> 00:00:02.600",
  "High blood pressure often has no signs.",
  "",
  "2",
  "00:00:02.600 --> 00:00:05.100",
  "Less salt and a daily walk help.",
  "",
].join("\n");

describe("a clip's captions", () => {
  it("are the backend's lines, each with when it is said, the header left out", () => {
    expect(parseVtt(VTT)).toEqual([
      { start: 0, end: 2.6, text: "High blood pressure often has no signs." },
      { start: 2.6, end: 5.1, text: "Less salt and a daily walk help." },
    ]);
  });

  it("show the line being said, and the last one once all is said", () => {
    const cues = parseVtt(VTT);
    expect(cueAt(cues, 0.5)?.text).toBe("High blood pressure often has no signs.");
    expect(cueAt(cues, 3)?.text).toBe("Less salt and a daily walk help.");
    expect(cueAt(cues, 9)?.text).toBe("Less salt and a daily walk help.");
    expect(cueAt([], 1)).toBeNull();
  });

  it("leave out a block that is not a cue, and read Windows line ends", () => {
    expect(parseVtt("WEBVTT\r\n\r\nNOTE a note\r\n\r\n00:00:01.000 --> 00:00:02.000\r\nOne.\r\n")).toEqual([{ start: 1, end: 2, text: "One." }]);
  });
});
