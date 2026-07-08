-- NHL Stats Dashboard schema
-- Based on real response shape from https://api-web.nhle.com/v1/standings/now

CREATE TABLE IF NOT EXISTS teams (
    team_abbrev     VARCHAR(3) PRIMARY KEY,   -- e.g. 'PIT'
    team_name       TEXT NOT NULL,             -- e.g. 'Pittsburgh Penguins'
    common_name     TEXT,                      -- e.g. 'Penguins'
    place_name      TEXT,                      -- e.g. 'Pittsburgh'
    conference      TEXT,                      -- 'Eastern' / 'Western'
    division         TEXT,                      -- 'Metropolitan', 'Atlantic', etc
    logo_url        TEXT
);

-- One row per team per day standings are pulled.
-- This is what lets you chart trends over the season instead of
-- only ever seeing "right now."
CREATE TABLE IF NOT EXISTS standings_snapshots (
    id                      SERIAL PRIMARY KEY,
    snapshot_date           DATE NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL REFERENCES teams(team_abbrev),
    season_id               INTEGER NOT NULL,       -- e.g. 20252026
    games_played            INTEGER,
    wins                    INTEGER,
    losses                  INTEGER,
    ot_losses               INTEGER,
    points                  INTEGER,
    point_pctg              NUMERIC(6,4),
    goal_for                INTEGER,
    goal_against            INTEGER,
    goal_differential       INTEGER,
    home_wins               INTEGER,
    home_losses             INTEGER,
    road_wins               INTEGER,
    road_losses             INTEGER,
    l10_wins                INTEGER,
    l10_losses              INTEGER,
    l10_ot_losses           INTEGER,
    streak_code             VARCHAR(1),             -- 'W' or 'L' or 'OT'
    streak_count            INTEGER,
    division_sequence       INTEGER,                -- rank within division
    conference_sequence     INTEGER,                -- rank within conference
    league_sequence         INTEGER,                -- overall league rank
    wildcard_sequence       INTEGER,
    created_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (snapshot_date, team_abbrev)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_team_date
    ON standings_snapshots (team_abbrev, snapshot_date);

-- One row per team per completed season -- backfilled once from the NHL API's
-- historical /v1/standings/{date} endpoint using each season's final date.
-- Kept separate from standings_snapshots since mixing one-point-per-year
-- with a season's dense daily points doesn't make sense on one chart.
-- team_abbrev is NOT a foreign key here (unlike standings_snapshots) --
-- relocated/renamed franchises (e.g. Arizona Coyotes -> Utah, 'ARI' -> 'UTA')
-- show up under their historical abbreviation, which won't exist in `teams`.
CREATE TABLE IF NOT EXISTS season_final_standings (
    id                      SERIAL PRIMARY KEY,
    season_id               INTEGER NOT NULL,       -- e.g. 20232024
    team_abbrev             VARCHAR(3) NOT NULL,
    games_played            INTEGER,
    wins                    INTEGER,
    losses                  INTEGER,
    ot_losses               INTEGER,
    points                  INTEGER,
    point_pctg              NUMERIC(6,4),
    goal_for                INTEGER,
    goal_against            INTEGER,
    goal_differential       INTEGER,
    division_sequence       INTEGER,
    conference_sequence     INTEGER,
    league_sequence         INTEGER,
    made_playoffs           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (season_id, team_abbrev)
);

CREATE INDEX IF NOT EXISTS idx_season_final_team
    ON season_final_standings (team_abbrev, season_id);