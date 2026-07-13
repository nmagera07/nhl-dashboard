"""
Phase 1 -- pure function tests for ingest_player_stats.py's season-history
aggregation, plus a lightweight fake-cursor exercise of upsert_season_history
itself (no real DB, no network -- same reasoning as the API test suite's
DBRouter, just a much smaller recorder since ingestion only ever INSERTs).

_combine_season_entries() is the trickiest part of the season-history
feature: when a player is traded mid-season, the NHL API gives multiple
seasonTotals entries for the same (season, gameTypeId), and they must be
combined by summing counting stats and *recomputing* rate stats
(shooting_pctg, save_pctg, goals_against_avg) from the summed underlying
counts -- never by averaging the per-entry rates, which misweights a short
stint the same as a long one. Both the naive-average failure mode and the
correct recomputation are asserted below with hand-verifiable numbers.
"""

import pytest

from ingest_player_stats import (
    _combine_season_entries,
    _parse_time_on_ice_to_seconds,
    upsert_season_history,
)


# ---------------------------------------------------------------------------
# _parse_time_on_ice_to_seconds
# ---------------------------------------------------------------------------


class TestParseTimeOnIceToSeconds:
    def test_typical_goalie_season_total(self):
        # Real Wedgewood-shaped value -- arbitrarily large minutes, since
        # this is a season (or even career) total, not a single period.
        assert _parse_time_on_ice_to_seconds("2549:04") == 2549 * 60 + 4

    def test_zero(self):
        assert _parse_time_on_ice_to_seconds("0:00") == 0

    def test_none_or_missing_is_zero(self):
        # A skater-only entry has no timeOnIce at all -- treated as 0 so
        # it doesn't break the sum across a mixed group (shouldn't happen
        # in practice since a group is always all-goalie or all-skater,
        # but the function itself doesn't assume that).
        assert _parse_time_on_ice_to_seconds(None) == 0

    def test_empty_string_is_zero(self):
        assert _parse_time_on_ice_to_seconds("") == 0


# ---------------------------------------------------------------------------
# _combine_season_entries
# ---------------------------------------------------------------------------


