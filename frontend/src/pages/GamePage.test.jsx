import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import GamePage from "./GamePage.jsx";

const REG = (number) => ({ number, periodType: "REG", maxRegulationPeriods: 3 });
const OT = { number: 4, periodType: "OT", maxRegulationPeriods: 3 };

function skater(overrides) {
  return {
    playerId: 1, sweaterNumber: 9, name: { default: "F. Forsberg" }, position: "L",
    goals: 0, assists: 0, points: 0, plusMinus: 0, pim: 0, hits: 0, sog: 0, blockedShots: 0, toi: "15:00",
    ...overrides,
  };
}

// Shaped like the backend's merged /games/{id}/boxscore response
// (NHL boxscore + landing summary + right-rail linescore/stats).
function finalGame(overrides = {}) {
  return {
    id: 2026020044,
    gameState: "OFF",
    gameDate: "2026-10-06",
    venue: { default: "Scotiabank Arena" },
    gameOutcome: { lastPeriodType: "OT" },
    awayTeam: { abbrev: "NSH", score: 4, placeName: { default: "Nashville" }, commonName: { default: "Predators" } },
    homeTeam: { abbrev: "TOR", score: 5, placeName: { default: "Toronto" }, commonName: { default: "Maple Leafs" } },
    linescore: {
      byPeriod: [
        { periodDescriptor: REG(1), away: 2, home: 0 },
        { periodDescriptor: REG(2), away: 2, home: 3 },
        { periodDescriptor: REG(3), away: 0, home: 1 },
        { periodDescriptor: OT, away: 0, home: 1 },
      ],
      totals: { away: 4, home: 5 },
    },
    shotsByPeriod: [
      { periodDescriptor: REG(1), away: 11, home: 8 },
      { periodDescriptor: REG(2), away: 7, home: 13 },
    ],
    summary: {
      scoring: [
        {
          periodDescriptor: REG(1),
          goals: [{
            eventId: 1, timeInPeriod: "07:13", strength: "pp", goalModifier: "none",
            name: { default: "S. Stamkos" }, goalsToDate: 2, teamAbbrev: { default: "NSH" },
            awayScore: 1, homeScore: 0,
            assists: [{ name: { default: "M. Wood" }, assistsToDate: 1 }, { name: { default: "R. Josi" }, assistsToDate: 3 }],
          }],
        },
        { periodDescriptor: OT, goals: [] },
      ],
      threeStars: [{ star: 1, name: { default: "G. McKenna" }, teamAbbrev: "TOR", position: "L", goals: 1, assists: 1 }],
    },
    teamGameStats: [
      { category: "sog", awayValue: 25, homeValue: 37 },
      { category: "faceoffWinningPctg", awayValue: 0.358491, homeValue: 0.641509 },
      { category: "faceoffWins", awayValue: "19/53", homeValue: "34/53" },
      { category: "powerPlay", awayValue: "1/3", homeValue: "0/2" },
    ],
    playerByGameStats: {
      awayTeam: {
        forwards: [skater({ playerId: 11, name: { default: "S. Stamkos" }, goals: 1, points: 1 })],
        defense: [skater({ playerId: 12, name: { default: "R. Josi" }, assists: 1, points: 1 })],
        goalies: [
          { playerId: 13, sweaterNumber: 74, name: { default: "J. Saros" }, shotsAgainst: 37, saves: 32, goalsAgainst: 5, toi: "62:00" },
          { playerId: 14, sweaterNumber: 30, name: { default: "Backup" }, shotsAgainst: 0, saves: 0, goalsAgainst: 0, toi: "00:00" },
        ],
      },
      homeTeam: {
        forwards: [skater({ playerId: 21, name: { default: "G. McKenna" }, goals: 1, assists: 1, points: 2 })],
        defense: [],
        goalies: [],
      },
    },
    ...overrides,
  };
}

