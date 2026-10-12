import { render, screen, within } from "@testing-library/react";
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
});