class TestCombineSeasonEntries:
    def test_save_pctg_is_recomputed_not_averaged(self):
        # The exact worked example from the design: a big, bad stint and
        # a smaller, better one. Naively averaging the two entries' own
        # save_pctgs would give the wrong answer -- entry A's raw save_pctg
        # is (100-10)/100 = 0.90, entry B's is (50-5)/50 = 0.90 -- so this
        # particular pair doesn't even expose the bug by naive averaging.
        # See test_save_pctg_recompute_diverges_from_naive_average below
        # for a pair where the difference is unmistakable.
        entries = [
            {"goalsAgainst": 10, "shotsAgainst": 100, "timeOnIce": "1000:00"},
            {"goalsAgainst": 5, "shotsAgainst": 50, "timeOnIce": "500:00"},
        ]
        combined = _combine_season_entries(entries)
        assert combined["savePctg"] == pytest.approx(0.9)

    def test_save_pctg_recompute_diverges_from_naive_average(self):
        # entry A: 10 shots against, 9 goals against -> raw save_pctg 0.10
        # entry B: 90 shots against, 0 goals against -> raw save_pctg 1.00
        # A naive average of the two raw pctgs would be 0.55 -- very wrong.
        # The correct, count-weighted recompute is (100-9)/100 = 0.91.
        entries = [
            {"goalsAgainst": 9, "shotsAgainst": 10, "timeOnIce": "10:00"},
            {"goalsAgainst": 0, "shotsAgainst": 90, "timeOnIce": "90:00"},
        ]
        combined = _combine_season_entries(entries)
        assert combined["savePctg"] == pytest.approx(0.91)

    def test_goals_against_avg_is_recomputed_from_summed_counts(self):
        # entry A: 6 goals against over 1800:00 (108000 seconds)
        # entry B: 4 goals against over 1200:00 (72000 seconds)
        # total: 10 goals against over 180000 seconds
        # GAA = goals-per-60-minutes = 10 * 3600 / 180000 = 0.2
        entries = [
            {"goalsAgainst": 6, "shotsAgainst": 0, "timeOnIce": "1800:00"},
            {"goalsAgainst": 4, "shotsAgainst": 0, "timeOnIce": "1200:00"},
        ]
        combined = _combine_season_entries(entries)
        assert combined["goalsAgainstAvg"] == pytest.approx(0.2)

    def test_shooting_pctg_is_recomputed_not_averaged(self):
        # entry A: 9 goals on 10 shots -> raw shooting_pctg 0.90
        # entry B: 0 goals on 90 shots -> raw shooting_pctg 0.00
        # Naive average would be 0.45. Correct recompute: 9/100 = 0.09.
        entries = [
            {"goals": 9, "shots": 10},
            {"goals": 0, "shots": 90},
        ]
        combined = _combine_season_entries(entries)
        assert combined["shootingPctg"] == pytest.approx(0.09)

    def test_counting_stats_are_summed_across_entries(self):
        entries = [
            {"gamesPlayed": 20, "goals": 3, "assists": 5, "points": 8, "pim": 10},
            {"gamesPlayed": 15, "goals": 2, "assists": 1, "points": 3, "pim": 6},
        ]
        combined = _combine_season_entries(entries)
        assert combined["gamesPlayed"] == 35
        assert combined["goals"] == 5
        assert combined["assists"] == 6
        assert combined["points"] == 11
        assert combined["pim"] == 16

    def test_none_values_count_as_zero_when_summing(self):
        # A goalie's entries won't have skater fields like plusMinus/shots,
        # and vice versa -- None must not poison the sum.
        entries = [
            {"gamesPlayed": 10, "wins": 6, "losses": 4, "goals": None, "shots": None},
            {"gamesPlayed": 8, "wins": 5, "losses": 3, "goals": None, "shots": None},
        ]
        combined = _combine_season_entries(entries)
        assert combined["wins"] == 11
        assert combined["losses"] == 7
        assert combined["goals"] == 0
        assert combined["shots"] == 0

    def test_zero_shots_gives_none_shooting_pctg_not_division_by_zero(self):
        entries = [{"goals": 0, "shots": 0}, {"goals": 0, "shots": 0}]
        combined = _combine_season_entries(entries)
        assert combined["shootingPctg"] is None

    def test_zero_shots_against_gives_none_save_pctg(self):
        entries = [
            {"goalsAgainst": 0, "shotsAgainst": 0, "timeOnIce": "0:00"},
            {"goalsAgainst": 0, "shotsAgainst": 0, "timeOnIce": "0:00"},
        ]
        combined = _combine_season_entries(entries)
        assert combined["savePctg"] is None

    def test_zero_time_on_ice_gives_none_goals_against_avg(self):
        entries = [
            {"goalsAgainst": 0, "shotsAgainst": 0, "timeOnIce": "0:00"},
            {"goalsAgainst": 0, "shotsAgainst": 0, "timeOnIce": "0:00"},
        ]
        combined = _combine_season_entries(entries)
        assert combined["goalsAgainstAvg"] is None

    def test_real_shaped_wedgewood_multi_team_season(self):
        # Shaped after the real, confirmed case: Scott Wedgewood
        # (player_id 8475809), season 20212022, traded mid-season -- 3
        # separate NHL regular-season entries across 3 teams. Numbers here
        # are synthetic (hand-verifiable) but shaped like the real entries.
        entries = [
            {
                "season": 20212022,
                "gameTypeId": 2,
                "leagueAbbrev": "NHL",
                "gamesPlayed": 15,
                "wins": 8,
                "losses": 5,
                "otLosses": 1,
                "goalsAgainst": 40,
                "shotsAgainst": 400,
                "timeOnIce": "900:00",
                "shutouts": 1,
            },
            {
                "season": 20212022,
                "gameTypeId": 2,
                "leagueAbbrev": "NHL",
                "gamesPlayed": 10,
                "wins": 4,
                "losses": 4,
                "otLosses": 1,
                "goalsAgainst": 25,
                "shotsAgainst": 250,
                "timeOnIce": "600:00",
                "shutouts": 0,
            },
            {
                "season": 20212022,
                "gameTypeId": 2,
                "leagueAbbrev": "NHL",
                "gamesPlayed": 5,
                "wins": 1,
                "losses": 3,
                "otLosses": 0,
                "goalsAgainst": 15,
                "shotsAgainst": 100,
                "timeOnIce": "300:00",
                "shutouts": 0,
            },
        ]
        combined = _combine_season_entries(entries)

        assert combined["gamesPlayed"] == 30
        assert combined["wins"] == 13
        assert combined["losses"] == 12
        assert combined["otLosses"] == 2
        assert combined["shutouts"] == 1
        # total goals against = 80, total shots against = 750
        assert combined["savePctg"] == pytest.approx((750 - 80) / 750)
        # total seconds = (900 + 600 + 300) * 60 = 108000
        assert combined["goalsAgainstAvg"] == pytest.approx(80 * 3600 / 108000)


# ---------------------------------------------------------------------------
# upsert_season_history -- fake-cursor exercise of the grouping/filtering
# logic (leagueAbbrev filter, gameTypeId mapping, single vs. multi-entry
# groups), without a real DB.
# ---------------------------------------------------------------------------


class _RecordingCursor:
    """Records every execute() call's (query, params) -- INSERT-only, no
    fetchone/fetchall needed since ingestion never reads its own writes."""

    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()).lower(), params))


