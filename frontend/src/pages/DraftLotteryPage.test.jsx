import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DraftLotteryPage from "./DraftLotteryPage.jsx";

const picks = (first, second = 0.18, third = 0.5) => [first, second, third, ...Array(13).fill((1 - first - second - third) / 13)];

const DATA = {
  as_of: "2026-10-20", standings_date: "2026-10-20",
  projected: [
    { team: "VAN", missed_playoffs: 0.91, picks: picks(0.15) },
    { team: "PIT", missed_playoffs: 0.62, picks: picks(0.04, 0.04, 0.03) },
    { team: "COL", missed_playoffs: 0.01, picks: Array(16).fill(0) },
  ],
  today: [
    { team: "LAK", position: 1, points: 2, games_played: 6, picks: picks(0.255, 0.188, 0.557) },
    { team: "PIT", position: 9, points: 7, games_played: 8, picks: [0.05, 0.05, 0.04, 0, 0, 0, 0, 0, 0.86, 0, 0, 0, 0, 0, 0, 0] },
  ],
  mock: {
    year: 2027,
    sources: [{ name: "Daily Faceoff", url: "https://df.example", as_of: "2026-10-09" }, { name: "Tankathon", url: "https://tk.example", as_of: "2026-10-08" }],
    projected: Array.from({ length: 32 }, (_, i) => ({
      pick: i + 1, team: i === 0 ? "VAN" : `T${i}`,
      prospect: { name: i === 0 ? "Landon DuPont" : `Prospect ${i + 1}`, pos: "D", team: "Michigan", league: "NCAA", ranks: { "Daily Faceoff": i + 1, Tankathon: null },
                  ...(i === 0 ? { ep: "701503/landon-dupont" } : {}) },
    })),
    today: [{ pick: 1, team: "LAK", prospect: { name: "Sergei Skvortsov", pos: "LW", team: "Torpedo", league: null, ranks: {} } }],
  },
};

describe("DraftLotteryPage", () => {
  beforeEach(() => {
    localStorage.clear();
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(DATA) });
  });

  it("shows the projected chances for the 2027 draft, skipping near-certain playoff teams", async () => {
    render(<MemoryRouter><DraftLotteryPage /></MemoryRouter>);
    expect(await screen.findByText(/No. 1 pick in the 2027 NHL Draft/)).toBeInTheDocument();
    const van = within(screen.getByRole("table")).getByText("VAN").closest("tr");
    expect(within(van).getByText("15.0%")).toBeInTheDocument();
    expect(within(van).getByText("91.0%")).toBeInTheDocument();
    expect(screen.queryByText("COL")).not.toBeInTheDocument();
  });

  it("if the season ended today: exact odds, standings, and the likeliest pick", async () => {
    render(<MemoryRouter><DraftLotteryPage /></MemoryRouter>);
    await userEvent.click(await screen.findByRole("button", { name: "If the season ended today" }));
    const lak = within(screen.getByRole("table")).getByText("LAK").closest("tr");
    expect(within(lak).getByText("25.5%")).toBeInTheDocument();    // at No. 1
    expect(within(lak).getByText("100%")).toBeInTheDocument();     // always top 3
    const pit = within(screen.getByRole("table")).getByText("PIT").closest("tr");
    expect(pit.lastChild).toHaveTextContent("9");                  // likeliest: stays 9th
  });

  it("shows a mock draft for the chosen view, lottery picks first", async () => {
    render(<MemoryRouter><DraftLotteryPage /></MemoryRouter>);
    const first = (await screen.findByText("Landon DuPont")).closest("li");
    expect(within(first).getByText("VAN")).toBeInTheDocument();
    expect(within(first).getByText("D · Michigan (NCAA)")).toBeInTheDocument();
    expect(screen.queryByText("Prospect 17")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show picks 17-32" }));
    expect(screen.getByText("Prospect 17")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tankathon" })).toHaveAttribute("href", "https://tk.example");
    const profile = screen.getByRole("link", { name: "Landon DuPont" });
    expect(profile).toHaveAttribute("href", "https://www.eliteprospects.com/player/701503/landon-dupont");
    expect(profile).toHaveAttribute("target", "_blank");
    expect(screen.queryByRole("link", { name: "Prospect 2" })).not.toBeInTheDocument();  // no profile id: plain name

    await userEvent.click(screen.getByRole("button", { name: "If the season ended today" }));
    expect(screen.getByText("Sergei Skvortsov").closest("li")).toHaveTextContent("LAK");
    expect(screen.queryByText("Landon DuPont")).not.toBeInTheDocument();
  });

  it("highlights your team", async () => {
    localStorage.setItem("nhl-dash:favorite-team", "PIT");
    render(<MemoryRouter><DraftLotteryPage /></MemoryRouter>);
    await screen.findByRole("table");
    expect(within(screen.getByRole("table")).getByText("PIT").closest("tr")).toHaveClass("lottery-row-favorite");
  });
});
