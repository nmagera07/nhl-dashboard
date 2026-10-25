"""compare_card and the compare share card routes."""

import compare_card

ERA = {"reference": 3.08, "reference_season": 20252026, "seasons": {"19851986": 3.97, "20222023": 3.18}}
GRETZKY = {"player_id": 8447400, "first_name": "Wayne", "last_name": "Gretzky", "position_code": "C", "team_abbrev": None,
           "in_hall_of_fame": True, "headshot_url": None,
           "career_totals": {"regular_season": {"games_played": 80, "points": 215}},
           "season_history": [{"season_id": 19851986, "season_type": "regular_season", "games_played": 80,
                               "goals": 52, "assists": 163, "points": 215}]}
MCDAVID = {"player_id": 8478402, "first_name": "Connor", "last_name": "McDavid", "position_code": "C", "team_abbrev": "EDM",
           "headshot_url": None, "career_totals": {"regular_season": {"games_played": 82, "points": 153}},
           "season_history": [{"season_id": 20222023, "season_type": "regular_season", "games_played": 82,
                               "goals": 64, "assists": 89, "points": 153}]}


def test_era_points_per_game_matches_the_site():
    # 52 x 3.08/3.97 = 40.3 -> 40; 163 x 3.08/3.97 = 126.46 -> 126
    assert compare_card.era_points_per_game(GRETZKY, ERA["seasons"], ERA["reference"]) == round(166 / 80, 2)
    # and halves round up like the site's Math.round, not to even like Python's round()
    assert compare_card._round(126.5) == 127 and compare_card._round(125.5) == 126


def test_summary_rows_and_subtitles():
    g, m = compare_card.summary(GRETZKY, ERA), compare_card.summary(MCDAVID, ERA)
    assert g["subtitle"] == "Hall of Fame · 1985-86" and m["subtitle"] == "EDM · since 2022"
    assert [r[0] for r in g["rows"]] == ["Points per game", "Era-adjusted pts/game", "Career points", "Best season (points)"]
    assert g["rows"][3][2] == "215 in 85-86"


class TestRoutes:
    def setup(self, monkeypatch):
        import api
        players = {8447400: GRETZKY, 8478402: MCDAVID, 8451033: {**GRETZKY, "position_code": "G", "last_name": "Roy"}}
        monkeypatch.setattr(api, "player_detail", lambda pid: players[pid])
        monkeypatch.setattr(api, "era_scoring", lambda: ERA)

    def test_share_text_and_image(self, client, monkeypatch):
        self.setup(monkeypatch)
        body = client.get("/compare/8478402/8447400/share").json()
        assert body["title"] == "McDavid vs Gretzky: who's better?"
        assert body["description"].startswith("Points per game: McDavid 1.87, Gretzky 2.69 (era-adjusted 1.80 vs 2.08)")
        image = client.get("/og/compare/8478402-8447400.png")
        assert image.status_code == 200 and image.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_a_skater_and_a_goalie_dont_compare(self, client, monkeypatch):
        self.setup(monkeypatch)
        assert client.get("/compare/8478402/8451033/share").status_code == 400
