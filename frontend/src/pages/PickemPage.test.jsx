import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PickemPage from "./PickemPage.jsx";
import { todayISO } from "../utils/dates.js";

const today = todayISO();
const later = new Date(Date.now() + 3 * 3600_000).toISOString();
const GAMES = { games: [
  { id: 1, gameType: 2, gameState: "FUT", gameDate: today, startTimeUTC: later, awayTeam: { abbrev: "PHI" }, homeTeam: { abbrev: "DET" } },
  { id: 2, gameType: 2, gameState: "LIVE", gameDate: today, startTimeUTC: later, awayTeam: { abbrev: "MTL" }, homeTeam: { abbrev: "WSH" } },
] };
const SIM = { model: { home_edge: 0.16, scale: 1.457 }, teams: { PHI: { rating: -0.2 }, DET: { rating: 0.3 }, MTL: { rating: 0 }, WSH: { rating: 0 } }, games: [] };
const BOARD = { players: [{ name: "Nate", correct: 7, graded: 10 }], puckpulse: { correct: 30, graded: 45 } };

function mockApi({ me, onPost } = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url, opts) => {
    const body = opts?.body ? JSON.parse(opts.body) : null;
    const reply = (status, json) => ({ ok: status < 300, status, json: async () => json });
    if (url.endsWith("/pickem/join")) return reply(200, { name: body.name, key: "pp_testkey_1234567890" });
    if (url.endsWith("/pickem/me")) return me ? reply(200, me) : reply(401, { detail: "Unknown player key." });
    if (url.endsWith("/pickem/pick")) { onPost?.(body); return reply(200, { game_id: body.game_id, pick: body.team }); }
    if (url.includes("/pickem/leaderboard")) return reply(200, BOARD);
    if (url.includes("/season-sim")) return reply(200, SIM);
    if (url.includes("/games/date/")) return reply(200, GAMES);
    return reply(404, {});
  });
}

const renderPage = () => render(<MemoryRouter><PickemPage /></MemoryRouter>);
const ME = { name: "Nate", record: { correct: 7, graded: 10, pending: 1 }, vs_puckpulse: { you: 7, puckpulse: 6, games: 10 }, date: today, picks: {} };

describe("PickemPage", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("joins with a name and remembers the key", async () => {
    mockApi({ me: ME });
    renderPage();
    await userEvent.type(screen.getByLabelText(/display name/i), "Nate");
    await userEvent.click(screen.getByRole("button", { name: "Join" }));
    expect(await screen.findByText(/1 pending/)).toHaveTextContent("Nate · 7-3 (70%) · 1 pending");
    expect(localStorage.getItem("puckpulse:pickem-key")).toBe("pp_testkey_1234567890");
  });

  it("picks a game, then shows PuckPulse's pick; started games are locked", async () => {
    localStorage.setItem("puckpulse:pickem-key", "pp_saved");
    const posted = [];
    mockApi({ me: ME, onPost: (b) => posted.push(b) });
    renderPage();
    const det = await screen.findByRole("button", { name: "DET" });
    const game = det.closest("li");
    expect(within(game).queryByText(/PuckPulse picks/)).not.toBeInTheDocument(); // hidden until you pick

    await userEvent.click(det);

    expect(det).toHaveAttribute("aria-pressed", "true");
    expect(posted).toEqual([{ key: "pp_saved", game_id: 1, team: "DET" }]);
    expect(within(game).getByText(/PuckPulse picks/)).toHaveTextContent("PuckPulse picks DET (61%)");
    const live = screen.getByRole("button", { name: "WSH" });
    expect(live).toBeDisabled(); // already live: locked, and PuckPulse's pick is shown
    expect(within(live.closest("li")).getByText(/Locked/)).toBeInTheDocument();
  });

  it("shows the leaderboard with PuckPulse as the benchmark", async () => {
    mockApi();
    renderPage();
    const board = await screen.findByRole("table");
    expect(within(board).getByText("Nate")).toBeInTheDocument();
    expect(screen.getByText(/PuckPulse, on every game/)).toHaveTextContent("30-15 (67%)");
  });
});
