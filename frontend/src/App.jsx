import React, { useState, useEffect, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

// Point this at your running FastAPI backend.
// Default assumes `uvicorn api:app --reload` running locally.
const API_BASE = "http://127.0.0.1:8000";

const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];

function StreakBadge({ code, count }) {
  if (!code) return <span className="streak streak-none">—</span>;
  const cls = code === "W" ? "streak streak-w" : code === "L" ? "streak streak-l" : "streak streak-ot";
  return <span className={cls}>{code}{count}</span>;
}

function StandingsTable({ rows, selectedTeam, onSelectTeam }) {
  const byDivision = useMemo(() => {
    const groups = {};
    rows.forEach((r) => {
      const d = r.division || "League";
      if (!groups[d]) groups[d] = [];
      groups[d].push(r);
    });
    return groups;
  }, [rows]);

  const divisions = Object.keys(byDivision).sort(
    (a, b) => DIVISION_ORDER.indexOf(a) - DIVISION_ORDER.indexOf(b)
  );

  return (
    <div className="standings-wrap">
      {divisions.map((div) => (
        <div key={div} className="division-block">
          <div className="division-label">{div}</div>
          <table className="standings-table">
            <thead>
              <tr>
                <th className="col-rank">#</th>
                <th className="col-team">Team</th>
                <th>GP</th>
                <th>W</th>
                <th>L</th>
                <th>OT</th>
                <th className="col-pts">PTS</th>
                <th>GF</th>
                <th>GA</th>
                <th>DIFF</th>
                <th>L10</th>
                <th>STRK</th>
              </tr>
            </thead>
            <tbody>
              {byDivision[div]
                .sort((a, b) => a.division_sequence - b.division_sequence)
                .map((row) => (
                  <tr
                    key={row.team_abbrev}
                    className={row.team_abbrev === selectedTeam ? "row-selected" : ""}
                    onClick={() => onSelectTeam(row.team_abbrev)}
                  >
                    <td className="col-rank">{row.division_sequence}</td>
                    <td className="col-team">
                      <span className="team-abbrev">{row.team_abbrev}</span>
                      <span className="team-name">{row.team_name}</span>
                    </td>
                    <td>{row.games_played}</td>
                    <td>{row.wins}</td>
                    <td>{row.losses}</td>
                    <td>{row.ot_losses}</td>
                    <td className="col-pts">{row.points}</td>
                    <td>{row.goal_for}</td>
                    <td>{row.goal_against}</td>
                    <td className={row.goal_differential >= 0 ? "diff-pos" : "diff-neg"}>
                      {row.goal_differential > 0 ? "+" : ""}{row.goal_differential}
                    </td>
                    <td>{row.l10_wins}-{row.l10_losses}-{row.l10_ot_losses}</td>
                    <td><StreakBadge code={row.streak_code} count={row.streak_count} /></td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function TrendChart({ history, teamAbbrev }) {
  const data = history.map((h) => ({
    date: h.snapshot_date,
    points: h.points,
    goalDiff: h.goal_differential,
  }));

  return (
    <div className="trend-panel">
      <div className="trend-header">
        <span className="trend-eyebrow">SEASON TREND</span>
        <span className="trend-team">{teamAbbrev}</span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
          <CartesianGrid stroke="#2a3142" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" stroke="#6b7690" tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }} />
          <YAxis stroke="#6b7690" tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }} />
          <Tooltip
            contentStyle={{
              background: "#12151f",
              border: "1px solid #2a3142",
              borderRadius: 4,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
            }}
            labelStyle={{ color: "#e8ecf1" }}
          />
          <Line type="monotone" dataKey="points" stroke="#e2231a" strokeWidth={2.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function NHLDashboard() {
  const [standings, setStandings] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState("PIT");
  const [status, setStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    fetch(`${API_BASE}/standings/latest`)
      .then((res) => res.json())
      .then((data) => {
        setStandings(data);
        setStatus("ready");
      })
      .catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    if (!selectedTeam) return;
    fetch(`${API_BASE}/standings/${selectedTeam}`)
      .then((res) => res.json())
      .then((data) => setHistory(Array.isArray(data) ? data : []))
      .catch(() => setHistory([]));
  }, [selectedTeam]);

  return (
    <div className="dashboard">
      <style>{`
        .dashboard {
          --font-display: 'Oswald', 'Arial Narrow', sans-serif;
          --font-mono: 'JetBrains Mono', 'Courier New', monospace;
          --font-body: 'Inter', system-ui, sans-serif;
          background: #0c0e14;
          color: #e8ecf1;
          font-family: var(--font-body);
          padding: 32px 24px;
          min-height: 100%;
        }
        .header {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          border-bottom: 3px solid #e2231a;
          padding-bottom: 16px;
          margin-bottom: 24px;
        }
        .header h1 {
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 32px;
          letter-spacing: 0.02em;
          text-transform: uppercase;
          margin: 0;
        }
        .header .subtitle {
          font-family: var(--font-mono);
          font-size: 12px;
          color: #6b7690;
          letter-spacing: 0.08em;
        }
        .status-line {
          font-family: var(--font-mono);
          font-size: 13px;
          color: #6b7690;
          margin-bottom: 16px;
        }
        .status-error {
          color: #e2231a;
        }
        .division-block { margin-bottom: 28px; }
        .division-label {
          font-family: var(--font-display);
          font-size: 13px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: #8a93ab;
          margin-bottom: 8px;
          padding-left: 4px;
        }
        .standings-table {
          width: 100%;
          border-collapse: collapse;
          font-family: var(--font-mono);
          font-size: 13px;
        }
        .standings-table thead th {
          text-align: right;
          font-weight: 400;
          color: #6b7690;
          font-size: 11px;
          letter-spacing: 0.05em;
          padding: 6px 10px;
          border-bottom: 1px solid #2a3142;
        }
        .standings-table th.col-team, .standings-table td.col-team { text-align: left; }
        .standings-table td {
          text-align: right;
          padding: 8px 10px;
          border-bottom: 1px solid #1a1f2e;
        }
        .standings-table tbody tr {
          cursor: pointer;
          transition: background 0.12s ease;
        }
        .standings-table tbody tr:hover { background: #12151f; }
        .row-selected { background: #1a1420 !important; }
        .row-selected .team-abbrev { color: #e2231a; }
        .col-rank { color: #6b7690; width: 28px; }
        .col-pts { font-weight: 700; color: #e8ecf1; }
        .team-abbrev {
          font-family: var(--font-display);
          font-weight: 700;
          margin-right: 10px;
        }
        .team-name {
          color: #8a93ab;
          font-family: var(--font-body);
          font-size: 12px;
        }
        .diff-pos { color: #3fb950; }
        .diff-neg { color: #e2231a; }
        .streak {
          font-family: var(--font-mono);
          font-size: 11px;
          font-weight: 700;
          padding: 2px 6px;
          border-radius: 2px;
        }
        .streak-w { background: #143d24; color: #3fb950; }
        .streak-l { background: #3d1414; color: #e2231a; }
        .streak-ot { background: #3d3414; color: #e8b93f; }
        .streak-none { color: #6b7690; }
        .trend-panel {
          margin-top: 32px;
          background: #12151f;
          border: 1px solid #2a3142;
          border-radius: 6px;
          padding: 20px;
        }
        .trend-header {
          display: flex;
          align-items: baseline;
          gap: 12px;
          margin-bottom: 8px;
        }
        .trend-eyebrow {
          font-family: var(--font-mono);
          font-size: 11px;
          letter-spacing: 0.1em;
          color: #6b7690;
        }
        .trend-team {
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 20px;
          color: #e2231a;
        }
      `}</style>

      <div className="header">
        <h1>NHL Standings</h1>
        <span className="subtitle">LIVE FROM NEON POSTGRES</span>
      </div>

      {status === "loading" && <div className="status-line">Loading standings…</div>}
      {status === "error" && (
        <div className="status-line status-error">
          Couldn't reach the API at {API_BASE}. Make sure `uvicorn api:app --reload` is running.
        </div>
      )}

      {status === "ready" && (
        <>
          <StandingsTable
            rows={standings}
            selectedTeam={selectedTeam}
            onSelectTeam={setSelectedTeam}
          />
          {history.length > 0 && (
            <TrendChart history={history} teamAbbrev={selectedTeam} />
          )}
        </>
      )}
    </div>
  );
}
