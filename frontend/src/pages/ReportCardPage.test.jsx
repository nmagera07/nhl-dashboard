import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import ReportCardPage from "./ReportCardPage.jsx";

const period = (overrides = {}) => ({
  games: 18,
  moneyline: { games: 18, brier_ours: 0.2211, brier_books: 0.2135, favorite_won_ours: 0.7222, favorite_won_books: 0.6875 },
  puck_line: { games: 16, brier_ours: 0.2033, brier_books: 0.1951 },
  total: { games: 15, brier_ours: 0.2466, brier_books: 0.2515 },
  value_bets: { bets: 0, wins: 0, losses: 0, pushes: 0, profit: 0, list: [] },
  disagreements: [{ date: "2026-10-17", away: "BOS", home: "LAK", ours: 0.61, books: 0.556, home_won: false }],
  ...overrides,
});

function renderWith(body) {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) });
  render(<MemoryRouter><ReportCardPage /></MemoryRouter>);
}

describe("ReportCardPage", () => {
  it("shows favorites, accuracy with the better side marked, and who was closer", async () => {
    renderWith({ as_of: "2026-10-18", week: period(), season: period() });
    expect(await screen.findByText("72%")).toBeInTheDocument();
    expect(screen.getByText("69%")).toBeInTheDocument();
    expect(screen.getByText("0.213")).toHaveClass("rc-better");  // the books' moneyline Brier (0.2135)
    expect(screen.getByText("0.247")).toHaveClass("rc-better");  // our total
    expect(screen.getByText("Books were closer")).toBeInTheDocument();  // we leaned LA; LA lost
    expect(screen.getByText(/No value badges in this stretch/)).toBeInTheDocument();
  });

  it("grades value badges as $100 bets, per period", async () => {
    const season = period({ value_bets: { bets: 2, wins: 1, losses: 1, pushes: 0, profit: 45, list: [
      { date: "2026-10-17", game: "SEA @ FLA", bet: "SEA", price: 165, book: "FanDuel", result: 1, profit: 165 },
      { date: "2026-10-16", game: "PIT @ COL", bet: "COL -1.5", price: 120, book: null, result: -1, profit: -100 }] } });
    renderWith({ as_of: "2026-10-18", week: period(), season });
    await userEvent.click(await screen.findByRole("button", { name: "Season" }));
    expect(screen.getByText("1-1")).toBeInTheDocument();
    expect(screen.getByText("+$45")).toBeInTheDocument();
    expect(screen.getByText("Won +$165")).toBeInTheDocument();
    expect(screen.getByText("Lost $100")).toBeInTheDocument();
  });
});
