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

// The latest scoreboard request (headlines and other cards fetch too).
const fetchedUrl = () => globalThis.fetch.mock.calls.map(([url]) => String(url)).filter((u) => u.includes("/games/date/")).at(-1);

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

  it("an unfollow from the card can be undone, even the last team, main team first again", async () => {
    const row = (team_abbrev, team_name) => ({
      team_abbrev, team_name, division: "Metropolitan", logo_url: null, wins: 2, losses: 2, ot_losses: 0, points: 4,
      division_sequence: 5, streak_code: "L", streak_count: 2,
    });
    window.localStorage.setItem("nhl-dash:followed-teams", JSON.stringify(["PIT", "BOS"]));
    renderAt("/", { standings: [row("PIT", "Pittsburgh Penguins"), row("BOS", "Boston Bruins")] });

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop following PIT" }));
    expect(JSON.parse(window.localStorage.getItem("nhl-dash:followed-teams"))).toEqual(["BOS"]);
    expect(screen.getByRole("status")).toHaveTextContent("Stopped following PIT · Undo");

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(JSON.parse(window.localStorage.getItem("nhl-dash:followed-teams"))).toEqual(["PIT", "BOS"]);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    window.localStorage.setItem("nhl-dash:followed-teams", JSON.stringify(["PIT"]));
    window.dispatchEvent(new Event("storage"));
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop following PIT" }));
    expect(screen.queryByRole("region", { name: /My team/ })).not.toBeInTheDocument(); // the card is gone...
    await userEvent.click(screen.getByRole("button", { name: "Undo" })); // ...but the undo isn't
    expect(JSON.parse(window.localStorage.getItem("nhl-dash:followed-teams"))).toEqual(["PIT"]);
    window.localStorage.clear();
  });
});
