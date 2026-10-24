import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SwingOfTheNight from "./SwingOfTheNight.jsx";
import { clearResponseCache } from "../utils/responseCache.js";

const SWING = {
  available: true, date: "2026-10-20", games: 11,
  game: { id: 2026020149, away: "DET", home: "SEA", away_score: 3, home_score: 4, last_period: "SO" },
  goal: { scorer: "A. DeBrincat", team: "DET", side: "away", second: 3583, when: "0:17 left in the 3rd",
          effect: "ties it", before: 0.02, after: 0.48 },
  points: [[0, 0.55], [3583, 0.98], [3583, 0.52], [3900, 1]], goals: [], playoff: false,
};

const renderWith = (body) => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => body });
  const view = render(<MemoryRouter><SwingOfTheNight /></MemoryRouter>);
  return { fetchMock, ...view };
};

describe("SwingOfTheNight", () => {
  beforeEach(() => clearResponseCache());
  afterEach(() => vi.restoreAllMocks());

  it("shows last night's moment, links to the game, and shares its own card", async () => {
    renderWith(SWING);
    expect(await screen.findByText("A. DeBrincat ties it with 0:17 left in the 3rd")).toBeInTheDocument();
    expect(screen.getByText("DET 2% → 48% to win · Final DET 3, SEA 4 (SO)")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/games/2026020149");

    const writeText = vi.fn().mockResolvedValue();
    Object.assign(navigator, { clipboard: { writeText } });
    screen.getByRole("button", { name: "Share Swing of the Night" }).click();
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("https://puckpulse.io/s/2026-10-20"));
  });

  it("stays hidden after a night without games", async () => {
    const { fetchMock, container } = renderWith({ available: false, date: "2026-07-01" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
