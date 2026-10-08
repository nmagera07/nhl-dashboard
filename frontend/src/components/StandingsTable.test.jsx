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
    xgoals_for_pct: null,
    xgoals_for: null,
    xgoals_against: null,
    shots_on_goal_for: null,
    shots_on_goal_against: null,
    pdo: null,
    ...overrides,
  };
}

function dataRows() {
  return screen.getAllByRole("row").slice(1); // drop the header row
}

describe("StandingsTable", () => {
  const rows = [
    team({
      team_abbrev: "COL", team_name: "Colorado Avalanche", division_sequence: 2,
      xgoals_for_pct: 0.57, xgoals_for: 181.4, xgoals_against: 137.2,
      shots_on_goal_for: 1900, shots_on_goal_against: 1650, pdo: 102.0,
    }),
    team({
      team_abbrev: "PIT", team_name: "Pittsburgh Penguins", division_sequence: 1,
      xgoals_for_pct: 0.51, xgoals_for: 160.1, xgoals_against: 155.8,
      shots_on_goal_for: 1807, shots_on_goal_against: 1751, pdo: 99.6,
    }),
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
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy="xgoals_for_pct" sortDir="desc" onSort={vi.fn()} />);

    const rendered = dataRows();
    expect(within(rendered[0]).getByText("COL")).toBeInTheDocument();
    expect(within(rendered[1]).getByText("PIT")).toBeInTheDocument();
  });

  it("clicking an advanced-stat column header calls onSort with that column's key", async () => {
    const onSort = vi.fn();
    render(<StandingsTable view="advanced" rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={onSort} />);

    await userEvent.click(screen.getByRole("columnheader", { name: /xGA/ }));

    expect(onSort).toHaveBeenCalledWith("xgoals_against");
  });

  it("shows the active sort column's direction arrow", () => {
    render(<StandingsTable view="advanced" rows={rows} onSelectTeam={vi.fn()} sortBy="pdo" sortDir="asc" onSort={vi.fn()} />);

    expect(screen.getByText(/PDO\s*▲/)).toBeInTheDocument();
  });

  it("formats xG% as a percentage, xGF/xGA to 1 decimal, SF/SA as plain integers, and PDO to 1 decimal", () => {
    render(<StandingsTable view="advanced" rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    expect(screen.getByText("57.0%")).toBeInTheDocument();
    expect(screen.getByText("181.4")).toBeInTheDocument();
    expect(screen.getByText("137.2")).toBeInTheDocument();
    expect(screen.getByText("1900")).toBeInTheDocument();
    expect(screen.getByText("1650")).toBeInTheDocument();
    expect(screen.getByText("102.0")).toBeInTheDocument();
  });

  it("renders an em dash for teams with no advanced stats row yet", () => {
    const noAdvanced = [team({ team_abbrev: "SEA" })];
    render(<StandingsTable view="advanced" rows={noAdvanced} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    const rendered = dataRows();
    expect(within(rendered[0]).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows a no-results row spanning every column when rows is empty", () => {
    render(<StandingsTable rows={[]} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    expect(within(screen.getByRole("table")).getByText("No teams match your search.")).toBeInTheDocument();
  });

  it("clicking a team row calls onSelectTeam with that team's abbreviation", async () => {
    const onSelectTeam = vi.fn();
    render(<StandingsTable rows={rows} onSelectTeam={onSelectTeam} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    await userEvent.click(within(screen.getByRole("table")).getByText("Colorado Avalanche"));

    expect(onSelectTeam).toHaveBeenCalledWith("COL");
  });

  // Mobile cards render alongside the table (CSS picks which one shows),
  // so they get their own coverage.
  it("the standard view shows the classic columns plus playoff odds, and hides advanced ones", () => {
    render(<StandingsTable rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual(["", "TEAM", "GP", "W", "L", "OT", "PTS", "GF", "GA", "DIFF", "L10", "STRK", "PO%"]);
  });

  it("the advanced view shows the sortable advanced columns", () => {
    render(<StandingsTable view="advanced" rows={rows} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual(["", "TEAM", "GP", "PTS", "xG%", "xGF", "xGA", "SF", "SA", "PDO"]);
  });

  it("formats playoff odds without overstating certainty", () => {
    const odds = { COL: 0.004, PIT: 0.9962 };
    render(<StandingsTable rows={rows} playoffOddsByTeam={odds} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    const table = within(screen.getByRole("table"));
    expect(table.getByText("<1%")).toBeInTheDocument();
    expect(table.getByText(">99%")).toBeInTheDocument();
  });

  it("shows each team's logo next to its name", () => {
    const withLogo = [team({ team_abbrev: "PIT", team_name: "Pittsburgh Penguins", logo_url: "https://example.com/pit.svg" })];
    const { container } = render(<StandingsTable rows={withLogo} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

    expect(container.querySelector("table img.team-cell-logo")).toHaveAttribute("src", "https://example.com/pit.svg");
  });

  describe("mobile cards", () => {
    const cardList = () => within(screen.getByLabelText("Team standings cards"));

    it("clicking a team card calls onSelectTeam with that team's abbreviation", async () => {
      const onSelectTeam = vi.fn();
      render(<StandingsTable rows={rows} onSelectTeam={onSelectTeam} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

      await userEvent.click(cardList().getByRole("button", { name: /open colorado avalanche team page/i }));

      expect(onSelectTeam).toHaveBeenCalledWith("COL");
    });

    it("shows an empty message when rows is empty", () => {
      render(<StandingsTable rows={[]} onSelectTeam={vi.fn()} sortBy={null} sortDir="desc" onSort={vi.fn()} />);

      expect(cardList().getByText("No teams match your search.")).toBeInTheDocument();
    });
  });
});
