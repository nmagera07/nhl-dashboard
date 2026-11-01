import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import BetsPage from "./BetsPage.jsx";
import { loadBets } from "../utils/myBets.js";

const side = (over) => ({ ours: 0.5, fair: 100, market: 0.5, edge: 0, price: -110, ev: -0.05, value: false, ...over });
const BOARD = {
  home: "COL", away: "PIT", b2b: { home: false, away: true }, snapshot: "close",
  goalies: { home: [{ name: "Mackenzie Blackwood", prob: 0.81 }], away: [{ name: "Arturs Silovs", prob: 0.62 }] },
  moneyline: { home: side({ ours: 0.66, fair: -194, price: -150, book: "DraftKings", ev: 0.1, edge: 0.06, value: true }),
               away: side({ ours: 0.34, fair: 194, price: 145, book: "FanDuel" }) },
  puck_line: { home_spread: -1.5, home: side({ price: 150 }), away: side({ price: -175 }) },
  total: { line: 6.5, experimental: true, over: side({ price: -130 }), under: side({ price: 110, ev: 0.15 }) },
};
const game = (id, state, start) => ({ id, gameState: state, startTimeUTC: start, gameType: 2,
                                      awayTeam: { abbrev: "PIT" }, homeTeam: { abbrev: "COL" } });

function mockFetch(games, boards) {
  globalThis.fetch = vi.fn((url) => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(url.includes("/bets") ? { games: boards } : { games }),
  }));
}

describe("BetsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("shows the best moneyline, fair odds, and a value badge for an open game", async () => {
    mockFetch([game(7, "FUT", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    const card = (await screen.findByRole("link", { name: /PIT @ COL/ })).closest("li");
    expect(within(card).getByText("DraftKings")).toBeInTheDocument();
    expect(within(card).getByText("Fair −194")).toBeInTheDocument();
    expect(within(card).getByText("Value +10%")).toBeInTheDocument();
    expect(within(card).getByText(/PIT on the 2nd night of a back-to-back/)).toBeInTheDocument();
    expect(within(card).getByText("COL −1.5")).toBeInTheDocument();
    // Each row says what the bet is, so the puck line price is not read as the moneyline.
    expect(within(card).getByText("to win")).toBeInTheDocument();
    expect(within(card).getByText("−1.5: win by 2+")).toBeInTheDocument();
    expect(within(card).getByText("In net").parentElement).toHaveTextContent("In net Silovs 62% · Blackwood 81%");
    expect(within(card).getAllByText(/^Value/)).toHaveLength(1); // the totals' positive EV is never badged
  });

  it("shows PuckPulse's win chance as a split bar, and each market as its own group", async () => {
    mockFetch([game(7, "FUT", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    expect(await screen.findByRole("img", { name: "PuckPulse win chance: PIT 34%, COL 66%" })).toBeInTheDocument();
    const puckLine = screen.getByRole("group", { name: "Puck line" });
    expect(within(puckLine).getByText("+150")).toBeInTheDocument();
    expect(within(puckLine).queryByText("−150")).not.toBeInTheDocument(); // the moneyline price stays in its own group
  });

  it("names each starter by the best word so far: reporters, then NHL.com, then ours", async () => {
    mockFetch([game(7, "FUT", "2026-10-17T23:00:00Z")], { 7: {
      ...BOARD,
      nhl_starters: { away: "Sergei Murashov", home: "Scott Wedgewood" },
      reported_starters: { away: { name: "Tristan Jarry", status: "confirmed", source: "RotoWire" }, home: null },
    } });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    const line = (await screen.findByText("In net", { selector: ".bets-goalies-label" })).parentElement;
    expect(line).toHaveTextContent("In net Jarry confirmed · Wedgewood NHL.com");
    expect(screen.getByRole("link", { name: "RotoWire" })).toBeInTheDocument();
  });

  it("drops the badges once a game starts", async () => {
    mockFetch([game(7, "LIVE", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    await screen.findByText(/last lines before puck drop/);
    expect(screen.queryByText(/^Value/, { selector: ".bets-badge" })).not.toBeInTheDocument();
  });

  it("tracks a bet at the price shown, and a second tap stops tracking it", async () => {
    mockFetch([game(7, "FUT", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    const pl = await screen.findByRole("button", { name: "Track PIT +1.5 at −175" });
    await userEvent.click(pl);
    expect(pl).toHaveAttribute("aria-pressed", "true");
    expect(within(pl).getByText("✓ Tracking")).toBeInTheDocument();
    expect(loadBets()).toEqual([expect.objectContaining({
      id: "7:puck_line:away", gameId: 7, away: "PIT", home: "COL", market: "puck_line", side: "away", line: 1.5, price: -175,
    })]);
    await userEvent.click(screen.getByRole("button", { name: "Stop tracking PIT +1.5 at −175" }));
    expect(loadBets()).toEqual([]);
  });

  it("can't track a game that has started", async () => {
    mockFetch([game(7, "LIVE", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    await screen.findByText(/last lines before puck drop/);
    expect(screen.queryByRole("button", { name: /^Track/ })).not.toBeInTheDocument();
  });

  it("keeps the responsible-gambling note on the page", async () => {
    mockFetch([], {});
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    expect(await screen.findByText(/No games today/)).toBeInTheDocument();
    expect(screen.getByText(/1-800-GAMBLER/)).toBeInTheDocument();
  });
});

describe("BetsPage win chance", () => {
  it("shows the model's chance, the same as the score tiles, not the fair odds' blend", async () => {
    const board = { ...BOARD, moneyline: { home: { ...BOARD.moneyline.home, model: 0.71 }, away: { ...BOARD.moneyline.away, model: 0.29 } } };
    mockFetch([game(7, "FUT", "2026-10-17T23:00:00Z")], { 7: board });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    expect(await screen.findByRole("img", { name: "PuckPulse win chance: PIT 29%, COL 71%" })).toBeInTheDocument();
    expect(screen.getByText("Fair −194")).toBeInTheDocument(); // the fair odds stay the blend
  });
});