class TestUpsertSeasonHistory:
    def test_no_nhl_entries_returns_false_and_writes_nothing(self):
        cur = _RecordingCursor()
        landing = {"seasonTotals": [{"season": 20112012, "gameTypeId": 2, "leagueAbbrev": "QMJHL"}]}

        result = upsert_season_history(cur, 8477492, landing)

        assert result is False
        assert cur.calls == []

    def test_missing_season_totals_key_returns_false(self):
        cur = _RecordingCursor()
        assert upsert_season_history(cur, 8477492, {}) is False
        assert cur.calls == []

    def test_non_nhl_leagues_are_filtered_out(self):
        cur = _RecordingCursor()
        landing = {
            "seasonTotals": [
                {"season": 20112012, "gameTypeId": 2, "leagueAbbrev": "QMJHL", "goals": 31},
                {"season": 20252026, "gameTypeId": 2, "leagueAbbrev": "NHL", "goals": 7, "shots": 47},
            ]
        }

        result = upsert_season_history(cur, 8477492, landing)

        assert result is True
        assert len(cur.calls) == 1
        _, params = cur.calls[0]
        assert params[1] == 20252026  # season_id
        assert params[4] == 7  # goals

    def test_unknown_game_type_id_is_skipped(self):
        cur = _RecordingCursor()
        landing = {
            "seasonTotals": [
                {"season": 20252026, "gameTypeId": 99, "leagueAbbrev": "NHL", "goals": 1},
            ]
        }

        result = upsert_season_history(cur, 8477492, landing)

        assert result is False
        assert cur.calls == []

    def test_single_entry_group_passes_raw_fields_through(self):
        cur = _RecordingCursor()
        landing = {
            "seasonTotals": [
                {
                    "season": 20252026,
                    "gameTypeId": 2,
                    "leagueAbbrev": "NHL",
                    "gamesPlayed": 13,
                    "goals": 7,
                    "assists": 8,
                    "shots": 47,
                    "shootingPctg": 0.148936,
                },
            ]
        }

        result = upsert_season_history(cur, 8477492, landing)

        assert result is True
        query, params = cur.calls[0]
        assert "insert into player_season_history" in query
        assert params[2] == "regular_season"  # season_type
        assert params[3] == 13  # games_played
        assert params[10] == pytest.approx(0.148936)  # shooting_pctg passed through as-is

    def test_regular_season_and_playoffs_produce_separate_rows(self):
        cur = _RecordingCursor()
        landing = {
            "seasonTotals": [
                {"season": 20252026, "gameTypeId": 2, "leagueAbbrev": "NHL", "gamesPlayed": 60},
                {"season": 20252026, "gameTypeId": 3, "leagueAbbrev": "NHL", "gamesPlayed": 12},
            ]
        }

        result = upsert_season_history(cur, 8477492, landing)

        assert result is True
        assert len(cur.calls) == 2
        season_types = {params[2] for _, params in cur.calls}
        assert season_types == {"regular_season", "playoffs"}

    def test_multi_entry_group_is_combined_before_upsert(self):
        # Two entries for the same (season, gameTypeId) -- a mid-season
        # trade -- must produce exactly one row with summed/recomputed
        # values, not two rows and not a naive average.
        cur = _RecordingCursor()
        landing = {
            "seasonTotals": [
                {
                    "season": 20212022,
                    "gameTypeId": 2,
                    "leagueAbbrev": "NHL",
                    "gamesPlayed": 15,
                    "wins": 8,
                    "losses": 5,
                    "otLosses": 1,
                    "goalsAgainst": 40,
                    "shotsAgainst": 400,
                    "timeOnIce": "900:00",
                    "shutouts": 1,
                },
                {
                    "season": 20212022,
                    "gameTypeId": 2,
                    "leagueAbbrev": "NHL",
                    "gamesPlayed": 10,
                    "wins": 4,
                    "losses": 4,
                    "otLosses": 1,
                    "goalsAgainst": 25,
                    "shotsAgainst": 250,
                    "timeOnIce": "600:00",
                    "shutouts": 0,
                },
            ]
        }

        result = upsert_season_history(cur, 8475809, landing)

        assert result is True
        assert len(cur.calls) == 1
        _, params = cur.calls[0]
        assert params[3] == 25  # games_played summed
        # column order: player_id, season_id, season_type, games_played,
        # goals, assists, points, plus_minus, pim, shots, shooting_pctg,
        # power_play_goals, power_play_points, shorthanded_goals,
        # shorthanded_points, game_winning_goals, ot_goals,
        # wins, losses, ot_losses, goals_against_avg, save_pctg, shutouts
        assert params[17] == 12  # wins summed
        assert params[18] == 9  # losses summed
        assert params[19] == 2  # ot_losses summed
        assert params[22] == 1  # shutouts summed
        assert params[20] == pytest.approx(65 * 3600 / 90000)  # goals_against_avg
        assert params[21] == pytest.approx((650 - 65) / 650)  # save_pctg
