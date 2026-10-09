// Pure helpers for the Playoffs page: grouping standings into the playoff
// format, and reshaping the odds history into chart series.

// The NHL format: top 3 in each division, then 2 wild cards per conference.
// wildcard_sequence is 0 for division top-3 teams, 1..N for everyone else.
export function raceGroups(rows) {
  const divisions = {};
  const others = [];
  rows.forEach((row) => {
    if (row.wildcard_sequence === 0 && row.division_sequence <= 3) {
      (divisions[row.division] ||= []).push(row);
    } else {
      others.push(row);
    }
  });
  Object.values(divisions).forEach((teams) => teams.sort((a, b) => a.division_sequence - b.division_sequence));
  others.sort((a, b) => a.wildcard_sequence - b.wildcard_sequence);
  return {
    divisions: Object.entries(divisions)
      .map(([name, teams]) => ({ name, teams }))
      .sort((a, b) => a.name.localeCompare(b.name)),
    wildcards: others.slice(0, 2),
    chasing: others.slice(2),
  };
}

// Regular-season length: 82 games through 2025-26, 84 from 2026-27 (2025 CBA).
export function seasonGames(seasonId) {
  return seasonId >= 20262027 ? 84 : 82;
}

// NHL clinchIndicator codes -> a short badge and a full description.
const CLINCH = {
  p: { label: "Clinched", title: "Clinched the Presidents' Trophy", tone: "in" },
  z: { label: "Clinched", title: "Clinched the conference", tone: "in" },
  y: { label: "Clinched", title: "Clinched the division", tone: "in" },
  x: { label: "Clinched", title: "Clinched a playoff spot", tone: "in" },
  e: { label: "Out", title: "Eliminated from playoff contention", tone: "out" },
};
export function clinchStatus(code) {
  return code ? CLINCH[code.toLowerCase()] || null : null;
}

// History points -> { dates, series } for one set of teams. Each series has
// one value per date (null where that team has no snapshot).
export function buildSeries(points, teams) {
  const dates = [...new Set(points.map((p) => p.as_of_date))].sort();
  const index = new Map(dates.map((d, i) => [d, i]));
  const byTeam = new Map(teams.map((t) => [t, Array(dates.length).fill(null)]));
  points.forEach((p) => {
    const values = byTeam.get(p.team_abbrev);
    if (values) values[index.get(p.as_of_date)] = Number(p.playoff_pct);
  });
  return { dates, series: teams.map((team) => ({ team, values: byTeam.get(team) })) };
}

// Each team's latest odds and the change since about a week earlier (the
// latest snapshot at least 7 days before; null if there isn't one yet).
export function latestWithChange(points) {
  const byTeam = {};
  points.forEach((p) => (byTeam[p.team_abbrev] ||= []).push(p));
  const out = {};
  Object.entries(byTeam).forEach(([team, list]) => {
    list.sort((a, b) => a.as_of_date.localeCompare(b.as_of_date));
    const latest = list[list.length - 1];
    const cutoff = daysBefore(latest.as_of_date, 7);
    const earlier = [...list].reverse().find((p) => p.as_of_date <= cutoff);
    out[team] = {
      pct: Number(latest.playoff_pct),
      change: earlier ? Number(latest.playoff_pct) - Number(earlier.playoff_pct) : null,
    };
  });
  return out;
}

function daysBefore(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

// Same rounding rules as the standings PO% column: never a flat 0%/100%
// unless it's truly settled.
export function formatOdds(pct) {
  if (pct == null) return "—";
  const value = Number(pct) * 100;
  if (value > 0 && value < 1) return "<1%";
  if (value > 99 && value < 100) return ">99%";
  return `${value.toFixed(0)}%`;
}
