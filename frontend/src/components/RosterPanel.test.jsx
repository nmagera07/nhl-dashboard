import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import RosterPanel from "./RosterPanel.jsx";

vi.mock("./TeamNews.jsx", () => ({ default: () => null }));
vi.mock("./SeasonSimulator.jsx", () => ({ default: () => null }));

describe("RosterPanel", () => {
  it("shows each skater's average time on ice", () => {
    const roster = [
      { player_id: 1, first_name: "Sidney", last_name: "Crosby", position_code: "C", sweater_number: 87, games_played: 6, points: 2, avg_toi_seconds: 1190 },
      { player_id: 2, first_name: "Kris", last_name: "Letang", position_code: "D", sweater_number: 58, games_played: 6, points: 3, avg_toi_seconds: null },
    ];
    render(<MemoryRouter><RosterPanel team={null} roster={roster} onSelectPlayer={() => {}} onBack={() => {}} /></MemoryRouter>);

    expect(within(screen.getByRole("table", { name: "Forwards" })).getByText("19:50")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Defense" })).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows the team's lines from its last game, fetched only when opened", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        team: "PIT", game: { id: 1, date: "2026-10-13", opponent: "CHI", home: false },
        lines: [{ players: ["Malkin", "Novak", "Chinakhov"], player_ids: [1, 2, 3], minutes: 9.4 }],
        pairs: [{ players: ["Karlsson", "Girard"], player_ids: [4, 5], minutes: 12.1 }],
      }),
    });
    render(<MemoryRouter><RosterPanel team={{ team_abbrev: "PIT" }} roster={[]} onSelectPlayer={() => {}} onBack={() => {}} /></MemoryRouter>);
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/lines"));

    await userEvent.click(screen.getByText("From the last game"));

    expect(await screen.findByText("Last game: Oct 13 @ CHI")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "PIT forward lines" })).toHaveTextContent(/1.*Malkin.*Novak.*Chinakhov/);
    expect(screen.getByRole("list", { name: "PIT defense pairs" })).toHaveTextContent(/1.*Karlsson.*Girard/);
    vi.restoreAllMocks();
  });
});
