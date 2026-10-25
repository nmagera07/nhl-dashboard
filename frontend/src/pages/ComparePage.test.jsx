import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ComparePage from "./ComparePage.jsx";
import { clearResponseCache } from "../utils/responseCache.js";

const player = (id, first, last, extra = {}) => ({
  player_id: id, first_name: first, last_name: last, position_code: "C", team_abbrev: null, headshot_url: null,
  season_stats: [], season_history: [], war: null, ...extra,
});
const PLAYERS = {
  8478402: player(8478402, "Connor", "McDavid", { team_abbrev: "EDM",
    career_totals: { regular_season: { games_played: 804, goals: 417, assists: 834, points: 1251 } } }),
  8447400: player(8447400, "Wayne", "Gretzky", { status: "retired", in_hall_of_fame: true, last_season_id: 19981999,
    career_totals: { regular_season: { games_played: 1487, goals: 894, assists: 1963, points: 2857 } },
    season_history: [{ season_id: 19851986, season_type: "regular_season", games_played: 80, goals: 52, assists: 163, points: 215 }] }),
  8451033: player(8451033, "Patrick", "Roy", { position_code: "G", status: "retired",
    career_totals: { regular_season: { games_played: 1029, wins: 551 } } }),
};

const ERA = { reference_season: 20252026, reference: 3.08, seasons: { 19851986: 3.97, 20222023: 3.18 } };

function renderAt(search) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    if (String(url).endsWith("/era/scoring")) return { ok: true, json: async () => ERA };
    const id = String(url).match(/\/players\/(\d+)$/)?.[1];
    return { ok: Boolean(PLAYERS[id]), json: async () => PLAYERS[id] };
  });
  return render(
    <MemoryRouter initialEntries={[`/compare${search}`]}>
      <Routes><Route path="/compare" element={<ComparePage />} /></Routes>
    </MemoryRouter>,
  );
}

describe("ComparePage", () => {
  beforeEach(() => clearResponseCache());
  afterEach(() => vi.restoreAllMocks());

  it("puts two players side by side and marks the better number", async () => {
    renderAt("?a=8478402&b=8447400");
    const career = (await screen.findByText("Career", {}, { timeout: 3000 })).closest("section");
    const points = within(career).getByText("Points").closest(".compare-row");
    expect(within(points).getByText("2857")).toHaveClass("compare-win");
    expect(within(points).getByText("1251")).not.toHaveClass("compare-win");
    expect(within(career).getByText("1.92")).toBeInTheDocument(); // points per game
    expect(screen.getByText("Hall of Fame")).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("McDavid vs Gretzky | PuckPulse")); // set just after render
  });

  it("switches to era-adjusted numbers, rescaling each season to today's scoring", async () => {
    renderAt("?a=8478402&b=8447400");
    const toggle = await screen.findByRole("button", { name: "Era-adjusted" }, { timeout: 3000 });
    toggle.click();
    expect(await screen.findByText(/Every season rescaled to 25-26 scoring \(3.08 goals per team per game\)/)).toBeInTheDocument();
    const best = screen.getByText("Best season").closest("section");
    expect(within(best).getByText("166")).toBeInTheDocument(); // Gretzky's 215 in 85-86, at today's scoring
  });

  it("won't compare a skater to a goalie", async () => {
    renderAt("?a=8478402&b=8451033");
    expect(await screen.findByText(/Pick two skaters or two goalies: their numbers don.t compare/, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText("Career")).not.toBeInTheDocument();
  });

  it("asks for the second player", async () => {
    renderAt("?a=8478402");
    expect(await screen.findByText("Connor McDavid", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByLabelText("Player 2")).toBeInTheDocument();
  });
});
