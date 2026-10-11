import { describe, expect, it } from "vitest";
import { nhlVideoUrl } from "./highlights.js";

describe("nhlVideoUrl", () => {
  it("turns score-feed paths into nhl.com links", () => {
    expect(nhlVideoUrl("/video/phi-at-bos-recap-6406612944112")).toBe("https://www.nhl.com/video/phi-at-bos-recap-6406612944112");
  });

  it("keeps nhl.com share URLs", () => {
    const url = "https://nhl.com/video/phi-bos-zacha-scores-goal-against-dan-vladar-6406606778112";
    expect(nhlVideoUrl(url)).toBe(url);
  });

  it("rejects anything that isn't an nhl.com video", () => {
    expect(nhlVideoUrl("https://evil.example/video/x")).toBeNull();
    expect(nhlVideoUrl("javascript:alert(1)")).toBeNull();
    expect(nhlVideoUrl("http://nhl.com/video/x")).toBeNull();
    expect(nhlVideoUrl("https://nhl.com/news/x")).toBeNull();
    expect(nhlVideoUrl("//evil.example/video/x")).toBeNull();
    expect(nhlVideoUrl(undefined)).toBeNull();
  });
});
