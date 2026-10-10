"""app.compact: the question-shaped summaries sent to the model."""

import json

from app import compact


def standing(abbrev, **overrides):
    row = {
        "team_abbrev": abbrev, "team_name": f"{abbrev} Team", "season_id": 20262027, "snapshot_date": "2026-10-08",
        "division": "Metropolitan", "conference": "Eastern", "games_played": 4,
        "wins": 2, "losses": 2, "ot_losses": 0, "points": 4, "point_pctg": 0.5,
        "goal_for": 15, "goal_against": 10, "goal_differential": 5,
        "home_wins": 1, "home_losses": 1, "road_wins": 1, "road_losses": 1,
        "l10_wins": 2, "l10_losses": 2, "l10_ot_losses": 0, "streak_code": "L", "streak_count": 2,
        "division_sequence": 4, "conference_sequence": 8, "league_sequence": 17, "wildcard_sequence": 0,
        "logo_url": "https://example.com/logo.svg", "created_at": "2026-10-08T06:00:00", "xgoals_for_pct": None,
    }
    row.update(overrides)
    return row


def skater(pid, pts, goals=0, team="PIT"):
    return {"player_id": pid, "first_name": "Skater", "last_name": str(pid), "team_abbrev": team,
            "position_code": "C", "games_played": 4, "goals": goals, "assists": pts - goals, "points": pts,
            "headshot_url": "https://example.com/x.png", "birth_city": "Somewhere"}


def goalie(pid, wins, gp=4):
    return {"player_id": pid, "first_name": "Goalie", "last_name": str(pid), "team_abbrev": "PIT",
            "position_code": "G", "games_played": gp, "wins": wins, "losses": 1, "ot_losses": 0,
            "goals_against_avg": 2.123, "save_pctg": 0.91234, "shutouts": 0}


class TestStandingRow:
    def test_keeps_what_questions_need_and_drops_noise(self):
        row = compact.standing_row(standing("PIT"), playoff_pct=0.669)

        assert row["record"] == "2-2-0"
        assert row["streak"] == "L2"
        assert row["home"] == "1-1"
        assert row["playoff_odds_pct"] == 66.9
        assert row["point_pct"] == 50.0
        for noise in ("logo_url", "created_at", "xgoals_for_pct"):
            assert noise not in row

    def test_a_zero_wildcard_rank_is_dropped_not_reported_as_a_rank(self):
        assert "wildcard_rank" not in compact.standing_row(standing("NYR", wildcard_sequence=0))
        assert compact.standing_row(standing("PIT", wildcard_sequence=2))["wildcard_rank"] == 2


class TestPlayoffSpot:
    def test_spells_out_the_playoff_picture(self):
        assert compact.playoff_spot(standing("NYR", division_sequence=1, wildcard_sequence=0)) == "Metropolitan #1 (in)"
        assert compact.playoff_spot(standing("PIT", division_sequence=4, wildcard_sequence=2, conference="Eastern")) == "Eastern wild card 2 (in)"
        assert compact.playoff_spot(standing("CBJ", division_sequence=5, wildcard_sequence=6, conference="Eastern")) == "Outside (Eastern wild-card race #6)"


class TestPlayoffPicture:
    def test_lists_division_top_threes_and_conference_wild_cards(self):
        rows = [
            standing("NYR", division_sequence=1, wildcard_sequence=0),
            standing("CAR", division_sequence=2, wildcard_sequence=0),
            standing("WSH", division_sequence=3, wildcard_sequence=0),
            standing("PIT", division_sequence=4, wildcard_sequence=2),
            standing("BUF", division="Atlantic", division_sequence=4, wildcard_sequence=1),
            standing("CBJ", division_sequence=5, wildcard_sequence=3),
        ]

        east = compact.playoff_picture(rows)["Eastern"]

        assert east["Metropolitan top 3"] == ["NYR", "CAR", "WSH"]
        assert east["wild cards"] == ["BUF", "PIT"]
        assert east["next out"] == ["CBJ"]


class TestLeadersAndOdds:
    def test_leaders_are_the_top_few_not_every_player(self):
        players = [skater(i, pts=i % 20, goals=i % 7) for i in range(1, 1200)] + [goalie(5000, wins=3), goalie(5001, wins=0, gp=0)]

        top = compact.leaders(players)

        assert len(top["points"]) == compact.TOP_POINTS
        assert top["points"][0]["pts"] == 19
        assert [g["name"] for g in top["goalie_wins"]] == ["Goalie 5000"]  # 0 GP excluded
        assert len(json.dumps(top)) < 4000

    def test_ignores_playoff_odds_from_another_season(self):
        odds = [{"team_abbrev": "PIT", "playoff_pct": 1.0, "season_id": 20252026, "as_of_date": "2026-04-17"}]

        by_team, as_of = compact.odds_by_team([standing("PIT")], odds)

        assert by_team == {} and as_of is None


