import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import MyTeamCard, { PlayoffLine } from "./MyTeamCard.jsx";

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
    expect(screen.getByRole("link", { name: /sim the season/i })).toHaveAttribute("href", "/teams/PIT#season-sim");
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


describe("PlayoffLine", () => {
  const today = new Date().toISOString().slice(0, 10);
  const data = (row, extra) => ({
    as_of_date: today, games_remaining: 1000, season_games: 84, source: "sim",
    cutline: { Eastern: { p25: 92, p50: 95, p75: 98 } },
    teams: { PIT: { conference: "Eastern", gp: 20, pts: 20, otl: 2, point_pctg: 0.5, games_left: 64, ...row } },
    ...extra,
  });
  const show = (d, team = PIT) => render(<PlayoffLine data={d} team={team} />);

  it("shows the line, the pace and the record needed (84-game season), collapsed to one line", () => {
    show(data());
    const headline = screen.getByText("Line ≈ 95 pts (92–98) · You: 20 pts, pace 84");
    expect(headline.closest("details").open).toBe(false); // the card stays short until tapped
    expect(screen.getByText("Need 75 in 64 GP → .586 (now .500)")).toBeInTheDocument();
    expect(screen.getByText(/^Roughly \d+-\d+-\d+ the rest of the way$/)).toBeInTheDocument();
    expect(screen.queryByText(/early estimate/i)).not.toBeInTheDocument();
  });

  it("labels an early estimate", () => {
    show(data({ gp: 6, pts: 6, otl: 0, games_left: 78 }));
    expect(screen.getByText(/early estimate/i)).toBeInTheDocument();
  });

  it("shows clinched and above-the-line teams", () => {
    show(data(), { ...PIT, clinch_indicator: "x" });
    expect(screen.getByText("Clinched ✓")).toBeInTheDocument();
    expect(screen.queryByText(/roughly/i)).not.toBeInTheDocument();
  });

  it("shows a team already above the line", () => {
    show(data({ gp: 70, pts: 96, games_left: 14 }));
    expect(screen.getByText("Above the line")).toBeInTheDocument();
  });

  it("shows eliminated with no record", () => {
    show(data({ gp: 72, pts: 70, games_left: 12 }));
    expect(screen.getByText("Eliminated")).toBeInTheDocument();
    expect(screen.queryByText(/roughly/i)).not.toBeInTheDocument();
  });

  it("hides off-season, on stale data, or without a line", () => {
    const { container, rerender } = show(data({}, { games_remaining: 0 }));
    expect(container).toBeEmptyDOMElement();
    rerender(<PlayoffLine data={data({}, { as_of_date: "2026-04-01" })} team={PIT} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<PlayoffLine data={data({}, { cutline: {} })} team={PIT} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<PlayoffLine data={null} team={PIT} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("the card loads the line from /playoff-line and never /season-sim", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => ({
      ok: true,
      json: async () => (url.endsWith("/playoff-line") ? data() : SCHEDULE),
    }));
    renderCard();
    expect(await screen.findByText("Line ≈ 95 pts (92–98) · You: 20 pts, pace 84")).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([u]) => u);
    expect(urls.some((u) => u.endsWith("/playoff-line"))).toBe(true);
    expect(urls.some((u) => u.includes("/season-sim"))).toBe(false);
    vi.restoreAllMocks();
  });
});
