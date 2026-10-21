import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { useFavoriteTeam } from "../hooks/useFavoriteTeam.js";
import { teamLogo } from "../utils/teamLogo.js";

// Lottery odds are quoted to a decimal: 0.255 -> "25.5%"; tiny chances "<0.1%", none "—".
const pct = (p) => (p >= 0.9995 ? "100%" : p >= 0.0005 ? `${(p * 100).toFixed(1)}%` : p > 0 ? "<0.1%" : "—");
const top3 = (picks) => picks[0] + picks[1] + picks[2];
const likeliest = (picks) => picks.indexOf(Math.max(...picks)) + 1;

// The draft a season's lottery is for: 2026-27 is the 2027 draft.
function draftYear(date) {
  const d = date ? new Date(`${date}T12:00:00`) : new Date();
  return d.getMonth() >= 6 ? d.getFullYear() + 1 : d.getFullYear();
}

function Team({ abbrev, teams }) {
  const team = teams[abbrev];
  return (
    <span className="team-cell">
      {team?.logo_url && <img className="team-cell-logo" src={teamLogo(team.logo_url)} alt="" />}
      <span className="team-abbrev">{abbrev}</span>
    </span>
  );
}

const shortDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
const LOTTERY_PICKS = 16;

// The first round, each team taking the best player left on the consensus
// board. The lottery picks show; the playoff teams' picks open on a tap.
function MockDraft({ mock, picks, teams, rowClass }) {
  const [showAll, setShowAll] = useState(false);
  if (!picks?.length) return null;
  const shown = showAll ? picks : picks.slice(0, LOTTERY_PICKS);
  const sources = mock.sources;
  return (
    <section className="pickem-card lottery-mock">
      <h2 className="lottery-mock-title">Mock draft</h2>
      <ol className="lottery-mock-list">
        {shown.map(({ pick, team, prospect }) => (
          <li key={pick} className={rowClass(team)}>
            <span className="lottery-rank">{pick}</span>
            <Team abbrev={team} teams={teams} />
            <span className="lottery-mock-player" title={sources.map((s) => `${s.name}: ${prospect.ranks[s.name] ?? "unranked"}`).join(" · ")}>
              {prospect.ep ? (
                <a className="lottery-mock-link" href={`https://www.eliteprospects.com/player/${prospect.ep}`} target="_blank" rel="noopener noreferrer">
                  {prospect.name}
                </a>
              ) : <strong>{prospect.name}</strong>}
              <span className="lottery-mock-meta">
                {prospect.pos} · {prospect.team}{prospect.league ? ` (${prospect.league})` : ""}
              </span>
            </span>
          </li>
        ))}
      </ol>
      {picks.length > LOTTERY_PICKS && (
        <button type="button" className="link-button lottery-mock-more" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show the lottery picks only" : `Show picks ${LOTTERY_PICKS + 1}-${picks.length}`}
        </button>
      )}
      <p className="pickem-hint">
        Each team takes the best player left on PuckPulse&apos;s board: the average of{" "}
        {sources.map((s, i) => (
          <span key={s.name}>
            {i > 0 && (i === sources.length - 1 ? " and " : ", ")}
            <a className="accent-link" href={s.url} target="_blank" rel="noreferrer">{s.name}</a> ({shortDate(s.as_of)})
          </span>
        ))}
        {" "}rankings. No lottery jumps; picks {LOTTERY_PICKS + 1}-{picks.length} go by record, though really they go by playoff results.
        {" "}Tap a prospect for his profile and stats on{" "}
        <a className="accent-link" href="https://www.eliteprospects.com" target="_blank" rel="noopener noreferrer">EliteProspects</a>.
      </p>
    </section>
  );
}

