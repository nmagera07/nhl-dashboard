import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import usePageTitle from "./usePageTitle.js";

function Probe() {
  usePageTitle();
  return null;
}

describe("usePageTitle", () => {
  it("sets the title for the route", () => {
    render(<MemoryRouter initialEntries={["/teams/PIT"]}><Probe /></MemoryRouter>);
    expect(document.title).toBe("Pittsburgh Penguins playoff odds & stats | PuckPulse");
  });

  it("uses the page name", () => {
    render(<MemoryRouter initialEntries={["/playoffs"]}><Probe /></MemoryRouter>);
    expect(document.title).toBe("NHL Playoff Odds | PuckPulse");
  });
});
