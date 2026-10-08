import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GameCalendar from "./GameCalendar.jsx";

const october = {
  season_start: "2026-10-07",
  season_end: "2027-06-10",
  days: [
    { date: "2026-10-07", games: 2 },
    { date: "2026-10-08", games: 10 },
    { date: "2026-10-10", games: 14 },
  ],
};
const november = { ...october, days: [{ date: "2026-11-02", games: 5 }] };

function renderCalendar(props = {}) {
  globalThis.fetch = vi.fn((url) => {
    const data = url.endsWith("/2026-11") ? november : october;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(data) });
  });
  const handlers = { onSelect: vi.fn(), onClose: vi.fn() };
  render(<GameCalendar value="2026-10-08" today="2026-10-08" {...handlers} {...props} />);
  return handlers;
}

const day = (name) => screen.findByRole("button", { name: new RegExp(`^${name}`) });

describe("GameCalendar", () => {
  it("opens on the selected day's month and loads its game days", async () => {
    renderCalendar();

    expect(screen.getByText(/October 2026/)).toBeInTheDocument();
    expect(await screen.findByText("Numbers show games that day.")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/games\/calendar\/2026-10$/));
  });

  it("only lets you pick days with games", async () => {
    renderCalendar();

    expect(await day("Saturday, October 10, 2026, 14 games")).toBeEnabled();
    expect(await day("Friday, October 9, 2026, no games")).toBeDisabled();
    expect(await day("Tuesday, October 6, 2026, no games")).toBeDisabled(); // before the season
  });

  it("selects a game day", async () => {
    const { onSelect } = renderCalendar();

    await userEvent.click(await day("Saturday, October 10, 2026"));

    expect(onSelect).toHaveBeenCalledWith("2026-10-10");
  });

  it("stops month navigation at the start of the season", async () => {
    renderCalendar();
    await screen.findByText("Numbers show games that day.");

    expect(screen.getByRole("button", { name: "Previous month" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next month" }));

    expect(screen.getByText(/November 2026/)).toBeInTheDocument();
    expect(await day("Monday, November 2, 2026, 5 games")).toBeEnabled();
  });

  it("closes on Escape", async () => {
    const { onClose } = renderCalendar();

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
  });
});
