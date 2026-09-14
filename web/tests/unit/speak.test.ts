import { describe, expect, it } from "vitest";
import { pickLocalVoice } from "../../src/speech/speak";

const voice = (lang: string, localService: boolean) => ({ lang, localService });

describe("the voice", () => {
  it("is one that runs on the phone, for his language", () => {
    const voices = [voice("en-US", false), voice("en-GB", true), voice("en-SG", true), voice("ms-MY", true)];
    expect(pickLocalVoice(voices, "en")).toEqual(voice("en-SG", true));
    expect(pickLocalVoice(voices, "ms")).toEqual(voice("ms-MY", true));
  });

  it("is never a network voice, even when that is the only one for the language", () => {
    expect(pickLocalVoice([voice("zh-CN", false), voice("en-SG", true)], "zh")).toBeNull();
    expect(pickLocalVoice([], "en")).toBeNull();
  });

  it("takes the language when the exact locale is missing", () => {
    expect(pickLocalVoice([voice("zh_TW", true)], "zh")).toEqual(voice("zh_TW", true));
  });
});
