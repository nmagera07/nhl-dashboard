import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import ScoresPage from "./ScoresPage.jsx";
import { shiftDate, todayISO } from "../utils/dates.js";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderAt(path) {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ games: [] }) });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<><ScoresPage /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>
  );
}

const fetchedUrl = () => globalThis.fetch.mock.calls.at(-1)[0];

describe("ScoresPage", () => {
  it("shows today's games by default", async () => {
    renderAt("/");

    expect(screen.getByText("Today")).toBeInTheDocument();
    await waitFor(() => expect(fetchedUrl()).toMatch(/\/games\/today$/));
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

    await waitFor(() => expect(fetchedUrl()).toMatch(/\/games\/today$/));
  });
});
