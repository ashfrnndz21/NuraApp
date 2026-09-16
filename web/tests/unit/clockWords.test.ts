import { describe, expect, it } from "vitest";
import { en } from "../../src/strings/en";
import { fill } from "../../src/strings";
import { clockWords } from "../../src/today/model";

const at = (iso: string) => new Date(iso);

describe("the hour in his words (plain words, rule 5; the backend's say_clock)", () => {
  it("the hour, half past, and the minutes — twelve-hour, never a colon, on the region's clock", () => {
    expect(clockWords(at("2026-09-14T02:00:00Z"), "en", "Asia/Singapore")).toBe("10 in the morning");
    expect(clockWords(at("2026-09-14T11:30:00Z"), "en", "Asia/Singapore")).toBe("half past 7 in the evening");
    expect(clockWords(at("2026-09-14T00:05:00Z"), "en", "Asia/Singapore")).toBe("8.05 in the morning");
    expect(clockWords(at("2026-09-14T06:15:00Z"), "en", "Asia/Singapore")).toBe("2.15 in the afternoon");
    expect(clockWords(at("2026-09-14T15:00:00Z"), "en", "Asia/Singapore")).toBe("11 at night");
    expect(fill(en.held.tapped, { time: clockWords(at("2026-09-14T00:05:00Z"), "en", "Asia/Singapore") })).toBe("You tapped this at 8.05 in the morning.");
  });
  it("in Malay and Chinese, in the backend's words", () => {
    expect(clockWords(at("2026-09-14T00:00:00Z"), "ms", "Asia/Kuala_Lumpur")).toBe("pukul 8 pagi");
    expect(clockWords(at("2026-09-14T00:05:00Z"), "ms", "Asia/Kuala_Lumpur")).toBe("pukul 8.05 pagi");
    expect(clockWords(at("2026-09-14T11:30:00Z"), "zh", "Asia/Singapore")).toBe("晚上7点半");
    expect(clockWords(at("2026-09-14T00:05:00Z"), "zh", "Asia/Singapore")).toBe("上午8点5分");
  });
});
