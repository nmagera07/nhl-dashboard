import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";
import { winProbability } from "../utils/seasonSim.js";
import { todayISO } from "../utils/dates.js";
import { teamLogo } from "../utils/teamLogo.js";
import { track } from "../utils/analytics.js";
import { fetchMe, joinPickem, makePick, record, saveKey, savedKey } from "../utils/pickem.js";

const NOT_STARTED = new Set(["FUT", "PRE"]);
const startTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

function JoinForm({ onJoined }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const join = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { key } = await joinPickem(name);
      track("pickem-join");
      onJoined(key);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const restore = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await fetchMe(code.trim());
      onJoined(code.trim());
    } catch (err) {
      setError(err.status === 401 ? "That code didn't match a player." : err.message);
    }
  };

  return (
    <section className="pickem-card">
      <form className="pickem-join" onSubmit={join}>
        <label htmlFor="pickem-name">Pick a display name to play</label>
        <div className="pickem-join-row">
          <input id="pickem-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={20}
                 placeholder="e.g. Penguins4Life" autoComplete="nickname" />
          <button type="submit" disabled={busy || name.trim().length < 3}>Join</button>
        </div>
        <p className="pickem-hint">Shown on the public leaderboard. No sign-up, no email.</p>
      </form>
      <details className="pickem-restore">
        <summary>Played on another device?</summary>
        <form className="pickem-join-row" onSubmit={restore}>
          <input id="pickem-code" aria-label="Recovery code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="pp_…" />
          <button type="submit" disabled={code.trim().length < 10}>Use code</button>
        </form>
      </details>
      {error && <p className="pickem-error" role="alert">{error}</p>}
    </section>
  );
}

function GameRow({ game, pick, onPick, inputs }) {
  const away = game.awayTeam.abbrev;
  const home = game.homeTeam.abbrev;
  const open = NOT_STARTED.has(game.gameState) && Date.now() < new Date(game.startTimeUTC).getTime();
  const a = inputs?.teams?.[away];
  const h = inputs?.teams?.[home];
  const row = (inputs?.games || []).find(([d, hm, aw]) => d === game.gameDate && hm === home && aw === away);
  const homeWin = a && h && inputs.model ? winProbability(h.rating, a.rating, inputs.model, Boolean(row?.[3]), Boolean(row?.[4])) : null;
  const modelPick = homeWin == null ? null : homeWin > 0.5 ? home : away;
  const modelPct = homeWin == null ? null : Math.round(100 * Math.max(homeWin, 1 - homeWin));

  const button = (team, logo) => (
    <button type="button" className={`pickem-team${pick === team ? " pickem-team-picked" : ""}`}
            aria-pressed={pick === team} disabled={!open} onClick={() => onPick(game.id, team)}>
      {logo && <img src={teamLogo(logo)} alt="" width="28" height="28" />}
      <span>{team}</span>
    </button>
  );

  return (
    <li className="pickem-game">
      <div className="pickem-teams">
        {button(away, game.awayTeam.logo)}
        <span className="pickem-at">@</span>
        {button(home, game.homeTeam.logo)}
      </div>
      <p className="pickem-meta">
        {open ? `Locks at ${startTime(game.startTimeUTC)}` : "Locked"}
        {/* PuckPulse's pick only after yours (or once it's locked), so it doesn't sway you. */}
        {modelPick && (pick || !open) && <> · PuckPulse picks <strong>{modelPick}</strong> ({modelPct}%)</>}
      </p>
    </li>
  );
}

function Leaderboard({ me }) {
  const { data, status } = useFetchWithStatus(`${API_BASE}/pickem/leaderboard`);
  if (status === "error") return <p className="pickem-hint">Couldn&apos;t load the leaderboard.</p>;
  if (!data) return <p className="pickem-hint">Loading…</p>;
  return (
    <section className="pickem-card">
      <h2>Leaderboard</h2>
      <p className="pickem-benchmark">
        PuckPulse, on every game: <strong>{record(data.puckpulse.correct, data.puckpulse.graded)}</strong>
      </p>
      {data.players.length === 0 ? (
        <p className="pickem-hint">No graded picks yet. Results post minutes after each final.</p>
      ) : (
        <table className="pickem-board">
          <thead><tr><th scope="col">#</th><th scope="col">Player</th><th scope="col">Right</th><th scope="col">Record</th></tr></thead>
          <tbody>
            {data.players.map((p, i) => (
              <tr key={p.name} className={p.name === me ? "row-selected" : undefined}>
                <td>{i + 1}</td><td>{p.name}</td><td>{p.correct}</td><td>{record(p.correct, p.graded)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function PickemPage() {
  const [key, setKey] = useState(savedKey);
  const [me, setMe] = useState(null);
  const [error, setError] = useState(null);
  const today = todayISO();
  const { data: scoreboard } = useFetchWithStatus(`${API_BASE}/games/date/${today}`);
  const { data: inputs } = useFetchWithStatus(`${API_BASE}/season-sim`);
  const games = (scoreboard?.games || []).filter((g) => g.gameType === 2 || g.gameType === 3);

  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    fetchMe(key, today)
      .then((m) => !cancelled && setMe(m))
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 401) {
          saveKey(null); // the code no longer matches a player: start over
          setKey(null);
        } else setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [key, today, reload]);

  const joined = (k) => {
    saveKey(k);
    setKey(k);
  };

  const pick = async (gameId, team) => {
    setError(null);
    setMe((m) => (m ? { ...m, picks: { ...m.picks, [String(gameId)]: team } } : m)); // show it right away
    try {
      await makePick(key, gameId, team);
      track("pickem-pick");
    } catch (err) {
      setError(err.message);
      setReload((n) => n + 1); // put back what the server has
    }
  };

  return (
    <main className="page pickem-page">
      <div className="page-header"><h1>Beat PuckPulse</h1></div>
      <p className="page-subtitle">Pick tonight&apos;s winners. A point for every right pick; picks lock at puck drop.</p>
      {!key ? (
        <JoinForm onJoined={joined} />
      ) : (
        <>
          {me && (
            <section className="pickem-card pickem-me">
              <p><strong>{me.name}</strong> · {record(me.record.correct, me.record.graded)}{me.record.pending > 0 && ` · ${me.record.pending} pending`}</p>
              {me.vs_puckpulse.games > 0 && (
                <p className="pickem-hint">
                  On your games: you {me.vs_puckpulse.you}, PuckPulse {me.vs_puckpulse.puckpulse} of {me.vs_puckpulse.games}
                </p>
              )}
            </section>
          )}
          <section className="pickem-card">
            <h2>Today</h2>
            {games.length === 0 ? (
              <p className="pickem-hint">No games today. <Link className="accent-link" to="/">See the schedule.</Link></p>
            ) : (
              <ul className="pickem-games">
                {games.map((g) => <GameRow key={g.id} game={g} pick={me?.picks?.[String(g.id)]} onPick={pick} inputs={inputs} />)}
              </ul>
            )}
            {error && <p className="pickem-error" role="alert">{error}</p>}
          </section>
          <details className="pickem-card pickem-restore">
            <summary>Play on another device</summary>
            <p className="pickem-hint">Your recovery code. Keep it private: anyone with it can make picks as you.</p>
            <code className="pickem-code">{key}</code>
          </details>
        </>
      )}
      <Leaderboard me={me?.name} />
    </main>
  );
}

export default PickemPage;