export default function DraftLotteryPage({ standings = [] }) {
  const { data, status } = useFetchWithStatus(`${API_BASE}/draft-lottery`);
  const [view, setView] = useState("projected");
  const [favorite] = useFavoriteTeam();
  const teams = useMemo(() => Object.fromEntries(standings.map((t) => [t.team_abbrev, t])), [standings]);
  const projected = (data?.projected || []).filter((t) => t.missed_playoffs >= 0.05 || t.picks[0] >= 0.001);
  const today = data?.today || [];
  const rowClass = (abbrev) => (abbrev === favorite ? "lottery-row-favorite" : undefined);

  return (
    <main className="page lottery-page">
      <div className="page-header"><h1>Draft lottery</h1></div>
      <p className="page-subtitle">
        Each team&apos;s chance at the No. 1 pick in the {draftYear(data?.as_of)} NHL Draft.{" "}
        <Link className="accent-link" to="/playoffs">Playoff race ›</Link>
      </p>
      <div className="preview-lines-toggle" role="group" aria-label="View">
        {[["projected", "Projected"], ["today", "If the season ended today"]].map(([key, label]) => (
          <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>
        ))}
      </div>

      {status === "error" ? (
        <p className="bets-note">Couldn&apos;t load the lottery odds.</p>
      ) : !data ? (
        <p className="bets-note">Loading…</p>
      ) : view === "projected" ? (
        projected.length === 0 ? (
          <p className="bets-note">The projection appears after the next daily run.</p>
        ) : (
          <section className="pickem-card">
            <table className="rc-table lottery-table">
              <thead><tr><th scope="col">Team</th><th scope="col">No. 1 pick</th><th scope="col">Top 3</th><th scope="col">In the lottery</th></tr></thead>
              <tbody>
                {projected.map((t) => (
                  <tr key={t.team} className={rowClass(t.team)}>
                    <th scope="row"><Team abbrev={t.team} teams={teams} /></th>
                    <td><strong>{pct(t.picks[0])}</strong></td>
                    <td>{pct(top3(t.picks))}</td>
                    <td className="muted">{pct(t.missed_playoffs)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="pickem-hint">
              From 10,000 simulations of the rest of the season: where each team might finish, then the lottery&apos;s odds
              for that finish. &quot;In the lottery&quot; is the chance of missing the playoffs.
            </p>
          </section>
        )
      ) : today.length === 0 ? (
        <p className="bets-note">Today&apos;s standings aren&apos;t in yet.</p>
      ) : (
        <section className="pickem-card">
          <table className="rc-table lottery-table">
            <thead><tr><th scope="col">Team</th><th scope="col">Pts</th><th scope="col">No. 1 pick</th><th scope="col">Top 3</th><th scope="col">Likeliest pick</th></tr></thead>
            <tbody>
              {today.map((t) => (
                <tr key={t.team} className={rowClass(t.team)}>
                  <th scope="row"><span className="lottery-teamcell"><span className="lottery-rank">{t.position}</span><Team abbrev={t.team} teams={teams} /></span></th>
                  <td className="muted">{t.points}<span className="lottery-gp">{t.games_played} GP</span></td>
                  <td><strong>{pct(t.picks[0])}</strong></td>
                  <td>{pct(top3(t.picks))}</td>
                  <td>{likeliest(t.picks)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="pickem-hint">The 16 teams out of a playoff spot today, worst first, with the lottery&apos;s exact odds.</p>
        </section>
      )}

      {data?.mock && <MockDraft key={view} mock={data.mock} picks={data.mock[view]} teams={teams} rowClass={rowClass} />}

      <section className="bets-about">
        <h2>How the lottery works</h2>
        <ul>
          <li><strong>Who&apos;s in</strong>: the 16 teams that miss the playoffs, holding 1,000 combinations between them; the worst team has 185, the 16th 5.</li>
          <li><strong>Two draws</strong> decide the first two picks; everyone else picks in reverse order of the standings.</li>
          <li><strong>No team moves up more than 10 spots</strong>, so only the 11 worst teams can win No. 1. If a 12th-16th team wins the first draw, it moves up 10 and the worst team keeps No. 1. That&apos;s why last place has a 25.5% chance, more than its 18.5% of the combinations, and can&apos;t fall below 3rd.</li>
          <li>Not modeled: a team can win the lottery at most twice in five years.</li>
        </ul>
      </section>
    </main>
  );
}
