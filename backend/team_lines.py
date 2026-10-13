"""
Line combinations: each team's forward lines and defense pairs this season,
from MoneyPuck's lines.csv (5-on-5 only; free for non-commercial use with
credit). Run by ingest_advanced_stats.py; served by GET /teams/{team}/lines.

MoneyPuck's lineId is the players' 7-digit NHL ids joined together
("847794684780428482078" = 8477946, 8478042, 8482078), so the API can keep
only combinations whose players are all on the team's active roster today.

These are the most-used combinations so far, not tonight's lineup: nobody
publishes projected lines as open data, and scraping the sites that do
isn't allowed.
"""

import csv
import io

LINES_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/lines.csv"
SITUATION = "5on5"
KINDS = {"line": "line", "pairing": "pair"}  # MoneyPuck position -> ours

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_lines (
    season_id               INTEGER NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL,
    kind                    VARCHAR(4) NOT NULL,      -- 'line' (forwards) or 'pair' (defense)
    player_ids              INTEGER[] NOT NULL,
    names                   TEXT NOT NULL,            -- MoneyPuck's "Last-Last-Last"
    games_played            INTEGER NOT NULL,
    icetime_seconds         INTEGER NOT NULL,
    xg_pct                  NUMERIC(5,4),
    goals_for               INTEGER,
    goals_against           INTEGER,
    updated_at              TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (season_id, team_abbrev, kind, player_ids)
)
"""


def split_line_id(line_id):
    """MoneyPuck lineId -> [player ids] (7 digits each)."""
    text = str(line_id).strip()
    if not text.isdigit() or len(text) % 7:
        raise ValueError(f"unexpected lineId {line_id!r}")
    return [int(text[i:i + 7]) for i in range(0, len(text), 7)]


def parse_lines(csv_text):
    """5-on-5 rows -> dicts ready to save. Rows with an odd lineId are skipped."""
    out = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("situation") != SITUATION or row.get("position") not in KINDS:
            continue
        try:
            ids = split_line_id(row["lineId"])
        except ValueError:
            continue
        xg = row.get("xGoalsPercentage")
        out.append({
            "team_abbrev": row["team"],
            "kind": KINDS[row["position"]],
            "player_ids": ids,
            "names": row["name"],
            "games_played": int(float(row.get("games_played") or 0)),
            "icetime_seconds": int(float(row.get("icetime") or 0)),
            "xg_pct": float(xg) if xg not in (None, "") else None,
            "goals_for": int(float(row.get("goalsFor") or 0)),
            "goals_against": int(float(row.get("goalsAgainst") or 0)),
        })
    return out


def save_lines(cur, season_id, lines):
    """Replace the season's lines (combinations come and go as lineups change)."""
    cur.execute(TABLE_SQL)
    cur.execute("GRANT SELECT ON team_lines TO nhl_api_readonly")
    cur.execute("DELETE FROM team_lines WHERE season_id = %s", (season_id,))
    for line in lines:
        cur.execute(
            """
            INSERT INTO team_lines (season_id, team_abbrev, kind, player_ids, names, games_played,
                                    icetime_seconds, xg_pct, goals_for, goals_against, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING
            """,
            (season_id, line["team_abbrev"], line["kind"], line["player_ids"], line["names"], line["games_played"],
             line["icetime_seconds"], line["xg_pct"], line["goals_for"], line["goals_against"]),
        )
    return len(lines)


def display_names(roster):
    """{player_id: name to show}: last name, plus a first initial when two
    teammates share it (Washington has two Protases). roster: {id: (first, last)}."""
    counts = {}
    for _, last in roster.values():
        counts[last] = counts.get(last, 0) + 1
    return {pid: (f"{first[:1]}. {last}" if counts[last] > 1 else last) for pid, (first, last) in roster.items()}


def top_lines(rows, roster, forwards=4, pairs=3):
    """
    A lineup built from the most-used combinations: the line with the most
    ice time first, then the next one that shares no player with those
    already picked, up to `forwards` lines and `pairs` defense pairs. Only
    combinations whose players are all on the active roster count.
    rows: dicts with the team_lines columns. roster: {player_id: (first, last)}.
    Names come from our players table, not MoneyPuck's (which drops accents).
    """
    names = display_names(roster)
    current = sorted((r for r in rows if set(r["player_ids"]) <= set(roster)), key=lambda r: -r["icetime_seconds"])

    def pick(kind, limit):
        picked, used = [], set()
        for r in current:
            ids = list(r["player_ids"])
            if r["kind"] != kind or used & set(ids):
                continue
            used |= set(ids)
            picked.append({
                "players": [names[i] for i in ids], "player_ids": ids,
                "minutes": round(r["icetime_seconds"] / 60), "games": r["games_played"],
                "xg_pct": float(r["xg_pct"]) if r["xg_pct"] is not None else None,
                "goals_for": r["goals_for"], "goals_against": r["goals_against"],
            })
            if len(picked) == limit:
                break
        return picked

    return {"lines": pick("line", forwards), "pairs": pick("pair", pairs)}
