import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { API_BASE } from "../config.js";
import LeaderboardPage from "./LeaderboardPage.jsx";

vi.mock("../hooks/useFetchWithStatus.js", () => ({
  useFetchWithStatus: vi.fn(() => ({ data: [], status: "ready" })),
}));
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";

describe("LeaderboardPage", () => {
  it("fetches the slim ?view=table leaders, not the full response", () => {
    render(<MemoryRouter><LeaderboardPage /></MemoryRouter>);
    expect(useFetchWithStatus).toHaveBeenCalledWith(`${API_BASE}/players/leaders?view=table`, expect.any(Object));
    expect(screen.queryByText(/couldn't load/i)).not.toBeInTheDocument();
  });
});
