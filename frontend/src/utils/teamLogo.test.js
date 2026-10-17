import { afterEach, describe, expect, it } from "vitest";
import { teamLogo } from "./teamLogo.js";

const LIGHT = "https://assets.nhle.com/logos/nhl/svg/TBL_light.svg";
const DARK = "https://assets.nhle.com/logos/nhl/svg/TBL_dark.svg";

describe("teamLogo", () => {
  afterEach(() => delete document.documentElement.dataset.theme);

  it("uses the dark-background version in the dark theme", () => {
    document.documentElement.dataset.theme = "dark";
    expect(teamLogo(LIGHT)).toBe(DARK);
  });

  it("uses the light-background version in the light theme", () => {
    document.documentElement.dataset.theme = "light";
    expect(teamLogo(DARK)).toBe(LIGHT);
    expect(teamLogo(LIGHT)).toBe(LIGHT);
  });

  it("leaves other URLs and missing values alone", () => {
    expect(teamLogo("https://example.com/pit.png")).toBe("https://example.com/pit.png");
    expect(teamLogo(null)).toBeNull();
  });
});
