import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Scoreboard from "./Scoreboard.jsx";
import { sortGames, statusLabel } from "./gameStatus.js";
import { rememberResponse } from "../utils/responseCache.js";
import { API_BASE } from "../config.js";
import { todayISO } from "../utils/dates.js";

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

  it("links a final's recap on NHL.com, and only once it's posted", async () => {
    const withRecap = { ...finalOT, threeMinRecap: "/video/nsh-at-tor-recap-6406612944112" };
    await renderWith([withRecap, upcoming]);

    const links = screen.getAllByRole("link", { name: /recap on NHL.com/ });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://www.nhl.com/video/nsh-at-tor-recap-6406612944112");
    expect(links[0]).toHaveAttribute("target", "_blank");
  });

  it("says when there are no games today", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ games: [] }) });
    render(<MemoryRouter><Scoreboard /></MemoryRouter>);

    expect(await screen.findByText("No games scheduled today.")).toBeInTheDocument();
  });

  it("coming back to Scores shows the last scores immediately, then updates", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ games: [live] }) });
    const first = render(<MemoryRouter><Scoreboard /></MemoryRouter>);
    await screen.findByRole("button", { name: /PIT at WSH/ });
    first.unmount();

    let resolveFresh;
    globalThis.fetch = vi.fn().mockReturnValue(new Promise((r) => { resolveFresh = r; }));
    render(<MemoryRouter><Scoreboard /></MemoryRouter>);

    // Before the refresh lands, the previous scores are already on screen (no blank flash).
    expect(screen.getByRole("button", { name: /PIT at WSH/ })).toBeInTheDocument();
    resolveFresh({ ok: true, json: () => Promise.resolve({ games: [live, upcoming] }) });
    await waitFor(() => expect(screen.getAllByRole("button", { name: / at / })).toHaveLength(2));
  });

  it("shows today's games from the pick'em page's copy of the same response", () => {
    // The pick'em page fetches this URL too and caches the full response.
    rememberResponse(`${API_BASE}/games/date/${todayISO()}`, { games: [live] });
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
    render(<MemoryRouter><Scoreboard /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /PIT at WSH/ })).toBeInTheDocument();
  });
});

describe("Scoreboard with a favorite team", () => {
  afterEach(() => vi.restoreAllMocks());

  it("pins your team's game first and stars it", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { MemoryRouter } = await import("react-router-dom");
    const game = (id, away, home, start) => ({ id, gameState: "FUT", startTimeUTC: start, awayTeam: { abbrev: away }, homeTeam: { abbrev: home } });
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ games: [
      game(1, "BOS", "TOR", "2026-10-12T23:00:00Z"), game(2, "PIT", "CBJ", "2026-10-13T00:00:00Z"),
    ] }) });
    const { default: Scoreboard } = await import("./Scoreboard.jsx");

    render(<MemoryRouter><Scoreboard date="2026-10-12" pinTeam="PIT" /></MemoryRouter>);

    const cards = await screen.findAllByRole("button", { name: / at / });
    expect(cards[0]).toHaveAccessibleName(/PIT at CBJ/);
    expect(cards[0]).toHaveClass("game-card-mine");
    expect(cards[1]).not.toHaveClass("game-card-mine");
  });
});
