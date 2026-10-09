import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MyTeamCard from "./MyTeamCard.jsx";

const PIT = {
  team_abbrev: "PIT", team_name: "Pittsburgh Penguins", division: "Metropolitan", logo_url: null,
  wins: 2, losses: 2, ot_losses: 0, points: 4, division_sequence: 5, streak_code: "L", streak_count: 2,
};
const TEAMS = [PIT, { ...PIT, team_abbrev: "BOS", team_name: "Boston Bruins" }];

const game = (id, opponent, extra) => ({ id, opponent, home: true, opponent_logo: null, start_time_utc: "2026-10-09T23:00:00Z", ...extra });
const SCHEDULE = {
  team: "PIT",
  live: null,
  recent: [
    game(3, "WSH", { home: false, team_score: 3, opponent_score: 5, result: "L", last_period_type: "REG" }),
    game(2, "MTL", { team_score: 5, opponent_score: 6, result: "OTL", last_period_type: "SO" }),
    game(1, "PHI", { home: false, team_score: 7, opponent_score: 0, result: "W", last_period_type: "REG" }),
  ],
  upcoming: [game(4, "CBJ", { home: false })],
  plays_today: true,
};

function mockSchedule(schedule = SCHEDULE) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => schedule });
}

function renderCard(props = {}) {
  return render(
    <MemoryRouter>
      <MyTeamCard team={PIT} odds={0.57} teams={TEAMS} onChangeTeam={vi.fn()} {...props} />
    </MemoryRouter>
  );
}

describe("MyTeamCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the season, odds, next game, and recent results", async () => {
    const fetchMock = mockSchedule();
    renderCard();

    expect(screen.getByText("2-2-0 · 4 PTS · 5th Metropolitan · L2 streak")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /playoff odds 57%/i })).toHaveAttribute("href", "/playoffs");
    expect(await screen.findByRole("link", { name: /next game: @ cbj/i })).toHaveAttribute("href", "/games/4");
    const chips = within(screen.getByRole("list")).getAllByRole("link");
    expect(chips.map((c) => c.getAttribute("title"))).toEqual(["Lost 3–5 @ WSH", "Lost in SO 5–6 vs MTL", "Won 7–0 @ PHI"]);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/teams\/PIT\/schedule$/));
  });

  it("shows the live game instead of the next one", async () => {
    mockSchedule({ ...SCHEDULE, live: game(5, "CAR", { team_score: 2, opponent_score: 1 }) });
    renderCard();

    const live = await screen.findByRole("link", { name: /live: vs car, 2–1/i });
    expect(live).toHaveAttribute("href", "/games/5");
    expect(screen.queryByText(/next/i)).not.toBeInTheDocument();
  });

  it("says so when the schedule can't load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, status: 503 });
    renderCard();

    expect(await screen.findByText("Couldn't load the schedule.")).toBeInTheDocument();
  });

  it("can switch teams or stop following", async () => {
    mockSchedule();
    const onChangeTeam = vi.fn();
    renderCard({ onChangeTeam });

    await userEvent.click(screen.getByRole("button", { name: "Change team" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /switch to/i }), "BOS");
    expect(onChangeTeam).toHaveBeenLastCalledWith("BOS");

    await userEvent.click(screen.getByRole("button", { name: "Change team" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop following" }));
    expect(onChangeTeam).toHaveBeenLastCalledWith(null);
  });
});
