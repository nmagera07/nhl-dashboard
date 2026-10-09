import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import SeasonSimulator from "./SeasonSimulator.jsx";

const MODEL = { home_edge: 0.264, scale: 1.47, ot_probability: 0.221, shootout_share_of_ot: 0.32 };
const team = (division, rating = 0) => ({
  points: 4, wins: 2, losses: 2, ot_losses: 0, regulation_wins: 2, row: 2, division, conference: "Eastern", rating, rating_sd: 0.2,
});
const INPUTS = {
  season_id: 20262027,
  model: MODEL,
  teams: { PIT: team("Metropolitan", 0.2), CBJ: team("Metropolitan"), NYR: team("Metropolitan"), BOS: team("Atlantic") },
  games: [["2026-10-09", "CBJ", "PIT"], ["2026-10-10", "PIT", "NYR"], ["2026-10-11", "BOS", "NYR"]],
};
const PIT = { team_abbrev: "PIT", common_name: "Penguins" };

function renderSim(response) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
  return render(
    <MemoryRouter>
      <SeasonSimulator team={PIT} />
    </MemoryRouter>
  );
}

describe("SeasonSimulator", () => {
  afterEach(() => vi.restoreAllMocks());

  it("plays out one season per click, with a game-by-game strip", async () => {
    renderSim({ ok: true, status: 200, json: async () => INPUTS });

    expect(await screen.findByText(/play out the penguins' last 2 games/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sim the season" }));

    const record = screen.getByText(/^\d+-\d+-\d+$/);
    const [w, l, otl] = record.textContent.split("-").map(Number);
    expect(w + l + otl).toBe(6); // 4 played + 2 simulated
    expect(screen.getByRole("list", { name: /simulated results/i }).children).toHaveLength(2);
    expect(screen.getByText("Your sims: 1 · playoffs in 1")).toBeInTheDocument(); // 3 division teams always make it

    await userEvent.click(screen.getByRole("button", { name: "Sim again" }));
    expect(screen.getByText(/^Your sims: 2/)).toBeInTheDocument();
    expect(await screen.findByText(/across 3,000 seasons/i, {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it("explains when the simulator hasn't run yet", async () => {
    renderSim({ ok: false, status: 404 });

    expect(await screen.findByText(/updates after each morning's playoff odds run/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sim the season" })).not.toBeInTheDocument();
  });

  it("says so when it can't load", async () => {
    renderSim({ ok: false, status: 500 });

    expect(await screen.findByText("Couldn't load the simulator.")).toBeInTheDocument();
  });
});
