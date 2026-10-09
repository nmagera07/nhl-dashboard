import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import ScoresPage from "./ScoresPage.jsx";
import { shiftDate, todayISO } from "../utils/dates.js";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderAt(path, props = {}) {
  globalThis.fetch = vi.fn().mockImplementation((url) =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve(url.includes("/schedule") ? { live: null, recent: [], upcoming: [] } : { games: [] }),
    })
  );
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<><ScoresPage {...props} /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>
  );
}

const fetchedUrl = () => globalThis.fetch.mock.calls.at(-1)[0];

describe("ScoresPage", () => {
  it("shows today's games by default", async () => {
    renderAt("/");

    expect(screen.getByText("Today")).toBeInTheDocument();
    await waitFor(() => expect(fetchedUrl()).toMatch(new RegExp(`/games/date/${todayISO()}$`)));
    expect(screen.queryByRole("button", { name: "Today" })).not.toBeInTheDocument();
  });

  it("steps to the previous day and loads that day's games", async () => {
    renderAt("/");

    await userEvent.click(screen.getByRole("button", { name: "Previous day" }));

    const yesterday = shiftDate(todayISO(), -1);
    expect(screen.getByTestId("location")).toHaveTextContent(`/?date=${yesterday}`);
    expect(screen.getByText("Yesterday")).toBeInTheDocument();
    await waitFor(() => expect(fetchedUrl()).toMatch(new RegExp(`/games/date/${yesterday}$`)));
    expect(await screen.findByText("No games on this day.")).toBeInTheDocument();
  });

  it("reads the day from the URL and jumps back to today", async () => {
    renderAt("/?date=2026-10-06");

    await waitFor(() => expect(fetchedUrl()).toMatch(/\/games\/date\/2026-10-06$/));
    await userEvent.click(screen.getByRole("button", { name: "Today" }));

    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
  });

  it("falls back to today for an invalid date in the URL", async () => {
    renderAt("/?date=not-a-date");

    await waitFor(() => expect(fetchedUrl()).toMatch(new RegExp(`/games/date/${todayISO()}$`)));
  });

  describe("my team", () => {
    const standings = [
      { team_abbrev: "PIT", team_name: "Pittsburgh Penguins", division: "Metropolitan", wins: 2, losses: 2, ot_losses: 0, points: 4, division_sequence: 5 },
      { team_abbrev: "BOS", team_name: "Boston Bruins", division: "Atlantic", wins: 3, losses: 1, ot_losses: 0, points: 6, division_sequence: 4 },
    ];
    afterEach(() => window.localStorage.clear());

    it("invites you to pick a team, then pins its card", async () => {
      renderAt("/", { standings, playoffOddsByTeam: { PIT: 0.57 } });

      await userEvent.selectOptions(screen.getByRole("combobox", { name: /follow a team/i }), "PIT");

      expect(screen.getByRole("region", { name: "My team: Pittsburgh Penguins" })).toBeInTheDocument();
      expect(screen.getByText("57%")).toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: /follow a team/i })).not.toBeInTheDocument();
    });

    it("shows the remembered team straight away", () => {
      window.localStorage.setItem("nhl-dash:favorite-team", "BOS");

      renderAt("/", { standings });

      expect(screen.getByRole("region", { name: "My team: Boston Bruins" })).toBeInTheDocument();
    });
  });
});
