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

  it("shows a skater's average time on ice this season", () => {
    renderPanel(skater({ season_stats: [{ season_id: 20262027, games_played: 6, goals: 1, assists: 2, points: 3, avg_toi_seconds: 1190 }] }));

    const strip = within(screen.getByLabelText("This season"));
    expect(strip.getByText("TOI").nextSibling).toHaveTextContent("19:50");
  });

  it("shows goalies' goals saved above expected", () => {
    renderPanel(skater({
      position_code: "G", shoots_catches: "L",
      season_stats: [], career_totals: null, season_history: [],
      goalie_advanced_stats: { season_id: 20262027, games_played: 5, goals_allowed: 10, xgoals_against: 13.5,
                               gsax: 3.5, gsax_per_60: 0.7, high_danger_gsax: -1.2 },
    }));

    const card = within(screen.getByText("Advanced (all situations)").closest("section"));
    expect(card.getByText("GSAx").closest("div")).toHaveTextContent("+3.5");
    expect(card.getByText("GSAx/60").closest("div")).toHaveTextContent("+0.70");
    expect(card.getByText("High-danger GSAx").closest("div")).toHaveTextContent("−1.2");
    expect(card.getByText(/10 goals allowed on shots worth 13.5 expected/)).toBeInTheDocument();
  });
});

describe("PlayerPanel advanced stats", () => {
  const advanced = { season_id: 20262027, games_played: 8, icetime_seconds: 8197, corsi_for_pct: 0.48, fenwick_for_pct: 0.47,
                     xgoals_for_pct: 0.48, xgoals_for: 7.4, xgoals_against: 8.0, individual_xgoals: 2.41, pdo: 104.2 };

  it("ranks each number among his position in plain words, with a luck note", () => {
    renderPanel(skater({ advanced_stats: advanced,
      advanced_percentiles: { group: "forwards", peers: 398, corsi: 43, xg: 41, ixg60: 89, ixg60_value: 1.11 } }));
    expect(screen.getByText("Controls play")).toBeInTheDocument();
    expect(screen.getByText("Creates his own chances")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Better than 89% of forwards" })).toBeInTheDocument();
    expect(screen.getByText(/running hot/)).toBeInTheDocument();          // PDO 104.2
    expect(screen.queryByText(/xGF–xGA/)).not.toBeInTheDocument();         // the raw totals are gone
  });

  it("shows a retired player's NHL career, last season, and Hall of Fame", () => {
    renderPanel(skater({
      first_name: "Wayne", last_name: "Gretzky", team_abbrev: null, season_stats: [], status: "retired", birth_date: "1961-01-26",
      in_hall_of_fame: true, last_season_id: 19981999, last_team_name: "New York Rangers",
      career_totals: { regular_season: { games_played: 1487, goals: 894, assists: 1963, points: 2857 }, playoffs: null },
    }));
    expect(screen.getByText("Hall of Fame")).toBeInTheDocument();
    expect(screen.getByText("NHL career")).toBeInTheDocument();
    expect(screen.getAllByText("2857").length).toBeGreaterThan(0);
    expect(screen.getByText(/Retired · last NHL season 98-99, New York Rangers/)).toBeInTheDocument();
    expect(screen.queryByText(/No current-season stats/)).not.toBeInTheDocument();
    expect(screen.getByText(/Born 1961/)).toBeInTheDocument(); // not an age, which would keep counting
    expect(screen.queryByText(/Age \d+/)).not.toBeInTheDocument();
  });

  it("opens WAR's breakdown on request, for skaters that have one", async () => {
    const parts = { ev_offense: 3.12, ev_defense: -0.4, finishing: 1.2, power_play: 0.5, penalty_kill: 0, penalties: 0.3 };
    renderPanel(skater({ war: { war: 0.77, gar: 4.75, games_played: 9, group: "forwards", rank: 1, of: 459, parts } }));
    const toggle = screen.getByRole("button", { name: "What makes it up" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("5-on-5 offense")).not.toBeInTheDocument(); // hidden by default
    await userEvent.click(toggle);
    expect(screen.getByText("5-on-5 offense").nextSibling).toHaveTextContent("+3.1");
    expect(screen.getByText("5-on-5 defense").nextSibling).toHaveTextContent("−0.4"); // a true minus sign, as formatSigned writes it
  });

  it("has no breakdown button before the parts exist", () => {
    renderPanel(skater({ war: { war: 0.77, gar: 4.75, games_played: 9, group: "forwards", rank: 1, of: 459 } }));
    expect(screen.queryByRole("button", { name: "What makes it up" })).not.toBeInTheDocument();
  });

  it("shows this season's WAR and where it ranks in his position", () => {
    renderPanel(skater({ war: { war: 0.77, gar: 4.75, games_played: 9, group: "forwards", rank: 1, of: 459 } }));
    expect(screen.getByText("+0.77")).toBeInTheDocument();
    expect(screen.getByText(/1st of 459 forwards/)).toBeInTheDocument();
  });

  it("says when there aren't enough minutes to rank yet", () => {
    renderPanel(skater({ advanced_stats: advanced, advanced_percentiles: { too_few_minutes: true } }));
    expect(screen.getByText(/Not enough 5-on-5 minutes yet/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Better than/ })).not.toBeInTheDocument();
  });
});
