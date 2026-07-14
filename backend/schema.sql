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

-- Current roster only -- one row per player currently on one of the 32
-- team rosters (~750 players), from https://api-web.nhle.com/v1/roster/{team}/current.
-- Re-running the ingestion just upserts, so released/traded players fall
-- out naturally next time their old team's roster is re-pulled... except
-- we never delete rows for players no longer listed, see ingest script note.
CREATE TABLE IF NOT EXISTS players (
    player_id           INTEGER PRIMARY KEY,        -- NHL API player id
    team_abbrev         VARCHAR(3) NOT NULL REFERENCES teams(team_abbrev),
    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,
    position_code       VARCHAR(1) NOT NULL,         -- C, L, R, D, G
    sweater_number      INTEGER,
    shoots_catches      VARCHAR(1),
    height_in_inches    INTEGER,
    weight_in_pounds    INTEGER,
    birth_date          DATE,
    birth_city          TEXT,
    birth_country       TEXT,
    headshot_url        TEXT,
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_players_team
    ON players (team_abbrev);

-- One row per player per season, refreshed each ingestion run (overwritten,
-- not a daily snapshot -- the NHL API's player landing page always returns
-- the season-to-date total in one call, so no need to poll daily like
-- standings_snapshots does). Skater and goalie stats share this table;
-- whichever set doesn't apply to a player's position stays NULL.
CREATE TABLE IF NOT EXISTS player_season_stats (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(player_id),
    season_id               INTEGER NOT NULL,
    games_played            INTEGER,
    -- skater stats
    goals                   INTEGER,
    assists                 INTEGER,
    points                  INTEGER,
    plus_minus              INTEGER,
    pim                     INTEGER,
    shots                   INTEGER,
    shooting_pctg           NUMERIC(6,4),
    power_play_goals        INTEGER,
    power_play_points       INTEGER,
    shorthanded_goals       INTEGER,
    shorthanded_points      INTEGER,
    game_winning_goals      INTEGER,
    ot_goals                INTEGER,
    -- goalie stats
    wins                    INTEGER,
    losses                  INTEGER,
    ot_losses               INTEGER,
    goals_against_avg       NUMERIC(6,4),
    save_pctg               NUMERIC(6,4),
    shutouts                INTEGER,
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (season_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_player_season_player
    ON player_season_stats (player_id, season_id);

-- One row per player per "season type" (regular season / playoffs),
-- refreshed each ingestion run (overwritten, not a daily snapshot --
-- same reasoning as player_season_stats). From the NHL API's player
-- landing page's careerTotals section, which is a single running
-- aggregate with no season_id dimension -- season_type plays that role
-- instead. A player with no playoff games at all (e.g. a rookie, or a
-- team that's never made the playoffs during their career) simply has
-- no 'playoffs' row here -- see ingest_player_stats.py. Skater and
-- goalie stats share this table, same as player_season_stats; whichever
-- set doesn't apply to a player's position stays NULL.
CREATE TABLE IF NOT EXISTS player_career_totals (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(player_id),
    season_type             VARCHAR(14) NOT NULL CHECK (season_type IN ('regular_season', 'playoffs')),
    games_played            INTEGER,
    -- skater stats
    goals                   INTEGER,
    assists                 INTEGER,
    points                  INTEGER,
    plus_minus              INTEGER,
    pim                     INTEGER,
    shots                   INTEGER,
    shooting_pctg           NUMERIC(6,4),
    power_play_goals        INTEGER,
    power_play_points       INTEGER,
    shorthanded_goals       INTEGER,
    shorthanded_points      INTEGER,
    game_winning_goals      INTEGER,
    ot_goals                INTEGER,
    -- goalie stats
    wins                    INTEGER,
    losses                  INTEGER,
    ot_losses               INTEGER,
    goals_against_avg       NUMERIC(6,4),
    save_pctg               NUMERIC(6,4),
    shutouts                INTEGER,
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (player_id, season_type)
);

CREATE INDEX IF NOT EXISTS idx_player_career_totals_player
    ON player_career_totals (player_id);

-- One row per player per season per "season type" (regular season /
-- playoffs), refreshed each ingestion run. From the NHL API's player
-- landing page's seasonTotals section, filtered to leagueAbbrev == "NHL"
-- only (that field also includes junior/international/other leagues,
-- out of scope for this app). Distinct from player_season_stats (which
-- only ever tracks the single current/latest season for roster and
-- leaderboard display) -- this table is the full career-spanning
-- breakdown for the player detail page, and does include the current
-- season too (some overlap with player_season_stats is expected and
-- fine; they serve different query patterns). A player traded mid-season
-- has multiple raw NHL API entries for the same (season, game type) --
-- see upsert_season_history() in ingest_player_stats.py for how those
-- get combined into the single row stored here. Skater and goalie stats
-- share this table, same split as player_season_stats/player_career_totals.
CREATE TABLE IF NOT EXISTS player_season_history (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(player_id),
    season_id               INTEGER NOT NULL,
    season_type             VARCHAR(14) NOT NULL CHECK (season_type IN ('regular_season', 'playoffs')),
    games_played            INTEGER,
    -- skater stats
    goals                   INTEGER,
    assists                 INTEGER,
    points                  INTEGER,
    plus_minus              INTEGER,
    pim                     INTEGER,
    shots                   INTEGER,
    shooting_pctg           NUMERIC(6,4),
    power_play_goals        INTEGER,
    power_play_points       INTEGER,
    shorthanded_goals       INTEGER,
    shorthanded_points      INTEGER,
    game_winning_goals      INTEGER,
    ot_goals                INTEGER,
    -- goalie stats
    wins                    INTEGER,
    losses                  INTEGER,
    ot_losses               INTEGER,
    goals_against_avg       NUMERIC(6,4),
    save_pctg               NUMERIC(6,4),
    shutouts                INTEGER,
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (player_id, season_id, season_type)
);

CREATE INDEX IF NOT EXISTS idx_player_season_history_player
    ON player_season_history (player_id, season_id);

-- Advanced possession/shot-quality stats sourced from MoneyPuck's public
-- seasonSummary CSVs (see ingest_advanced_stats.py). MoneyPuck's own site
-- and directory listings sit behind a Cloudflare bot-check demanding a paid
-- data license, but the individual CSV files under
-- moneypuck.com/moneypuck/playerData/seasonSummary/{season}/regular/*.csv
-- are not gated -- confirmed by fetching them directly. All rows here are
-- the "5on5" situation slice (MoneyPuck's CSVs include multiple situations
-- per team/player -- all, 5on5, 4on5, 5on4, other); 5-on-5 is the standard
-- reference frame the industry quotes CF%/FF%/xG% in, since special-teams
-- shot attempts otherwise swamp the signal. Recomputed from scratch each
-- ingestion run (not incremental), so this is always MoneyPuck's latest
-- published snapshot for the season.
CREATE TABLE IF NOT EXISTS team_advanced_stats (
    id                      SERIAL PRIMARY KEY,
    team_abbrev             VARCHAR(3) NOT NULL REFERENCES teams(team_abbrev),
    season_id               INTEGER NOT NULL,
    games_played            INTEGER,
    corsi_for_pct           NUMERIC(6,4),
    fenwick_for_pct         NUMERIC(6,4),
    xgoals_for_pct          NUMERIC(6,4),
    xgoals_for              NUMERIC(8,3),
    xgoals_against          NUMERIC(8,3),
    goals_for               INTEGER,
    goals_against           INTEGER,
    shots_on_goal_for       INTEGER,
    shots_on_goal_against   INTEGER,
    pdo                     NUMERIC(6,2),
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (season_id, team_abbrev)
);

CREATE INDEX IF NOT EXISTS idx_team_advanced_team
    ON team_advanced_stats (team_abbrev, season_id);

-- Same MoneyPuck source, one row per skater per season (goalies aren't
-- included -- on-ice possession shares aren't a meaningful goalie stat the
-- way they are for skaters, matching how the old Corsi/Fenwick
-- implementation also skater-only). individual_xgoals ("ixG") is the
-- player's own shot quality, independent of who else is on the ice --
-- useful alongside goals to see who's over/underperforming their chances.
-- pdo here is the player's on-ice shooting% + on-ice save% while they're
-- on the ice (not the team's), a common shorthand for "how sustainable is
-- this player's on-ice results."
CREATE TABLE IF NOT EXISTS player_advanced_stats (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(player_id),
    season_id               INTEGER NOT NULL,
    games_played            INTEGER,
    icetime_seconds         INTEGER,
    corsi_for_pct           NUMERIC(6,4),
    fenwick_for_pct         NUMERIC(6,4),
    xgoals_for_pct          NUMERIC(6,4),
    xgoals_for              NUMERIC(8,3),
    xgoals_against          NUMERIC(8,3),
    individual_xgoals       NUMERIC(8,3),
    pdo                     NUMERIC(6,2),
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (season_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_player_advanced_player
    ON player_advanced_stats (player_id, season_id);

-- Monte Carlo playoff-odds simulation. Multiple as_of_date rows per season
-- are expected -- a "live" row updated as the season progresses, plus any
-- backtest snapshots used to validate the model against a completed season.
-- The API always serves the latest as_of_date. See simulate_playoff_odds.py.
CREATE TABLE IF NOT EXISTS playoff_odds (
    id                      SERIAL PRIMARY KEY,
    season_id               INTEGER NOT NULL,
    as_of_date              DATE NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL REFERENCES teams(team_abbrev),
    playoff_pct             NUMERIC(6,4) NOT NULL,
    trials                  INTEGER NOT NULL,
    computed_at             TIMESTAMP DEFAULT NOW(),
    UNIQUE (season_id, as_of_date, team_abbrev)
);

CREATE INDEX IF NOT EXISTS idx_playoff_odds_lookup
    ON playoff_odds (season_id, as_of_date);