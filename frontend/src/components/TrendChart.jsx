import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList,
} from "recharts";
import { formatSeasonLabel } from "../utils/formatSeasonLabel.js";

function YearlyDot({ cx, cy, payload }) {
  const fill = payload?.madePlayoffs ? "#3b82f6" : "#4b5563";
  return <circle cx={cx} cy={cy} r={5} fill={fill} stroke="#0a0b0f" strokeWidth={2} />;
}

function YearlyPointLabel({ x, y, value }) {
  return (
    <text x={x} y={y - 14} textAnchor="middle" fill="#e5e7eb" fontSize={12} fontWeight={700}>
      {value}
    </text>
  );
}

const chartTooltipStyle = {
  contentStyle: {
    background: "#12151c",
    border: "1px solid #1f2937",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "#e5e7eb" },
};

function TrendChart({ mode, onModeChange, history, seasonHistory, teamAbbrev }) {
  const dailyData = history.map((h) => ({
    date: h.snapshot_date,
    points: h.points,
  }));

  const yearlyData = seasonHistory.map((s) => ({
    season: formatSeasonLabel(s.season_id),
    points: s.points,
    madePlayoffs: s.made_playoffs,
  }));

  return (
    <div className="trend-panel">
      <div className="trend-header">
        <span className="trend-eyebrow">{mode === "years" ? "LAST 5 YEARS" : "SEASON TREND"}</span>
        <span className="trend-team">{teamAbbrev}</span>
        <div className="trend-toggle">
          <button
            className={mode === "season" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
            onClick={() => onModeChange("season")}
          >
            This Season
          </button>
          <button
            className={mode === "years" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
            onClick={() => onModeChange("years")}
          >
            Last 5 Years
          </button>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        {mode === "years" ? (
          <AreaChart data={yearlyData} margin={{ top: 24, right: 20, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="yearlyFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="season" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
            <Tooltip {...chartTooltipStyle} />
            <Area
              type="monotone"
              dataKey="points"
              stroke="#3b82f6"
              strokeWidth={2.5}
              fill="url(#yearlyFill)"
              dot={<YearlyDot />}
              isAnimationActive={false}
            >
              <LabelList dataKey="points" content={<YearlyPointLabel />} />
            </Area>
          </AreaChart>
        ) : (
          <LineChart data={dailyData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 11 }} />
            <YAxis stroke="#6b7280" tick={{ fontSize: 11 }} />
            <Tooltip {...chartTooltipStyle} />
            <Line type="monotone" dataKey="points" stroke="#3b82f6" strokeWidth={2.5} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
      {mode === "years" && (
        <div className="years-legend">
          <span><span className="legend-dot legend-dot-playoff" /> Made playoffs</span>
          <span><span className="legend-dot legend-dot-missed" /> Missed playoffs</span>
        </div>
      )}
    </div>
  );
}

export default TrendChart;
