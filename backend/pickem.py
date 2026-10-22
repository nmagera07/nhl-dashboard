"""
"Beat PuckPulse" pick'em: pick each game's winner before puck drop, one
point per correct pick, on a public leaderboard, with PuckPulse's own
picks (the model's favorite) as the benchmark.

No accounts: joining with a display name returns a random key the browser
keeps (and shows as a recovery code for another device). Only the key's
SHA-256 hash is stored, so a database leak doesn't hand out keys. Keys
travel in POST bodies, never in URLs or logs.

Results come from game_results (written by notify_live_games.py when a
game goes final, minutes after it ends) and, as a fallback, the nightly
grading in game_predictions.

Tables are created by scripts/setup_pickem.py (and schema.sql); the API
role can read and write the pick'em tables.
"""

import hashlib
import re
import secrets
from datetime import datetime, timezone

NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]{3,20}$")
RESERVED = ("puckpulse", "admin", "moderator", "official")
# A filter for public display names, aimed at slurs and hate (not exhaustive).
# BLOCKED terms match anywhere in the name; WORDS only as a whole word ("spic"
# but not "Conspicuous"). Both are checked after undoing number swaps (n1gg3r)
# and, for BLOCKED, also with repeated letters squeezed (niiigger -> niger).
BLOCKED = (
    "fuck", "shit", "cunt", "bitch", "whore", "slut", "rape", "retard",
    "nigg", "nigga", "niga", "nigr", "niger", "fag", "kike", "kyke", "wetback", "beaner", "towelhead", "raghead",
    "sandnig", "gook", "chingchong", "tranny",
    "nazi", "hitler", "heil", "fuhrer", "reich", "kkk", "klan", "whitepower", "whitepride", "aryan", "holocaust",
    "auschwitz", "gasthe", "ovens", "jewboy", "jewrat", "dirtyjew", "killjew", "hatejew", "fuckjew", "zog",
)
WORDS = ("spic", "spick", "chink", "coon", "jap", "paki", "gyp", "goy", "goyim", "yid", "kraut", "negro", "abo")
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g"})
NOT_STARTED = {"FUT", "PRE"}

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS pickem_players (
    player_id               UUID PRIMARY KEY,
    key_hash                CHAR(64) NOT NULL UNIQUE,
    display_name            VARCHAR(20) NOT NULL,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS pickem_players_name ON pickem_players (LOWER(display_name));
CREATE TABLE IF NOT EXISTS pickem_picks (
    player_id               UUID NOT NULL REFERENCES pickem_players (player_id) ON DELETE CASCADE,
    game_id                 BIGINT NOT NULL,
    game_date               DATE NOT NULL,
    home_abbrev             VARCHAR(3) NOT NULL,
    away_abbrev             VARCHAR(3) NOT NULL,
    pick                    VARCHAR(3) NOT NULL,
    picked_at               TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (player_id, game_id)
);
CREATE INDEX IF NOT EXISTS pickem_picks_game ON pickem_picks (game_id);
CREATE TABLE IF NOT EXISTS game_results (
    game_id                 BIGINT PRIMARY KEY,
    home_won                BOOLEAN NOT NULL,
    home_score              SMALLINT,
    away_score              SMALLINT,
    recorded_at             TIMESTAMPTZ DEFAULT NOW()
);
"""
GRANTS_SQL = """
GRANT SELECT, INSERT, UPDATE ON pickem_players, pickem_picks TO nhl_api_readonly;
GRANT SELECT ON game_results TO nhl_api_readonly;
"""

# Finished games: the live notifier's results first, then the nightly grading.
RESULTS_CTE = """
results AS (
    SELECT game_id, home_won FROM game_results
    UNION ALL
    SELECT game_id, home_won FROM game_predictions
    WHERE home_won IS NOT NULL AND game_id NOT IN (SELECT game_id FROM game_results)
)
"""


def name_problem(name):
    """Why a display name can't be used, or None if it's fine."""
    name = (name or "").strip()
    if not NAME_RE.match(name):
        return "Names are 3-20 letters, numbers, spaces, or _ . -"
    if not re.search(r"[A-Za-z]", name):
        return "Names need at least one letter."
    squashed = re.sub(r"[^a-z]", "", name.lower())
    if any(word in squashed for word in RESERVED):
        return "That name is reserved."
    if _offensive(name):
        return "Please pick a different name."
    return None


def _offensive(name):
    if "1488" in re.sub(r"[^0-9]", "", name):
        return True
    letters = re.sub(r"[^a-z]", "", name.lower().translate(LEET))
    squeezed = re.sub(r"(.)\1+", r"\1", letters)
    if any(term in letters or term in squeezed for term in BLOCKED):
        return True
    # Whole words: split on spaces and punctuation, and on capitals in CamelCase names.
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z0-9]+(?![a-z])", name)
    return any(re.sub(r"[^a-z]", "", form) in WORDS for w in words for form in (w.lower(), w.lower().translate(LEET)))


def new_key():
    """A random player key: shown once as the recovery code, stored only hashed."""
    return "pp_" + secrets.token_urlsafe(24)


def hash_key(key):
    return hashlib.sha256((key or "").encode()).hexdigest()


def pick_problem(game, team, now=None):
    """Why this pick can't be made, or None. game: an NHL box score/landing dict."""
    now = now or datetime.now(timezone.utc)
    home = (game.get("homeTeam") or {}).get("abbrev")
    away = (game.get("awayTeam") or {}).get("abbrev")
    if team not in (home, away):
        return "Pick one of the two teams in this game."
    start = game.get("startTimeUTC")
    started = game.get("gameState") not in NOT_STARTED
    if start:
        started = started or now >= datetime.fromisoformat(start.replace("Z", "+00:00"))
    if started:
        return "This game has started; picks are locked."
    return None


def player_record(cur, player_id):
    """Graded picks, correct picks, pending picks, and PuckPulse's record on the same graded games."""
    cur.execute(
        f"""
        WITH {RESULTS_CTE}
        SELECT
            COUNT(r.home_won) AS graded,
            COUNT(*) FILTER (WHERE (p.pick = p.home_abbrev) = r.home_won) AS correct,
            COUNT(*) FILTER (WHERE r.home_won IS NULL) AS pending,
            COUNT(*) FILTER (WHERE r.home_won IS NOT NULL AND gp.home_win_prob IS NOT NULL) AS model_games,
            COUNT(*) FILTER (WHERE (gp.home_win_prob > 0.5) = r.home_won) AS model_correct
        FROM pickem_picks p
        LEFT JOIN results r ON r.game_id = p.game_id
        LEFT JOIN game_predictions gp ON gp.game_id = p.game_id
        WHERE p.player_id = %s
        """,
        (player_id,),
    )
    return cur.fetchone()


def leaderboard(cur, limit=50):
    """Players by correct picks (then accuracy), and PuckPulse's record on every graded game."""
    cur.execute(
        f"""
        WITH {RESULTS_CTE}
        SELECT pl.display_name,
               COUNT(*) FILTER (WHERE (p.pick = p.home_abbrev) = r.home_won) AS correct,
               COUNT(r.home_won) AS graded
        FROM pickem_picks p
        JOIN pickem_players pl ON pl.player_id = p.player_id
        JOIN results r ON r.game_id = p.game_id
        GROUP BY pl.display_name
        ORDER BY correct DESC, graded ASC, pl.display_name
        LIMIT %s
        """,
        (limit,),
    )
    players = cur.fetchall()
    cur.execute(
        f"""
        WITH {RESULTS_CTE}
        SELECT COUNT(*) FILTER (WHERE (gp.home_win_prob > 0.5) = r.home_won) AS correct, COUNT(*) AS graded
        FROM game_predictions gp JOIN results r ON r.game_id = gp.game_id
        WHERE gp.source = 'daily'
        """
    )
    return players, cur.fetchone()
