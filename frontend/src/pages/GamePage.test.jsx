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

function renderGame(game) {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(game) });
  return render(
    <MemoryRouter initialEntries={["/games/2026020044"]}>
      <Routes>
        <Route path="/games/:gameId" element={<GamePage />} />
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

    expect(screen.getByText("Shots on goal")).toBeInTheDocument();
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

  it("shows a pre-game message and no box score for a game that hasn't started", async () => {
    renderGame(finalGame({ gameState: "FUT", linescore: {}, shotsByPeriod: [], summary: {}, teamGameStats: [] }));

    expect(await screen.findByText(/hasn't started yet/i)).toBeInTheDocument();
    expect(screen.queryByText("Box score")).not.toBeInTheDocument();
    expect(screen.queryByText("Player stats")).not.toBeInTheDocument();
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
