import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PickemCard from "./PickemCard.jsx";
import GamePick from "./GamePick.jsx";
import { clearResponseCache } from "../utils/responseCache.js";
import { todayISO } from "../utils/dates.js";

const today = todayISO();
const later = new Date(Date.now() + 3 * 3600_000).toISOString();
const OPEN = { id: 1, gameType: 2, gameState: "FUT", gameDate: today, startTimeUTC: later, awayTeam: { abbrev: "PHI" }, homeTeam: { abbrev: "DET" } };
const LIVE = { id: 2, gameType: 2, gameState: "LIVE", gameDate: today, startTimeUTC: later, awayTeam: { abbrev: "MTL" }, homeTeam: { abbrev: "WSH" } };
const BOARD = { players: [{ name: "agent00", correct: 16, graded: 34 }, { name: "Nate", correct: 7, graded: 10 },
  { name: "Mighty Ducks", correct: 1, graded: 4 }, { name: "Fourth", correct: 0, graded: 2 }], puckpulse: { correct: 42, graded: 67 } };
const ME = { name: "Nate", record: { correct: 7, graded: 10, pending: 0 }, vs_puckpulse: { games: 0 }, picks: { 1: "DET" } };

function mockApi({ games = [OPEN, LIVE], posts = [] } = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url, opts) => {
    const reply = (json) => ({ ok: true, status: 200, json: async () => json });
    if (opts?.body) posts.push([url, JSON.parse(opts.body)]);
    if (url.includes("/games/date/")) return reply({ games });
    if (url.endsWith("/pickem/leaderboard")) return reply(BOARD);
    if (url.endsWith("/pickem/me")) return reply(ME);
    if (url.endsWith("/pickem/pick")) return reply({ ok: true });
    throw new Error(`unexpected ${url}`);
  });
}

const renderIt = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("PickemCard", () => {
  beforeEach(() => { localStorage.clear(); clearResponseCache(); });
  afterEach(() => vi.restoreAllMocks());

  it("invites you in with PuckPulse's record and the top three", async () => {
    mockApi();
    renderIt(<PickemCard />);
    expect(await screen.findByText(/PuckPulse is 42-25/)).toBeInTheDocument();
    expect(screen.getByText("Can you beat PuckPulse?")).toBeInTheDocument();
    expect(screen.getByLabelText("Leaderboard top three")).toHaveTextContent("1agent00 162Nate 73Mighty Ducks 1");
    expect(screen.getByRole("link")).toHaveAttribute("href", "/pickem");
    expect(screen.getByText("Play ›")).toBeInTheDocument();
  });

  it("shows your picks and rank once you've joined", async () => {
    localStorage.setItem("puckpulse:pickem-key", "pp_saved");
    mockApi();
    renderIt(<PickemCard />);
    expect(await screen.findByText("1 of 2 picked")).toBeInTheDocument();
    expect(screen.getByText("You're 2nd of 4 on the leaderboard")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByText("Finish picks ›")).toBeInTheDocument();
  });

  it("stays hidden on a day without games", async () => {
    const fetchMock = mockApi({ games: [] });
    const { container } = renderIt(<PickemCard />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(container).toBeEmptyDOMElement();
  });
});

describe("GamePick", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("links to join before you have a pick'em name", () => {
    mockApi();
    renderIt(<GamePick game={OPEN} />);
    expect(screen.getByRole("link", { name: /pick PHI or DET before puck drop/ })).toHaveAttribute("href", "/pickem");
  });

  it("shows your pick and lets you change it", async () => {
    localStorage.setItem("puckpulse:pickem-key", "pp_saved");
    const posts = [];
    mockApi({ posts });
    renderIt(<GamePick game={OPEN} />);
    expect(await screen.findByRole("button", { name: "DET", pressed: true })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "PHI" }));

    expect(screen.getByRole("button", { name: "PHI", pressed: true })).toBeInTheDocument();
    expect(posts.at(-1)).toEqual([expect.stringContaining("/pickem/pick"), { key: "pp_saved", game_id: 1, team: "PHI" }]);
  });

  it("is gone once the game starts", () => {
    localStorage.setItem("puckpulse:pickem-key", "pp_saved");
    mockApi();
    const { container } = renderIt(<GamePick game={LIVE} />);
    expect(container).toBeEmptyDOMElement();
  });
});
