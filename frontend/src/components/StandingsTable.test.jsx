import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StandingsTable from "./StandingsTable.jsx";

function team(overrides) {
  return {
    team_abbrev: "PIT",
    team_name: "Pittsburgh Penguins",
    division_sequence: 1,
    games_played: 82,
    wins: 40,
    losses: 30,
    ot_losses: 12,
    points: 92,
    goal_for: 250,
    goal_against: 240,
    goal_differential: 10,
    l10_wins: 5,
    l10_losses: 3,
    l10_ot_losses: 2,
    streak_code: "W",
    streak_count: 2,
    corsi_for_pct: null,
    fenwick_for_pct: null,
    xgoals_for_pct: null,
    pdo: null,
    ...overrides,
  };
}

function dataRows() {
  return screen.getAllByRole("row").slice(1); // drop the header row
}

describe("StandingsTable", () => {
  const rows = [
    team({ team_abbrev: "COL", team_name: "Colorado Avalanche", division_sequence: 2, corsi_for_pct: 0.57, xgoals_for_pct: 0.57, pdo: 102.0 }),
    team({ team_abbrev: "PIT", team_name: "Pittsburgh Penguins", division_sequence: 1, corsi_for_pct: 0.47, xgoals_for_pct: 0.51, pdo: 99.6 }),
  ];

  it("defaults to division_sequence order when no sort is active", () => {
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    const rendered = dataRows();
    expect(within(rendered[0]).getByText("PIT")).toBeInTheDocument();
    expect(within(rendered[1]).getByText("COL")).toBeInTheDocument();
  });

  it("trusts the given row order (does not re-sort) when a sort is active", () => {
    // rows arrive pre-sorted by the API in this case -- COL first despite
    // its higher division_sequence -- the table must not silently
    // override that with its own division-rank sort.
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy="corsi_for_pct" sortDir="desc" onSort={vi.fn()} />);

    const rendered = dataRows();
    expect(within(rendered[0]).getByText("COL")).toBeInTheDocument();
    expect(within(rendered[1]).getByText("PIT")).toBeInTheDocument();
  });

  it("clicking an advanced-stat column header calls onSort with that column's key", async () => {
    const onSort = vi.fn();
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={onSort} />);

    await userEvent.click(screen.getByRole("columnheader", { name: /xG%/ }));

    expect(onSort).toHaveBeenCalledWith("xgoals_for_pct");
  });

  it("shows the active sort column's direction arrow", () => {
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy="pdo" sortDir="asc" onSort={vi.fn()} />);

    expect(screen.getByText(/PDO\s*▲/)).toBeInTheDocument();
  });

  it("formats corsi/xG as a percentage and PDO to 1 decimal", () => {
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    // COL's corsi_for_pct and xgoals_for_pct are both 0.57 -- two cells
    // legitimately render the same "57.0%" text.
    expect(screen.getAllByText("57.0%")).toHaveLength(2);
    expect(screen.getByText("102.0")).toBeInTheDocument();
  });

  it("renders an em dash for teams with no advanced stats row yet", () => {
    const noAdvanced = [team({ team_abbrev: "SEA", corsi_for_pct: null, xgoals_for_pct: null, pdo: null })];
    render(<StandingsTable rows={noAdvanced} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    const rendered = dataRows();
    expect(within(rendered[0]).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows a no-results row spanning every column when rows is empty", () => {
    render(<StandingsTable rows={[]} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    expect(screen.getByText("No teams match your search.")).toBeInTheDocument();
  });

  it("clicking a team row calls onSelectTeam with that team's abbreviation", async () => {
    const onSelectTeam = vi.fn();
    render(<StandingsTable rows={rows} onSelectTeam={onSelectTeam} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    await userEvent.click(screen.getByText("Colorado Avalanche"));

    expect(onSelectTeam).toHaveBeenCalledWith("COL");
  });
});