function renderGame(game, props = {}, simInputs = null, routes = {}) {
  globalThis.fetch = vi.fn().mockImplementation((url) => {
    const extra = Object.keys(routes).find((path) => url.includes(path));
    const body = extra ? routes[extra] : url.includes("/season-sim") ? simInputs : game;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  return render(
    <MemoryRouter initialEntries={["/games/2026020044"]}>
      <Routes>
        <Route path="/games/:gameId" element={<GamePage {...props} />} />
      </Routes>
    </MemoryRouter>
  );
}

const loaded = () => screen.findByText("Box score");

describe("GamePage", () => {
  it("shows the final score with the OT outcome", async () => {
    renderGame(finalGame());
    await loaded();

    expect(screen.getByText("Final/OT")).toBeInTheDocument();
    expect(screen.getByText("Nashville Predators")).toBeInTheDocument();
    expect(screen.getByText("Toronto Maple Leafs")).toBeInTheDocument();
  });

  it("renders a period-by-period linescore with an OT column and totals", async () => {
    renderGame(finalGame());
    await loaded();

    const goals = within(screen.getByRole("table", { name: "Goals" }));
    expect(goals.getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Goals", "1", "2", "3", "OT", "T"]);
    const [, awayRow, homeRow] = goals.getAllByRole("row");
    expect(within(awayRow).getAllByRole("cell").map((td) => td.textContent)).toEqual(["NSH", "2", "2", "0", "0", "4"]);
    expect(within(homeRow).getAllByRole("cell").map((td) => td.textContent)).toEqual(["TOR", "0", "3", "1", "1", "5"]);
  });

  it("totals shots on goal from the per-period counts", async () => {
    renderGame(finalGame());
    await loaded();

    const [, awayRow] = within(screen.getByRole("table", { name: "Shots" })).getAllByRole("row");
    expect(within(awayRow).getAllByRole("cell").at(-1)).toHaveTextContent("18");
  });

  it("links the recap, condensed game, and each goal's clip on NHL.com", async () => {
    const game = finalGame({ gameVideo: { threeMinRecap: "/video/nsh-at-tor-recap-1", condensedGame: "/video/nsh-at-tor-condensed-game-2" } });
    game.summary.scoring[0].goals[0].highlightClipSharingUrl = "https://nhl.com/video/nsh-tor-stamkos-scores-3";
    renderGame(game);
    await loaded();

    expect(screen.getByRole("link", { name: /3-minute recap/ })).toHaveAttribute("href", "https://www.nhl.com/video/nsh-at-tor-recap-1");
    expect(screen.getByRole("link", { name: /Condensed game/ })).toHaveAttribute("href", "https://www.nhl.com/video/nsh-at-tor-condensed-game-2");
    expect(screen.getByRole("link", { name: "Watch S. Stamkos's goal on NHL.com" }))
      .toHaveAttribute("href", "https://nhl.com/video/nsh-tor-stamkos-scores-3");
  });

  it("hides the highlights card until the NHL posts videos", async () => {
    renderGame(finalGame());
    await loaded();

    expect(screen.queryByText("Highlights")).toBeNull();
    expect(screen.queryByRole("link", { name: /Watch/ })).toBeNull();
  });

  it("lists goals with scorer, assists, strength, and running score, skipping empty periods", async () => {
    renderGame(finalGame());
    await loaded();

    expect(screen.getByText("S. Stamkos (2)")).toBeInTheDocument();
    expect(screen.getByText("Assists: M. Wood (1), R. Josi (3)")).toBeInTheDocument();
    expect(screen.getByText("PP")).toBeInTheDocument();
    expect(screen.getByText("NSH 1–0 TOR")).toBeInTheDocument();
    expect(screen.getByText("1ST PERIOD")).toBeInTheDocument();
    expect(screen.queryByText("OT", { selector: ".trend-eyebrow" })).not.toBeInTheDocument();
  });

  it("shows team stats with readable labels and formatted percentages", async () => {
    renderGame(finalGame());
    await loaded();

    expect(within(screen.getByRole("heading", { name: "Team stats" }).closest("section")).getByText("Shots on goal")).toBeInTheDocument();
    expect(screen.getByText("35.8%")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    // Redundant categories are dropped.
    expect(screen.queryByText("19/53")).not.toBeInTheDocument();
  });

  it("shows one team's players at a time and hides goalies who didn't play", async () => {
    renderGame(finalGame());
    await loaded();

    const panel = () => within(screen.getByRole("tabpanel"));
    expect(panel().getByRole("table", { name: "Forwards" })).toHaveTextContent("S. Stamkos");
    expect(panel().getByRole("table", { name: "Goalies" })).toHaveTextContent(".865");
    expect(panel().queryByText("Backup")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "TOR" }));

    expect(panel().getByRole("table", { name: "Forwards" })).toHaveTextContent("G. McKenna");
    expect(panel().queryByText("S. Stamkos")).not.toBeInTheDocument();
  });

  it("previews a game that hasn't started: win probability, matchup, players to watch", async () => {
    const upcoming = finalGame({
      gameState: "FUT", linescore: {}, shotsByPeriod: [], summary: {}, teamGameStats: [],
      awayTeam: { abbrev: "NSH", record: "2-3-0" }, homeTeam: { abbrev: "TOR", record: "4-1-0" },
      teamSeasonStats: {
        awayTeam: { goalsForPerGamePlayed: 2.4, goalsForPerGamePlayedRank: 25, ppPctg: 0.2 },
        homeTeam: { goalsForPerGamePlayed: 4.0, goalsForPerGamePlayedRank: 2, ppPctg: 0.3 },
      },
      last10Record: {
        awayTeam: { record: "2-3-0", streakType: "L", streak: 2, pastGameResults: [{ opponentAbbrev: "BOS", gameResult: "L" }] },
        homeTeam: { record: "4-1-0", streakType: "W", streak: 3, pastGameResults: [{ opponentAbbrev: "MTL", gameResult: "SOL" }] },
      },
      matchup: {
        skaterComparison: { leaders: [{ category: "points", awayLeader: { name: { default: "F. Forsberg" }, value: 5 }, homeLeader: { name: { default: "W. Nylander" }, value: 9 } }] },
        goalieComparison: { awayTeam: { leaders: [{ name: { default: "J. Saros" }, record: "2-2-0", gaa: 3.1, savePctg: 0.899 }] }, homeTeam: { leaders: [] } },
      },
    });
    const sim = { model: { home_edge: 0.264, scale: 1.47 }, teams: { NSH: { rating: -0.2 }, TOR: { rating: 0.3 } } };
    renderGame(upcoming, { standings: [], playoffOddsByTeam: { NSH: 0.31, TOR: 0.82 } }, sim);

    expect(await screen.findByRole("img", { name: /NSH \d+% chance to win, TOR \d+%/ })).toBeInTheDocument();
    expect(screen.getByText(/not betting advice/i)).toBeInTheDocument();
    expect(screen.getByText("2-3-0", { selector: ".game-team-record" })).toBeInTheDocument();  // record under the logo
    expect(screen.getByText("4.00 (2nd)")).toHaveClass("preview-better");                  // better stat highlighted
    expect(screen.getByText("82%")).toBeInTheDocument();                                     // playoff odds
    expect(screen.getByText("W. Nylander · 9")).toBeInTheDocument();
    expect(screen.getByText(/J\. Saros · 2-2-0 · 3\.10 GAA · 0\.899/)).toBeInTheDocument();
    expect(screen.getByTitle("SOL vs MTL")).toHaveTextContent("SO");
    expect(screen.queryByText("Box score")).not.toBeInTheDocument();
  });

  it("shows games in net, and loads each team's lines only when opened", async () => {
    const upcoming = finalGame({
      gameState: "FUT", linescore: {}, shotsByPeriod: [], summary: {}, teamGameStats: [],
      awayTeam: { id: 18, abbrev: "NSH" }, homeTeam: { id: 10, abbrev: "TOR" },
      matchup: {
        goalieComparison: { awayTeam: { leaders: [] }, homeTeam: { leaders: [] } },
        goalieSeasonStats: { goalies: [
          { teamId: 18, name: { default: "J. Saros" }, gamesPlayed: 4 },
          { teamId: 18, name: { default: "J. Annunen" }, gamesPlayed: 1 },
          { teamId: 10, name: { default: "A. Stolarz" }, gamesPlayed: 5 },
          { teamId: 10, name: { default: "D. Hildeby" } },
        ] },
      },
    });
    const lines = (abbrev) => ({
      team: abbrev,
      game: { id: 1, date: "2026-10-12", opponent: "BUF", home: abbrev === "TOR" },
      lines: [{ players: ["Knies", "Matthews", "Marner"], player_ids: [1, 2, 3], minutes: 41 }],
      pairs: [{ players: ["Rielly", "McCabe"], player_ids: [4, 5], minutes: 55 }],
    });
    renderGame(upcoming, { standings: [] }, null, { "/teams/NSH/lines": lines("NSH"), "/teams/TOR/lines": lines("TOR") });

    expect(await screen.findByText("Saros 4 · Annunen 1")).toBeInTheDocument();
    expect(screen.getByText("Stolarz 5")).toBeInTheDocument();  // a goalie with no games isn't listed
    expect(globalThis.fetch).not.toHaveBeenCalledWith(expect.stringContaining("/lines"));

    await userEvent.click(screen.getByText("From each team's last game"));

    expect(await screen.findByRole("list", { name: "TOR forward lines" })).toHaveTextContent("Knies – Matthews – Marner41 min");
    expect(screen.getByRole("list", { name: "NSH defense pairs" })).toHaveTextContent("Rielly – McCabe");
    expect(screen.getByRole("heading", { name: "TOR · Oct 12 vs BUF" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NSH · Oct 12 @ BUF" })).toBeInTheDocument();
    expect(screen.getByText(/Not tonight's confirmed lineup/)).toBeInTheDocument();
  });

  it("a team on the second night of a back-to-back shifts the odds, and the preview says so", async () => {
    const upcoming = finalGame({
      gameState: "FUT", gameDate: "2026-10-14", linescore: {}, shotsByPeriod: [], summary: {}, teamGameStats: [],
      awayTeam: { abbrev: "DAL" }, homeTeam: { abbrev: "COL" }, matchup: {},
    });
    const sim = { model: { home_edge: 0.16, scale: 1.457, home_b2b: -0.306, away_b2b: 0.53 },
                  teams: { DAL: { rating: 0.1 }, COL: { rating: 0.1 } }, games: [["2026-10-14", "COL", "DAL", false, true]] };
    renderGame(upcoming, { standings: [] }, sim);

    // Equal teams: home ice (0.16) plus a tired road team (0.53) -> 62%.
    expect(await screen.findByRole("img", { name: "DAL 38% chance to win, COL 62%" })).toBeInTheDocument();
    expect(screen.getByText(/DAL played last night/)).toBeInTheDocument();
  });

  it("Market view compares the model with the sportsbooks, only when opened", async () => {
    const upcoming = finalGame({
      id: 2026020120, gameState: "FUT", gameDate: "2026-10-15", linescore: {}, shotsByPeriod: [], summary: {}, teamGameStats: [],
      awayTeam: { abbrev: "PHI" }, homeTeam: { abbrev: "DET" }, matchup: {},
    });
    const sim = { model: { home_edge: 0.16, scale: 1.457 }, teams: { PHI: { rating: -0.2 }, DET: { rating: 0.3 } }, games: [] };
    const market = { date: "2026-10-15", games: { 2026020120: { home: "DET", away: "PHI", home_prob: 0.558, home_line: -138, away_line: 117, books: 9 } } };
    renderGame(upcoming, { standings: [] }, sim, { "/market-odds": market });
    await screen.findByRole("img", { name: /PHI \d+% chance to win, DET \d+%/ });
    expect(globalThis.fetch).not.toHaveBeenCalledWith(expect.stringContaining("/market-odds"));

    await userEvent.click(screen.getByText("How the betting markets see it"));

    // Ours: (0.3 + 0.2 + 0.16) / 1.457 -> 61%; the books: 56%.
    expect(await screen.findByText("DET 61%")).toBeInTheDocument();
    expect(screen.getByText("DET 56%")).toBeInTheDocument();
    expect(screen.getByText("DET −138 · PHI +117 · median of 9 books")).toBeInTheDocument();
    expect(screen.getByText("PuckPulse is 5 points higher on DET than the books.")).toBeInTheDocument();
    expect(screen.getByText(/1-800-GAMBLER/)).toBeInTheDocument();
  });

  it("shows each team's record from the standings once the game has started", async () => {
    const standings = [
      { team_abbrev: "NSH", wins: 3, losses: 2, ot_losses: 1 },
      { team_abbrev: "TOR", wins: 4, losses: 1, ot_losses: 0 },
    ];
    renderGame(finalGame(), { standings });
    await loaded();

    expect(screen.getByText("3-2-1", { selector: ".game-team-record" })).toBeInTheDocument();
    expect(screen.getByText("4-1-0", { selector: ".game-team-record" })).toBeInTheDocument();
  });

  it("shows the period and clock for a live game and refreshes it", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const live = finalGame({ gameState: "LIVE", periodDescriptor: REG(2), clock: { timeRemaining: "12:34", inIntermission: false } });
      renderGame(live);

      expect(await screen.findByText("2nd · 12:34")).toBeInTheDocument();
      expect(globalThis.fetch).toHaveBeenCalledTimes(1);

      await act(() => vi.advanceTimersByTimeAsync(30000));

      expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("links back to the scoreboard day the game was opened from", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(finalGame()) });
    render(
      <MemoryRouter initialEntries={[{ pathname: "/games/2026020044", state: { from: "/?date=2026-10-06" } }]}>
        <Routes>
          <Route path="/games/:gameId" element={<GamePage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByRole("link", { name: "← Scores" })).toHaveAttribute("href", "/?date=2026-10-06");
  });

  it("shows the API's error message when the box score can't be loaded", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({ detail: "The NHL live game feed is temporarily unavailable." }) });
    render(
      <MemoryRouter initialEntries={["/games/2026020044"]}>
        <Routes>
          <Route path="/games/:gameId" element={<GamePage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
  });
});
