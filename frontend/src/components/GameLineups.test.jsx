import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

  it("shows NHL.com's projected lineup as a depth chart, one team at a time", async () => {
    mockFetch({
      "/lineup": { available: true, url: "https://www.nhl.com/news/x", published: "2026-10-18T17:58:00Z",
                   away: { abbrev: "CBJ", ...TEAM("Cam Talbot") }, home: { abbrev: "MIN", ...TEAM("Jesper Wallstedt") } },
      "/teams/CBJ/roster": [{ player_id: 8482113, first_name: "Matthew", last_name: "Knies", sweater_number: 23,
                              headshot_url: "https://assets.nhle.com/mugs/knies.png" }],
      "/teams/MIN/roster": [],
    });
    render(<MemoryRouter><GameLineups gameId={1} away={away} home={home} /></MemoryRouter>);
    await userEvent.click(await screen.findByText("Tonight's projected lineup · NHL.com"));
    const [first, second] = within(screen.getByRole("list", { name: "CBJ forward lines" })).getAllByRole("listitem");
    expect(first).toHaveTextContent(/1.*Knies.*Fantilli.*Johnson/);
    expect(second).toHaveTextContent(/2.*Kelly.*Brindley/);  // an 11-forward night
    const knies = await within(first).findByRole("link", { name: /Knies/ });
    expect(knies).toHaveAttribute("href", "/players/8482113");  // matched to the roster by name
    expect(within(knies).getByLabelText("number 23")).toBeInTheDocument();
    expect(within(first).queryByRole("link", { name: /Fantilli/ })).not.toBeInTheDocument();  // not on the roster: shown, unlinked
    expect(screen.getByRole("list", { name: "CBJ defense pairs" })).toHaveTextContent(/7D.*Juulsen/);
    const goalies = screen.getByRole("list", { name: "CBJ goalies" });
    expect(goalies).toHaveTextContent(/Talbot.*Likely starter.*Greaves/);
    expect(screen.getByText("Dante Fabbro (broken hand)")).toBeInTheDocument();
    expect(screen.getByText("Carson Soucy")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Status report on NHL.com/ })).toHaveAttribute("href", "https://www.nhl.com/news/x");

    await userEvent.click(screen.getByRole("button", { name: "MIN" }));
    expect(screen.getByRole("list", { name: "MIN goalies" })).toHaveTextContent("Wallstedt");
  });

  it("falls back to each team's last game before NHL.com posts", async () => {
    mockFetch({
      "/lineup": { available: false },
      "/teams/CBJ/lines": { team: "CBJ", game: { id: 9, date: "2026-10-17", opponent: "NYR", home: true },
                            lines: [{ players: ["Knies", "Fantilli", "Johnson"], player_ids: [1, 2, 3], minutes: 15.9 }], pairs: [] },
      "/teams/CBJ/roster": [{ player_id: 2, first_name: "Adam", last_name: "Fantilli", sweater_number: 19 }],
    });
    render(<MemoryRouter><GameLineups gameId={1} away={away} home={home} /></MemoryRouter>);
    await userEvent.click(await screen.findByText("From each team's last game"));
    const line = (await screen.findByRole("list", { name: "CBJ forward lines" })).querySelector("li");
    expect(line).toHaveTextContent(/1.*Knies.*Fantilli.*Johnson/);
    expect(await within(line).findByRole("link", { name: /Fantilli/ })).toHaveAttribute("href", "/players/2");  // matched by id
    expect(screen.queryByText(/min$/)).not.toBeInTheDocument();  // no minutes-together column
  });
});
