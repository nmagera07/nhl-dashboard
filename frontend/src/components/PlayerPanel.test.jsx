import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PlayerPanel from "./PlayerPanel.jsx";

function season(seasonId, type, overrides = {}) {
  return {
    season_id: seasonId, season_type: type, games_played: 82, goals: 30, assists: 40, points: 70,
    plus_minus: 5, shots: 200, pim: 20, ...overrides,
  };
}

function skater(overrides = {}) {
  return {
    player_id: 8471675, first_name: "Sidney", last_name: "Crosby", position_code: "C",
    sweater_number: 87, team_abbrev: "PIT", team_logo_url: null, headshot_url: null,
    shoots_catches: "L", height_in_inches: 71, weight_in_pounds: 206,
    birth_date: "1987-08-07", birth_city: "Cole Harbour", birth_country: "CAN",
    season_stats: [{ season_id: 20262027, games_played: 4, goals: 0, assists: 2, points: 2, plus_minus: -3, shots: 12, pim: 0 }],
    advanced_stats: null,
    career_totals: {
      regular_season: { games_played: 1424, goals: 654, assists: 1109, points: 1763, plus_minus: 194, shots: 4471, pim: 898 },
      playoffs: { games_played: 186, goals: 72, assists: 134, points: 206, plus_minus: 17, shots: 561, pim: 89 },
    },
    season_history: [
      season(20262027, "regular_season", { points: 2 }),
      season(20252026, "regular_season", { points: 74 }),
      season(20242025, "regular_season", { points: 91 }),
      season(20232024, "regular_season", { points: 94 }),
      season(20222023, "regular_season", { points: 93 }),
      season(20212022, "regular_season", { points: 84 }),
      season(20222023, "playoffs", { points: 9 }),
    ],
    ...overrides,
  };
}

function renderPanel(player) {
  return render(
    <MemoryRouter>
      <PlayerPanel player={player} onBack={vi.fn()} backLabel="Back to Roster" />
    </MemoryRouter>
  );
}

describe("PlayerPanel", () => {
  it("shows the player's identity, a one-line bio, and a link to their team", () => {
    renderPanel(skater());

    expect(screen.getByRole("heading", { name: "Sidney Crosby" })).toBeInTheDocument();
    expect(screen.getByText(/Shoots L · 5'11" · 206 lbs · Age \d+ · Cole Harbour, CAN/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /PIT/ })).toHaveAttribute("href", "/teams/PIT");
  });

  it("shows this season's stats in the header strip", () => {
    renderPanel(skater());

    expect(screen.getByText("26-27 season")).toBeInTheDocument();
    const strip = within(screen.getByLabelText("This season"));
    expect(strip.getByText("PTS").nextSibling).toHaveTextContent("2");
    expect(strip.getByText("+/-").nextSibling).toHaveTextContent("-3");
    expect(strip.getByText("SOG").nextSibling).toHaveTextContent("12");
  });

  it("shows an empty state when there are no current-season stats yet", () => {
    renderPanel(skater({ season_stats: [] }));

    expect(screen.getByText("No current-season stats are available yet.")).toBeInTheDocument();
  });

  it("shows career totals as a table with regular season and playoff rows", () => {
    renderPanel(skater());

    const career = within(screen.getByRole("table", { name: "Career totals" }));
    expect(career.getByText("Regular season").closest("tr")).toHaveTextContent("1763");
    expect(career.getByText("Playoffs").closest("tr")).toHaveTextContent("+17");
  });

  it("shows the last 5 seasons, then all of them on request", async () => {
    renderPanel(skater());

    const table = () => within(screen.getByRole("table", { name: "Season by season" }));
    expect(table().getAllByRole("row")).toHaveLength(1 + 5);
    expect(table().queryByText("21-22")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show all 6 seasons" }));

    expect(table().getByText("21-22")).toBeInTheDocument();
  });

  it("switches season-by-season to playoffs", async () => {
    renderPanel(skater());

    await userEvent.click(screen.getByRole("button", { name: "Playoffs" }));

    const table = within(screen.getByRole("table", { name: "Season by season" }));
    expect(table.getAllByRole("row")).toHaveLength(1 + 1);
    expect(table.getByText("22-23").closest("tr")).toHaveTextContent("9");
  });

  it("uses goalie columns, with save percentage formatted like .912", () => {
    renderPanel(skater({
      position_code: "G", shoots_catches: "L",
      season_stats: [{ season_id: 20262027, games_played: 3, wins: 2, losses: 1, ot_losses: 0, goals_against_avg: 3.375, save_pctg: 0.859, shutouts: 1 }],
      career_totals: null,
      season_history: [],
    }));

    expect(screen.getByText(/Catches L/)).toBeInTheDocument();
    const strip = within(screen.getByLabelText("This season"));
    expect(strip.getByText("SV%").nextSibling).toHaveTextContent(".859");
    expect(strip.getByText("GAA").nextSibling).toHaveTextContent("3.38");
    expect(strip.queryByText("PTS")).not.toBeInTheDocument();
  });
});
