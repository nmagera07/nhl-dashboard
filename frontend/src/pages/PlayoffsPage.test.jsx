import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PlayoffsPage from "./PlayoffsPage.jsx";

const team = (team_abbrev, conference, division, division_sequence, wildcard_sequence, extra = {}) => ({
  team_abbrev, conference, division, division_sequence, wildcard_sequence,
  season_id: 20262027, games_played: 10, points: 12, logo_url: null, clinch_indicator: null, ...extra,
});

const STANDINGS = [
  team("OTT", "Eastern", "Atlantic", 1, 0), team("TBL", "Eastern", "Atlantic", 2, 0), team("FLA", "Eastern", "Atlantic", 3, 0),
  team("NYR", "Eastern", "Metropolitan", 1, 0, { clinch_indicator: "x" }), team("CAR", "Eastern", "Metropolitan", 2, 0), team("WSH", "Eastern", "Metropolitan", 3, 0),
  team("BOS", "Eastern", "Atlantic", 4, 1), team("TOR", "Eastern", "Atlantic", 5, 2),
  team("PIT", "Eastern", "Metropolitan", 5, 3), team("PHI", "Eastern", "Metropolitan", 8, 4, { clinch_indicator: "e" }),
  team("COL", "Western", "Central", 1, 0),
];

const pts = (date, values) => Object.entries(values).map(([team_abbrev, playoff_pct]) => ({ as_of_date: date, team_abbrev, playoff_pct }));

const CURRENT = {
  season_id: 20262027,
  available_seasons: [20262027, 20252026],
  points: [...pts("2026-11-01", { PIT: 0.3, BOS: 0.5, COL: 0.9 }), ...pts("2026-11-08", { PIT: 0.42, BOS: 0.47, COL: 0.95 })],
};
const LAST_SEASON = {
  season_id: 20252026,
  available_seasons: [20262027, 20252026],
  points: [...pts("2025-11-01", { PIT: 0.2 }), ...pts("2025-12-01", { PIT: 0.6 })],
};

function mockApi(current = CURRENT) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((url) =>
    Promise.resolve({ json: async () => (url.includes("season_id=20252026") ? LAST_SEASON : current) })
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PlayoffsPage standings={STANDINGS} />
    </MemoryRouter>
  );
}

const rowFor = (abbrev) => screen.getByRole("link", { name: abbrev }).closest("tr");

describe("PlayoffsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lays out the conference in the playoff format with odds and weekly change", async () => {
    mockApi();
    renderPage();

    expect(await screen.findByRole("img", { name: /playoff odds from nov 1 to nov 8/i })).toBeInTheDocument();
    const groups = screen.getAllByRole("columnheader").filter((h) => h.getAttribute("scope") === "colgroup").map((h) => h.textContent);
    expect(groups).toEqual(["Atlantic", "Metropolitan", "Wild card", "Chasing"]);
    expect(within(rowFor("PIT")).getByText("42%")).toBeInTheDocument();
    expect(within(rowFor("PIT")).getByText("▲ 12")).toBeInTheDocument();
    expect(within(rowFor("BOS")).getByText("▼ 3")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "COL" })).not.toBeInTheDocument(); // other conference
  });

  it("shows clinched and eliminated badges", async () => {
    mockApi();
    renderPage();

    expect(await within(rowFor("NYR")).findByTitle("Clinched a playoff spot")).toHaveTextContent("Clinched");
    expect(within(rowFor("PHI")).getByTitle("Eliminated from playoff contention")).toHaveTextContent("Out");
  });

  it("switches conference", async () => {
    mockApi();
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: "Western" }));

    expect(screen.getByRole("link", { name: "COL" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "PIT" })).not.toBeInTheDocument();
  });

  it("highlights a team's race when its row is picked", async () => {
    mockApi();
    renderPage();
    await screen.findByRole("img", { name: /playoff odds/i });

    await userEvent.click(rowFor("PIT"));

    expect(rowFor("PIT")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("PIT", { selector: ".odds-chart-readout strong" })).toBeInTheDocument();
  });

  it("offers last season's race while this season's chart is still empty", async () => {
    const fetchMock = mockApi({ ...CURRENT, points: pts("2026-10-08", { PIT: 0.4 }) });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /see last season's race/i }));

    expect(await screen.findByRole("img", { name: /playoff odds from nov 1 to dec 1/i })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/playoff-odds/history?season_id=20252026"));
    expect(screen.getByRole("button", { name: "25-26" })).toHaveAttribute("aria-pressed", "true");
  });

  it("doesn't show last season's odds as this season's", async () => {
    mockApi({ ...LAST_SEASON, season_id: 20252026 });
    renderPage();
    await screen.findByRole("img", { name: /playoff odds/i });

    expect(within(rowFor("PIT")).getByText("—", { selector: ".race-odds" })).toBeInTheDocument();
  });

  it("shows an error when the odds can't load", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("down"));
    renderPage();

    expect(await screen.findByText("Couldn't load playoff odds.")).toBeInTheDocument();
  });
});
