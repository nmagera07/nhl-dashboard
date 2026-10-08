import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Scoreboard from "./Scoreboard.jsx";
import { sortGames, statusLabel } from "./gameStatus.js";

const REG = (number) => ({ number, periodType: "REG", maxRegulationPeriods: 3 });

function game(id, overrides = {}) {
  return {
    id,
    gameState: "FUT",
    startTimeUTC: "2026-10-08T23:00:00Z",
    awayTeam: { abbrev: "UTA", logo: "https://example.com/uta.svg", record: "2-2-0" },
    homeTeam: { abbrev: "BOS", logo: "https://example.com/bos.svg", record: "3-1-0" },
    tvBroadcasts: [{ market: "N", network: "TNT" }, { market: "H", network: "NESN" }],
    ...overrides,
  };
}

const live = game(2, {
  gameState: "LIVE",
  startTimeUTC: "2026-10-08T23:30:00Z",
  periodDescriptor: REG(2),
  clock: { timeRemaining: "12:34", inIntermission: false },
  awayTeam: { abbrev: "PIT", score: 1 },
  homeTeam: { abbrev: "WSH", score: 2 },
});
const finalOT = game(3, {
  gameState: "OFF",
  startTimeUTC: "2026-10-08T22:00:00Z",
  gameOutcome: { lastPeriodType: "OT" },
  awayTeam: { abbrev: "NSH", score: 4 },
  homeTeam: { abbrev: "TOR", score: 5 },
});
const upcoming = game(1);

describe("statusLabel", () => {
  it("shows period and clock for a live game", () => {
    expect(statusLabel(live)).toBe("2nd · 12:34");
  });

  it("shows intermission between periods", () => {
    expect(statusLabel({ ...live, clock: { inIntermission: true } })).toBe("2nd Intermission");
  });

  it("marks overtime and shootout finals", () => {
    expect(statusLabel(finalOT)).toBe("Final/OT");
    expect(statusLabel({ ...finalOT, gameOutcome: { lastPeriodType: "SO" } })).toBe("Final/SO");
    expect(statusLabel({ ...finalOT, gameOutcome: { lastPeriodType: "REG" } })).toBe("Final");
  });
});

describe("sortGames", () => {
  it("puts live games first, then upcoming by start time, then finals", () => {
    const later = game(4, { startTimeUTC: "2026-10-09T02:00:00Z" });
    expect(sortGames([finalOT, later, upcoming, live]).map((g) => g.id)).toEqual([2, 1, 4, 3]);
  });
});

describe("Scoreboard", () => {
  async function renderWith(games) {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ games }) });
    render(<MemoryRouter><Scoreboard /></MemoryRouter>);
    return screen.findAllByRole("button", { name: / at / });
  }

  it("shows logos, records, and national TV for upcoming games, with no scores yet", async () => {
    const [card] = await renderWith([upcoming]);

    expect(card.querySelector("img.game-card-logo")).toHaveAttribute("src", "https://example.com/uta.svg");
    expect(within(card).getByText("2-2-0")).toBeInTheDocument();
    expect(within(card).getByText("TNT")).toBeInTheDocument();
    expect(card.querySelector(".game-card-score")).toBeNull();
  });

  it("shows live games first, with scores and the clock", async () => {
    const cards = await renderWith([upcoming, finalOT, live]);

    expect(cards[0]).toHaveAccessibleName("PIT at WSH, 2nd · 12:34");
    expect(cards[0]).toHaveClass("game-card-live");
    expect(within(cards[0]).getByText("2")).toBeInTheDocument();
  });

  it("dims the losing team of a final", async () => {
    const [card] = await renderWith([finalOT]);

    const [away, home] = card.querySelectorAll(".game-card-team");
    expect(away).toHaveClass("is-loser");
    expect(home).toHaveClass("is-winner");
  });

  it("says when there are no games today", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ games: [] }) });
    render(<MemoryRouter><Scoreboard /></MemoryRouter>);

    expect(await screen.findByText("No games scheduled today.")).toBeInTheDocument();
  });
});
