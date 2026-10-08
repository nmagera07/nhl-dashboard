import { darkLogo } from "./darkLogo.js";

describe("darkLogo", () => {
  it("swaps an NHL light logo for its dark-background version", () => {
    expect(darkLogo("https://assets.nhle.com/logos/nhl/svg/TBL_light.svg")).toBe(
      "https://assets.nhle.com/logos/nhl/svg/TBL_dark.svg"
    );
  });

  it("leaves other URLs and missing values alone", () => {
    expect(darkLogo("https://example.com/pit.png")).toBe("https://example.com/pit.png");
    expect(darkLogo(null)).toBeNull();
  });
});
