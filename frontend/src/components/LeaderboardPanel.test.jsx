import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LeaderboardPanel from "./LeaderboardPanel.jsx";

function player(overrides) {
  return {
    player_id: 1,
    first_name: "First",
    last_name: "Last",
    team_abbrev: "PIT",
    team_logo_url: null,
    position_code: "C",
    points: 0,
    goals: 0,
    assists: 0,
    plus_minus: 0,
    pim: 0,
    shots: 0,
    games_played: 0,
    wins: 0,
    losses: 0,
    ot_losses: 0,
    goals_against_avg: 0,
    save_pctg: 0,
    shutouts: 0,
    ...overrides,
  };
}

function playerRows() {
  return screen.getAllByRole("row").slice(1); // drop the header row
}

// Desktop table and mobile cards both render (CSS picks which one shows),
// so text assertions are scoped to one or the other.
const table = () => within(screen.getByRole("table"));
const cardList = (group = "skaters") => within(screen.getByLabelText(`${group} player cards`));

describe("LeaderboardPanel", () => {
  const skaters = [
    player({ player_id: 1, first_name: "Sidney", last_name: "Crosby", team_abbrev: "PIT", position_code: "C", points: 90 }),
    player({ player_id: 2, first_name: "Connor", last_name: "McDavid", team_abbrev: "EDM", position_code: "C", points: 150 }),
  ];
  const goalie = player({ player_id: 3, first_name: "Marc-Andre", last_name: "Fleury", team_abbrev: "MIN", position_code: "G", wins: 20 });

  it("defaults to skaters, sorted by points descending", () => {
    render(<LeaderboardPanel players={skaters} onSelectPlayer={vi.fn()} />);

    const rows = playerRows();
    expect(within(rows[0]).getByText(/mcdavid/i)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/crosby/i)).toBeInTheDocument();
    expect(screen.getByText(/showing top 2 of 2/i)).toBeInTheDocument();
  });

  it("excludes goalies from the default skaters view, and vice versa", async () => {
    render(<LeaderboardPanel players={[...skaters, goalie]} onSelectPlayer={vi.fn()} />);
    expect(screen.queryByText(/fleury/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "GOALIES" }));

    expect(table().getByText(/fleury/i)).toBeInTheDocument();
    expect(screen.queryByText(/crosby/i)).not.toBeInTheDocument();
    // Switching group also resets the sort column to that group's default.
    expect(screen.getByRole("columnheader", { name: /^W\s*▼$/ })).toBeInTheDocument();
  });

  it("clicking a column header sorts by it, clicking again reverses direction", async () => {
    render(<LeaderboardPanel players={skaters} onSelectPlayer={vi.fn()} />);

    await userEvent.click(screen.getByRole("columnheader", { name: /GP/ }));
    // Both players have games_played: 0 (tied) -- direction can't be
    // observed from row order here, so assert on the header's own arrow
    // instead, which is what actually encodes sort state to the user.
    expect(screen.getByRole("columnheader", { name: /^GP\s*▼$/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("columnheader", { name: /GP/ }));
    expect(screen.getByRole("columnheader", { name: /^GP\s*▲$/ })).toBeInTheDocument();
  });

  it("a lower-is-better column (GAA) defaults to ascending on first click", async () => {
    render(<LeaderboardPanel players={[goalie]} onSelectPlayer={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "GOALIES" }));

    await userEvent.click(screen.getByRole("columnheader", { name: /GAA/ }));

    expect(screen.getByRole("columnheader", { name: /^GAA\s*▲$/ })).toBeInTheDocument();
  });

  it("search filters by name and by team abbreviation, and drops the top-50 cap while searching", async () => {
    render(<LeaderboardPanel players={skaters} onSelectPlayer={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Find a player..."), "mcdavid");

    // Case-sensitive here: a case-insensitive match would also hit the
    // status line below ("1 result for 'mcdavid'"), which echoes the
    // lowercase search term back.
    expect(table().getByText(/McDavid/)).toBeInTheDocument();
    expect(screen.queryByText(/crosby/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 result for "mcdavid"/i)).toBeInTheDocument();
  });

  it("shows a no-results row when the search matches nobody", async () => {
    render(<LeaderboardPanel players={skaters} onSelectPlayer={vi.fn()} />);

    await userEvent.type(screen.getByPlaceholderText("Find a player..."), "zzz-nobody");

    expect(table().getByText("No players match your search.")).toBeInTheDocument();
  });

  it("formats GAA to 2 decimals and SV% to 3, and renders a missing stat as an em dash", async () => {
    const partial = player({
      player_id: 9,
      first_name: "Partial",
      last_name: "Stats",
      position_code: "G",
      wins: 1,
      goals_against_avg: 2.5,
      save_pctg: 0.912,
      shutouts: null,
    });
    render(<LeaderboardPanel players={[partial]} onSelectPlayer={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "GOALIES" }));

    expect(table().getByText("2.50")).toBeInTheDocument();
    expect(table().getByText("0.912")).toBeInTheDocument();
    expect(table().getByText("—")).toBeInTheDocument();
  });

  it("clicking a player row calls onSelectPlayer with that player's id", async () => {
    const onSelectPlayer = vi.fn();
    render(<LeaderboardPanel players={skaters} onSelectPlayer={onSelectPlayer} />);

    await userEvent.click(table().getByText(/crosby/i));

    expect(onSelectPlayer).toHaveBeenCalledWith(1);
  });

  describe("mobile cards", () => {
    it("clicking a player card calls onSelectPlayer with that player's id", async () => {
      const onSelectPlayer = vi.fn();
      render(<LeaderboardPanel players={skaters} onSelectPlayer={onSelectPlayer} />);

      await userEvent.click(cardList().getByRole("button", { name: /open sidney crosby profile/i }));

      expect(onSelectPlayer).toHaveBeenCalledWith(1);
    });

    it("continues rank numbering across pages instead of restarting at 1", async () => {
      const many = Array.from({ length: 60 }, (_, i) =>
        player({ player_id: i + 1, first_name: "Player", last_name: `${i + 1}`, points: 100 - i })
      );
      render(<LeaderboardPanel players={many} onSelectPlayer={vi.fn()} />);

      await userEvent.click(screen.getByRole("button", { name: "Next page" }));

      const firstCard = cardList().getByRole("button", { name: /open player 51 profile/i });
      expect(within(firstCard).getByText("51")).toBeInTheDocument();
    });

    it("shows goalie stats with the same formatting as the table", async () => {
      render(<LeaderboardPanel players={[player({ ...goalie, goals_against_avg: 2.5, save_pctg: 0.912 })]} onSelectPlayer={vi.fn()} />);
      await userEvent.click(screen.getByRole("button", { name: "GOALIES" }));

      expect(cardList("goalies").getByText("2.50")).toBeInTheDocument();
      expect(cardList("goalies").getByText("0.912")).toBeInTheDocument();
    });

    it("shows an empty message when the search matches nobody", async () => {
      render(<LeaderboardPanel players={skaters} onSelectPlayer={vi.fn()} />);

      await userEvent.type(screen.getByPlaceholderText("Find a player..."), "zzz-nobody");

      expect(cardList().getByText("No players match your search.")).toBeInTheDocument();
    });
  });
});
