import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import BetsPage from "./BetsPage.jsx";

const side = (over) => ({ ours: 0.5, fair: 100, market: 0.5, edge: 0, price: -110, ev: -0.05, value: false, ...over });
const BOARD = {
  home: "COL", away: "PIT", b2b: { home: false, away: true }, snapshot: "close",
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
  beforeEach(() => vi.restoreAllMocks());

  it("shows the best moneyline, fair odds, and a value badge for an open game", async () => {
    mockFetch([game(7, "FUT", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    const card = (await screen.findByRole("link", { name: /PIT @ COL/ })).closest("li");
    expect(within(card).getByText("DraftKings")).toBeInTheDocument();
    expect(within(card).getByText("fair −194")).toBeInTheDocument();
    expect(within(card).getByText("Value +10%")).toBeInTheDocument();
    expect(within(card).getByText(/PIT on the 2nd night of a back-to-back/)).toBeInTheDocument();
    expect(within(card).getByText("COL −1.5")).toBeInTheDocument();
    expect(within(card).getAllByText(/^Value/)).toHaveLength(1); // the totals' positive EV is never badged
  });

  it("drops the badges once a game starts", async () => {
    mockFetch([game(7, "LIVE", "2026-10-17T23:00:00Z")], { 7: BOARD });
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    await screen.findByText(/last lines before puck drop/);
    expect(screen.queryByText(/^Value/, { selector: ".bets-badge" })).not.toBeInTheDocument();
  });

  it("keeps the responsible-gambling note on the page", async () => {
    mockFetch([], {});
    render(<MemoryRouter><BetsPage /></MemoryRouter>);
    expect(await screen.findByText(/No games today/)).toBeInTheDocument();
    expect(screen.getByText(/1-800-GAMBLER/)).toBeInTheDocument();
  });
});
