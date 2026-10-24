import { render, screen, act } from "@testing-library/react";
import AllPlayerSearch from "./AllPlayerSearch.jsx";

const FOUND = { players: [
  { player_id: 8447400, name: "Wayne Gretzky", position_code: "C", active: false, last_team_abbrev: "NYR", last_season_id: 19981999 },
  { player_id: 8478402, name: "Connor McDavid", position_code: "C", active: true, last_team_abbrev: "EDM", last_season_id: 20262027 },
] };

describe("AllPlayerSearch", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it("after a pause, lists matches beyond current rosters, and opens one", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => FOUND });
    const onSelect = vi.fn();
    render(<AllPlayerSearch query="gret" exclude={new Set([8478402])} onSelectPlayer={onSelect} />);
    expect(fetchMock).not.toHaveBeenCalled();

    await act(() => vi.advanceTimersByTimeAsync(300));

    expect(fetchMock.mock.calls[0][0]).toMatch(/\/players\/search\?q=gret$/);
    expect(screen.getByText("C · Retired · last played 1998-99 (NYR)")).toBeInTheDocument();
    expect(screen.queryByText("Connor McDavid")).not.toBeInTheDocument(); // already in the list above
    screen.getByRole("button", { name: /Wayne Gretzky/ }).click();
    expect(onSelect).toHaveBeenCalledWith(8447400);
  });

  it("waits for three letters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    render(<AllPlayerSearch query="gr" exclude={new Set()} onSelectPlayer={vi.fn()} />);
    await act(() => vi.advanceTimersByTimeAsync(500));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
