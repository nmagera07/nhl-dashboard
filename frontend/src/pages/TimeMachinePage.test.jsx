import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import TimeMachinePage from "./TimeMachinePage.jsx";
import { clearResponseCache } from "../utils/responseCache.js";

const ERA = { reference_season: 20252026, reference: 3.08, seasons: { 19851986: 3.97, 20252026: 3.08 } };
const RESULT = {
  player: { id: 8447400, name: "Wayne Gretzky", position: "C", headshot: null },
  source: { season_id: 19851986, games_played: 80, goals: 52, assists: 163, points: 215, scoring: 3.97 },
  target: { season_id: 20252026, scoring: 3.08 },
  factor: 0.776, pace_82: { goals: 41, assists: 130, points: 171 }, seasons: [19841985, 19851986],
  goals: { median: 41, low: 33, high: 50 }, assists: { median: 130, low: 110, high: 150 },
  points: { median: 171, low: 144, high: 199 }, histogram: [[120, 10], [150, 60], [180, 25], [210, 5]], bin_width: 30,
};

function renderAt(search, result = RESULT) {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => ({
    json: async () => (String(url).endsWith("/era/scoring") ? ERA : result),
  }));
  render(
    <MemoryRouter initialEntries={[`/time-machine${search}`]}>
      <Routes><Route path="/time-machine" element={<TimeMachinePage />} /></Routes>
    </MemoryRouter>,
  );
  return fetch;
}

describe("TimeMachinePage", () => {
  beforeEach(() => clearResponseCache());
  afterEach(() => vi.restoreAllMocks());

  it("asks for a player first", () => {
    renderAt("");
    expect(screen.getByRole("textbox", { name: "Player" })).toBeInTheDocument();
  });

  it("shows the season replayed in today's game, with the likely range and his real numbers", async () => {
    renderAt("?player=8447400");
    expect(await screen.findByText(/wayne gretzky's 1985-86 in today's game/i, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("~171")).toBeInTheDocument();
    expect(screen.getByText(/likely 144–199 over 82 games/)).toBeInTheDocument();
    expect(screen.getByText(/52 G, 163 A/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /most between 144 and 199/i })).toBeInTheDocument();
    expect(document.title).toBe("Wayne Gretzky in another era | PuckPulse");
  });

  it("picking another era asks the API for that target", async () => {
    const fetch = renderAt("?player=8447400");
    await screen.findByText("~171", {}, { timeout: 3000 });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /play it in/i }), "19851986");
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/players\/8447400\/time-machine\?target=19851986$/));
    expect(within(screen.getByRole("combobox", { name: /play it in/i })).getByRole("option", { name: /today \(2025-26\)/i }))
      .toBeInTheDocument();
  });

  it("shows the API's reason when it can't run", async () => {
    renderAt("?player=8451033", { detail: "The time machine is for skaters (goalies are coming)." });
    expect(await screen.findByText(/for skaters/, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pick someone else/i })).toBeInTheDocument();
  });
});
