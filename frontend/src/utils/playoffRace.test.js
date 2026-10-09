import { buildSeries, clinchStatus, formatOdds, latestWithChange, raceGroups, seasonGames } from "./playoffRace.js";

const row = (team_abbrev, division, division_sequence, wildcard_sequence) => ({ team_abbrev, division, division_sequence, wildcard_sequence });

describe("raceGroups", () => {
  it("lays a conference out in the playoff format", () => {
    const rows = [
      row("BOS", "Atlantic", 4, 1), row("OTT", "Atlantic", 1, 0), row("TBL", "Atlantic", 2, 0), row("FLA", "Atlantic", 3, 0),
      row("NYR", "Metropolitan", 1, 0), row("CAR", "Metropolitan", 2, 0), row("WSH", "Metropolitan", 3, 0),
      row("PHI", "Metropolitan", 8, 4), row("TOR", "Atlantic", 5, 2), row("PIT", "Metropolitan", 5, 3),
    ];

    const groups = raceGroups(rows);

    expect(groups.divisions.map((d) => [d.name, d.teams.map((t) => t.team_abbrev)])).toEqual([
      ["Atlantic", ["OTT", "TBL", "FLA"]],
      ["Metropolitan", ["NYR", "CAR", "WSH"]],
    ]);
    expect(groups.wildcards.map((t) => t.team_abbrev)).toEqual(["BOS", "TOR"]);
    expect(groups.chasing.map((t) => t.team_abbrev)).toEqual(["PIT", "PHI"]);
  });
});

describe("clinchStatus", () => {
  it("maps NHL clinch codes to badges", () => {
    expect(clinchStatus("x")).toMatchObject({ label: "Clinched", tone: "in" });
    expect(clinchStatus("e")).toMatchObject({ label: "Out", tone: "out" });
    expect(clinchStatus(null)).toBeNull();
    expect(clinchStatus("?")).toBeNull();
  });
});

describe("buildSeries", () => {
  it("gives each team one value per date, null where it has no snapshot", () => {
    const points = [
      { as_of_date: "2026-10-09", team_abbrev: "PIT", playoff_pct: 0.5 },
      { as_of_date: "2026-10-08", team_abbrev: "PIT", playoff_pct: "0.4" },
      { as_of_date: "2026-10-09", team_abbrev: "BOS", playoff_pct: 0.6 },
      { as_of_date: "2026-10-09", team_abbrev: "COL", playoff_pct: 0.9 }, // other conference
    ];

    expect(buildSeries(points, ["PIT", "BOS"])).toEqual({
      dates: ["2026-10-08", "2026-10-09"],
      series: [
        { team: "PIT", values: [0.4, 0.5] },
        { team: "BOS", values: [null, 0.6] },
      ],
    });
  });
});

describe("latestWithChange", () => {
  it("compares the latest odds with the last snapshot at least a week earlier", () => {
    const points = [
      { as_of_date: "2026-11-01", team_abbrev: "PIT", playoff_pct: 0.3 },
      { as_of_date: "2026-11-03", team_abbrev: "PIT", playoff_pct: 0.35 },
      { as_of_date: "2026-11-07", team_abbrev: "PIT", playoff_pct: 0.4 },
      { as_of_date: "2026-11-10", team_abbrev: "PIT", playoff_pct: 0.5 },
    ];

    const { PIT } = latestWithChange(points);

    expect(PIT.pct).toBe(0.5);
    expect(PIT.change).toBeCloseTo(0.15); // vs Nov 3, the last snapshot on or before Nov 3
  });

  it("has no change until there's a week of history", () => {
    const points = [
      { as_of_date: "2026-10-08", team_abbrev: "PIT", playoff_pct: 0.4 },
      { as_of_date: "2026-10-09", team_abbrev: "PIT", playoff_pct: 0.45 },
    ];

    expect(latestWithChange(points).PIT).toEqual({ pct: 0.45, change: null });
  });
});

describe("formatOdds", () => {
  it("never rounds a live chance to a flat 0% or 100%", () => {
    expect(formatOdds(0.004)).toBe("<1%");
    expect(formatOdds(0.996)).toBe(">99%");
    expect(formatOdds(1)).toBe("100%");
    expect(formatOdds(0.426)).toBe("43%");
    expect(formatOdds(null)).toBe("—");
  });
});

describe("seasonGames", () => {
  it("is 84 games from 2026-27 on", () => {
    expect(seasonGames(20252026)).toBe(82);
    expect(seasonGames(20262027)).toBe(84);
  });
});
