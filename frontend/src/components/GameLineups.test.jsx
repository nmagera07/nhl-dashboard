import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import GameLineups from "./GameLineups.jsx";

const TEAM = (goalie) => ({
  forwards: [["Matthew Knies", "Adam Fantilli", "Kent Johnson"], ["Parker Kelly", "Gavin Brindley"]],
  defense: [["Zach Werenski", "Damon Severson"], ["Noah Juulsen"]],
  goalies: [goalie, "Jet Greaves"], scratched: ["Carson Soucy"], injured: [{ name: "Dante Fabbro", detail: "broken hand" }],
});

function mockFetch(byUrl) {
  globalThis.fetch = vi.fn((url) => {
    const key = Object.keys(byUrl).find((k) => url.includes(k));
    return Promise.resolve({ ok: true, json: () => Promise.resolve(byUrl[key]) });
  });
}

const away = { abbrev: "CBJ" };
const home = { abbrev: "MIN" };

describe("GameLineups", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows NHL.com's projected lineup, one team at a time, with labeled lines", async () => {
    mockFetch({ "/lineup": { available: true, url: "https://www.nhl.com/news/x", published: "2026-10-18T17:58:00Z",
                             away: { abbrev: "CBJ", ...TEAM("Cam Talbot") }, home: { abbrev: "MIN", ...TEAM("Jesper Wallstedt") } } });
    render(<GameLineups gameId={1} away={away} home={home} />);
    await userEvent.click(await screen.findByText("Tonight's projected lineup · NHL.com"));
    const forwards = screen.getByRole("list", { name: "CBJ forward lines" });
    expect(forwards).toHaveTextContent("L1Knies – Fantilli – Johnson");
    expect(forwards).toHaveTextContent("L2Kelly – Brindley");  // an 11-forward night
    expect(screen.getByRole("list", { name: "CBJ defense pairs" })).toHaveTextContent("7DJuulsen");
    expect(screen.getByText("Cam Talbot")).toBeInTheDocument();
    expect(screen.getByText(/Dante Fabbro \(broken hand\)/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Status report on NHL.com/ })).toHaveAttribute("href", "https://www.nhl.com/news/x");

    await userEvent.click(screen.getByRole("button", { name: "MIN" }));
    expect(screen.getByText("Jesper Wallstedt")).toBeInTheDocument();
  });

  it("falls back to each team's last game before NHL.com posts", async () => {
    mockFetch({
      "/lineup": { available: false },
      "/teams/CBJ/lines": { team: "CBJ", game: { id: 9, date: "2026-10-17", opponent: "NYR", home: true },
                            lines: [{ players: ["Knies", "Fantilli", "Johnson"], player_ids: [1, 2, 3], minutes: 15.9 }], pairs: [] },
    });
    render(<GameLineups gameId={1} away={away} home={home} />);
    await userEvent.click(await screen.findByText("From each team's last game"));
    expect(await screen.findByRole("list", { name: "CBJ forward lines" })).toHaveTextContent("L1Knies – Fantilli – Johnson");
    expect(screen.queryByText(/min$/)).not.toBeInTheDocument();  // no minutes-together column
  });
});
