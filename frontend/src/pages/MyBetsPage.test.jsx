import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import MyBetsPage from "./MyBetsPage.jsx";
import { loadBets, saveBets } from "../utils/myBets.js";

const BET = { id: "7:moneyline:home", gameId: 7, date: "2026-10-27", away: "PIT", home: "COL", market: "moneyline",
              side: "home", line: null, price: -150, placedAt: "2026-10-27T15:00:00Z" };
const OPEN = { ...BET, id: "9:total:over", gameId: 9, date: "2099-01-01", away: "TBL", home: "FLA", market: "total", side: "over", line: 6.5, price: -110 };

function serve() {
  globalThis.fetch = vi.fn((url) => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(url.includes("/bets")
      ? { games: { 7: { snapshot: "close", moneyline: { home: { market: 0.64, price: -175 } } } } }
      : { games: [{ id: 7, gameState: "OFF", awayTeam: { score: 1 }, homeTeam: { score: 3 } }] }),
  }));
}

const renderPage = () => render(<MemoryRouter><MyBetsPage /></MemoryRouter>);

describe("MyBetsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("points to the Bets tab when nothing is tracked", () => {
    renderPage();
    expect(screen.getByText(/No bets yet/)).toBeInTheDocument();
  });

  it("grades a finished game, saves the result, and leaves a future bet open", async () => {
    saveBets([BET, OPEN]);
    serve();
    renderPage();
    expect(await screen.findByText("Won +0.67u")).toBeInTheDocument();
    expect(screen.getByText("+7% vs. the close (−175)")).toBeInTheDocument();
    expect(screen.getByText(/Beat the closing line on/)).toHaveTextContent("Beat the closing line on 1 of 1 (average +7%)");
    expect(within(screen.getByRole("heading", { name: "Open" }).parentElement).getByText("Over 6.5")).toBeInTheDocument();
    expect(loadBets().find((b) => b.id === BET.id).result).toMatchObject({ outcome: "win", clv: 0.0667 });
    // Only the past day is fetched; graded bets aren't fetched again.
    expect(globalThis.fetch.mock.calls.every(([url]) => url.includes("2026-10-27"))).toBe(true);
  });

  it("removes a bet", async () => {
    saveBets([OPEN]);
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: /Remove Over 6.5/ }));
    expect(loadBets()).toEqual([]);
    expect(screen.getByText(/No bets yet/)).toBeInTheDocument();
  });
});
