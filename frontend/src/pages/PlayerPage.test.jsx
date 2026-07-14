import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import PlayerPage from "./PlayerPage.jsx";

const player = {
  player_id: 8477492,
  first_name: "Nathan",
  last_name: "MacKinnon",
  position_code: "C",
  team_abbrev: "COL",
  season_stats: [],
  advanced_stats: null,
};

function renderAt(path, { state } = {}) {
  globalThis.fetch = vi.fn().mockResolvedValue({ json: () => Promise.resolve(player) });

  const initialEntries = [{ pathname: path, state }];

  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/players/:playerId" element={<PlayerPage />} />
        <Route path="/leaderboard" element={<div>Leaderboard page</div>} />
        <Route path="/teams/:teamAbbrev" element={<div>Roster page</div>} />
        <Route path="/" element={<div>Standings page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("PlayerPage", () => {
  it("shows a loading state, then the player once the fetch resolves", async () => {
    renderAt("/players/8477492");

    expect(screen.getByText("Loading player…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/mackinnon/i)).toBeInTheDocument());
  });

  it("shows an error state when the fetch fails", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network down"));

    render(
      <MemoryRouter initialEntries={["/players/8477492"]}>
        <Routes>
          <Route path="/players/:playerId" element={<PlayerPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Couldn't load player details.")).toBeInTheDocument());
  });

  it("deep link with no navigation state defaults to 'Back to Roster', navigating to the player's own team", async () => {
    renderAt("/players/8477492"); // no state -- e.g. a bookmarked/shared URL
    await waitFor(() => screen.getByText(/mackinnon/i));

    expect(screen.getByRole("button", { name: /back to roster/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /back to roster/i }));

    expect(screen.getByText("Roster page")).toBeInTheDocument();
  });

  it("navigating in from the leaderboard shows 'Back to Leaderboard' and returns there", async () => {
    renderAt("/players/8477492", { state: { from: "leaderboard" } });
    await waitFor(() => screen.getByText(/mackinnon/i));

    expect(screen.getByRole("button", { name: /back to leaderboard/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /back to leaderboard/i }));

    expect(screen.getByText("Leaderboard page")).toBeInTheDocument();
  });
});
