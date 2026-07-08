import React, { useState, useEffect, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

// Points at the live FastAPI backend deployed on Azure Container Apps.
// For local development against `uvicorn api:app --reload`, swap this
// back to "http://127.0.0.1:8000".
const API_BASE = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io";

const DIVISION_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"];

function StreakBadge({ code, count }) {
  if (!code) return <span className="streak streak-none">—</span>;
  const cls = code === "W" ? "streak streak-w" : code === "L" ? "streak streak-l" : "streak streak-ot";
  return <span className={cls}>{code}{count}</span>;
}

function TopNav({ search, onSearchChange }) {
  return (
    <div className="topnav">
      <div className="brand">
        <span className="brand-dot" />
        <span className="brand-name">NHL Standings</span>
      </div>
      <div className="nav-tabs">
        <button className="nav-tab nav-tab-active">Standings</button>
        <button className="nav-tab nav-tab-disabled" disabled>
          Player Stats <span className="soon-badge">SOON</span>
        </button>
      </div>
      <div className="nav-right">
        <input
          className="search-input"
          placeholder="Find a team..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <span className="live-badge">
          <span className="live-dot" /> LIVE
        </span>
      </div>
    </div>
  );
}

function DivisionTabs({ divisions, active, onSelect, disabled }) {
  return (
    <div className={disabled ? "division-tabs division-tabs-disabled" : "division-tabs"}>
      {divisions.map((div) => (
        <button
          key={div}
          className={div === active ? "division-tab division-tab-active" : "division-tab"}
          onClick={() => onSelect(div)}
          disabled={disabled}
        >
          {div.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function StandingsTable({ rows, selectedTeam, onSelectTeam }) {
  return (
    <div className="table-card">
      <table className="standings-table">
        <thead>
          <tr>
            <th className="col-rank"></th>
            <th className="col-team">TEAM</th>
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
          {rows.length === 0 && (
            <tr>
              <td colSpan={11} className="no-results">No teams match your search.</td>
            </tr>
          )}
          {rows
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
  );
}

function TrendChart({ history, teamAbbrev }) {
  const data = history.map((h) => ({
    date: h.snapshot_date,
    points: h.points,
  }));

  return (
    <div className="trend-panel">
      <div className="trend-header">
        <span className="trend-eyebrow">SEASON TREND</span>
        <span className="trend-team">{teamAbbrev}</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 11 }} />
          <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: "#12151c",
              border: "1px solid #1f2937",
              borderRadius: 6,
              fontSize: 12,
            }}
            labelStyle={{ color: "#e5e7eb" }}
          />
          <Line type="monotone" dataKey="points" stroke="#3b82f6" strokeWidth={2.5} dot={false} />
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
  const [activeDivision, setActiveDivision] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/standings/latest`)
      .then((res) => res.json())
      .then((data) => {
        setStandings(data);
        setStatus("ready");
        const firstDivision = data.find((d) => d.division)?.division;
        if (firstDivision) setActiveDivision(firstDivision);
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

  const divisions = useMemo(() => {
    const set = new Set(standings.map((r) => r.division).filter(Boolean));
    return Array.from(set).sort(
      (a, b) => DIVISION_ORDER.indexOf(a) - DIVISION_ORDER.indexOf(b)
    );
  }, [standings]);

  const isSearching = search.trim().length > 0;

  const visibleRows = useMemo(() => {
    let rows = standings;
    if (isSearching) {
      const q = search.trim().toLowerCase();
      rows = rows.filter(
        (r) =>
          r.team_name.toLowerCase().includes(q) ||
          r.team_abbrev.toLowerCase().includes(q)
      );
    } else if (activeDivision) {
      rows = rows.filter((r) => r.division === activeDivision);
    }
    return rows;
  }, [standings, activeDivision, search, isSearching]);

  return (
    <div className="dashboard">
      <style>{`
        .dashboard {
          --accent: #3b82f6;
          --bg: #0a0b0f;
          --card: #12141a;
          --border: #1f2430;
          --text: #e5e7eb;
          --text-dim: #8b93a3;
          background: var(--bg);
          color: var(--text);
          font-family: 'Inter', system-ui, sans-serif;
          min-height: 100%;
          padding: 0 0 32px 0;
        }
        .topnav {
          display: flex;
          align-items: center;
          gap: 24px;
          padding: 16px 24px;
          border-bottom: 1px solid var(--border);
          margin-bottom: 20px;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .brand-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--accent);
        }
        .brand-name {
          font-weight: 700;
          font-size: 15px;
          color: var(--text);
        }
        .nav-tabs {
          display: flex;
          gap: 4px;
          flex: 1;
        }
        .nav-tab {
          background: none;
          border: none;
          color: var(--text-dim);
          font-size: 14px;
          font-weight: 500;
          padding: 8px 4px;
          cursor: pointer;
          border-bottom: 2px solid transparent;
        }
        .nav-tab-active {
          color: var(--text);
          border-bottom: 2px solid var(--accent);
        }
        .nav-tab-disabled {
          cursor: default;
          opacity: 0.6;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .soon-badge {
          font-size: 9px;
          background: #2a2f3a;
          color: var(--text-dim);
          padding: 2px 6px;
          border-radius: 3px;
          letter-spacing: 0.05em;
        }
        .nav-right {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        .search-input {
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 7px 12px;
          color: var(--text);
          font-size: 13px;
          width: 200px;
        }
        .search-input::placeholder { color: var(--text-dim); }
        .live-badge {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          font-weight: 700;
          color: #22c55e;
          background: rgba(34, 197, 94, 0.1);
          padding: 5px 10px;
          border-radius: 12px;
          letter-spacing: 0.05em;
        }
        .live-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #22c55e;
        }
        .division-tabs {
          display: flex;
          gap: 8px;
          padding: 0 24px;
          margin-bottom: 16px;
        }
        .division-tab {
          background: var(--card);
          border: 1px solid var(--border);
          color: var(--text-dim);
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.05em;
          padding: 6px 14px;
          border-radius: 6px;
          cursor: pointer;
        }
        .division-tab-active {
          color: var(--accent);
          border-color: var(--accent);
          background: rgba(59, 130, 246, 0.1);
        }
        .division-tabs-disabled .division-tab {
          opacity: 0.4;
          cursor: not-allowed;
        }
        .no-results {
          text-align: center;
          color: var(--text-dim);
          padding: 24px 14px;
        }
        .table-card {
          margin: 0 24px;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          overflow: hidden;
        }
        .standings-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }
        .standings-table thead th {
          text-align: right;
          font-weight: 500;
          color: var(--text-dim);
          font-size: 11px;
          letter-spacing: 0.05em;
          padding: 12px 14px;
          border-bottom: 1px solid var(--border);
        }
        .standings-table th.col-team, .standings-table td.col-team { text-align: left; }
        .standings-table td {
          text-align: right;
          padding: 10px 14px;
          border-bottom: 1px solid var(--border);
        }
        .standings-table tbody tr:last-child td { border-bottom: none; }
        .standings-table tbody tr {
          cursor: pointer;
          transition: background 0.12s ease;
        }
        .standings-table tbody tr:hover { background: #171a22; }
        .row-selected { background: #161d2e !important; }
        .row-selected .team-abbrev { color: var(--accent); }
        .col-rank { color: var(--text-dim); width: 28px; }
        .col-pts { font-weight: 700; color: var(--accent); }
        .team-abbrev {
          font-weight: 700;
          margin-right: 10px;
        }
        .team-name {
          color: var(--text-dim);
          font-size: 12px;
        }
        .diff-pos { color: #22c55e; }
        .diff-neg { color: #ef4444; }
        .streak {
          font-size: 11px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 4px;
        }
        .streak-w { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
        .streak-l { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
        .streak-ot { background: rgba(234, 179, 8, 0.15); color: #eab308; }
        .streak-none { color: var(--text-dim); }
        .trend-panel {
          margin: 24px 24px 0 24px;
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 20px;
        }
        .trend-header {
          display: flex;
          align-items: baseline;
          gap: 12px;
          margin-bottom: 8px;
        }
        .trend-eyebrow {
          font-size: 11px;
          letter-spacing: 0.1em;
          color: var(--text-dim);
        }
        .trend-team {
          font-weight: 700;
          font-size: 18px;
          color: var(--accent);
        }
        .status-line {
          font-size: 13px;
          color: var(--text-dim);
          padding: 0 24px;
        }
        .status-error { color: #ef4444; }
      `}</style>

      <TopNav search={search} onSearchChange={setSearch} />

      {status === "loading" && <div className="status-line">Loading standings…</div>}
      {status === "error" && (
        <div className="status-line status-error">
          Couldn't reach the API at {API_BASE}.
        </div>
      )}

      {status === "ready" && (
        <>
          <DivisionTabs
            divisions={divisions}
            active={activeDivision}
            onSelect={setActiveDivision}
            disabled={isSearching}
          />
          <StandingsTable
            rows={visibleRows}
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