class TestTeamFacts:
    def test_standing_plus_roster_sorted_by_points(self):
        roster = [skater(1, 2), skater(2, 7), goalie(3, wins=2)]

        facts = compact.team_facts("PIT", [standing("PIT")], roster, [])

        assert facts["standing"]["record"] == "2-2-0"
        assert [p["pts"] for p in facts["skaters"]] == [7, 2]
        assert facts["goalies"][0]["save_pct"] == 0.912
        assert "team" not in facts["skaters"][0]  # it's the team page; no need to repeat


class TestPlayerFacts:
    def test_season_career_and_recent_history(self):
        player = {
            "first_name": "Sidney", "last_name": "Crosby", "position_code": "C", "team_name": "Pittsburgh Penguins",
            "height_in_inches": 71, "birth_city": "Cole Harbour", "birth_country": "CAN",
            "season_stats": [{"season_id": 20262027, "games_played": 4, "goals": 0, "assists": 2, "points": 2}],
            "career_totals": {"regular_season": {"games_played": 1424, "points": 1763}},
            "season_history": [{"season_id": 20262027 - 10001 * i, "season_type": "regular_season", "points": i} for i in range(8)],
        }

        facts = compact.player_facts(player)

        assert facts["name"] == "Sidney Crosby"
        assert facts["height"] == "5'11\""
        assert facts["birthplace"] == "Cole Harbour, CAN"
        assert facts["this_season"] == {"season": "2026-27", "gp": 4, "g": 0, "a": 2, "pts": 2}
        assert facts["career_regular_season"]["pts"] == 1763
        assert len(facts["recent_seasons"]) == compact.RECENT_SEASONS


class TestGameFacts:
    def test_writes_goals_as_readable_lines_and_keeps_the_box_score(self):
        game = {
            "gameState": "OFF", "gameDate": "2026-10-06", "gameOutcome": {"lastPeriodType": "OT"},
            "awayTeam": {"abbrev": "NSH", "score": 4, "sog": 25, "placeName": {"default": "Nashville"}, "commonName": {"default": "Predators"}},
            "homeTeam": {"abbrev": "TOR", "score": 5, "sog": 37},
            "linescore": {"byPeriod": [{"periodDescriptor": {"number": 1, "periodType": "REG"}, "away": 2, "home": 0}]},
            "summary": {
                "scoring": [{
                    "periodDescriptor": {"number": 4, "periodType": "OT"},
                    "goals": [{"timeInPeriod": "04:46", "teamAbbrev": {"default": "TOR"}, "name": {"default": "A. Matthews"},
                               "goalsToDate": 2, "strength": "ev", "goalModifier": "none",
                               "assists": [{"name": {"default": "W. Nylander"}}], "awayScore": 4, "homeScore": 5}],
                }],
                "threeStars": [{"star": 1, "name": {"default": "G. McKenna"}, "teamAbbrev": "TOR", "goals": 1, "assists": 1}],
            },
            "teamGameStats": [{"category": "sog", "awayValue": 25, "homeValue": 37}],
            "playerByGameStats": {"homeTeam": {
                "forwards": [{"name": {"default": "A. Matthews"}, "goals": 1, "assists": 0, "points": 1, "sog": 4, "toi": "20:01"}],
                "goalies": [{"name": {"default": "Starter"}, "saves": 21, "shotsAgainst": 25, "toi": "64:46"},
                            {"name": {"default": "Backup"}, "toi": "00:00"}],
            }},
        }

        facts = compact.game_facts(game)

        assert facts["away"]["name"] == "Nashville Predators"
        assert facts["ended_in"] == "OT"
        assert facts["scoring"] == ["OT 04:46 TOR: A. Matthews (2), assists: W. Nylander -> 4-5 (away-home)"]
        assert facts["goals_by_period"] == [{"period": "P1", "away": 2, "home": 0}]
        assert facts["three_stars"][0]["name"] == "G. McKenna"
        assert [g["name"] for g in facts["home_players"]["goalies"]] == ["Starter"]
        assert "current_period" not in facts  # only for live games
