"""og_image: link preview images and text for games."""

import io

from PIL import Image

import og_image as og

PRE = {"gameState": "FUT", "startTimeUTC": "2026-10-19T00:00:00Z", "awayTeam": {"abbrev": "PIT"}, "homeTeam": {"abbrev": "COL"}}
FINAL = {"gameState": "OFF", "gameOutcome": {"lastPeriodType": "OT"},
         "awayTeam": {"abbrev": "SEA", "score": 3}, "homeTeam": {"abbrev": "TBL", "score": 4}}


def test_renders_a_1200x630_png_for_every_team():
    for team in og.TEAM_COLORS:
        png = og.render_game({**PRE, "homeTeam": {"abbrev": team}}, 0.5)
        assert Image.open(io.BytesIO(png)).size == (1200, 630)
    assert Image.open(io.BytesIO(og.render_game(FINAL))).format == "PNG"


def test_status_lines():
    assert og.status_line(FINAL) == "Final · OT"
    assert og.status_line({"gameState": "LIVE", "periodDescriptor": {"number": 2}}) == "LIVE · 2nd"
    assert og.status_line(PRE).endswith("PM ET")


def test_share_text_names_the_favorite_before_and_the_score_after():
    title, description = og.share_text(PRE, 0.663)
    assert title.startswith("PIT @ COL · ")
    assert description.startswith("PuckPulse gives COL a 66% chance to win")
    title, description = og.share_text(FINAL)
    assert title == "SEA 3 @ TBL 4 · Final · OT" and "Box score" in description
    assert og.share_text(PRE)[1].startswith("Preview")


def test_game_share_text_has_no_betting_wording():
    # Link previews land in subreddits and group chats that don't like betting promos;
    # the in-app Bets tab keeps its wording.
    for game, prob in ((PRE, 0.663), (PRE, None), (FINAL, None)):
        for text in og.share_text(game, prob):
            assert "odds" not in text.lower() and "bet" not in text.lower()


def test_light_team_colors_get_dark_text():
    assert og._text_on(og._rgb("#FCB514")) != (255, 255, 255)  # Pittsburgh gold
    assert og._text_on(og._rgb("#002654")) == (255, 255, 255)


def test_team_share_text_leads_with_playoff_odds_and_record():
    team = {"team_name": "Buffalo Sabres", "wins": 3, "losses": 3, "ot_losses": 0, "points": 6}
    title, description = og.team_share_text("BUF", team, 0.177)
    assert title == "Buffalo Sabres: 17.7% to make the playoffs"
    assert description.startswith("3-3-0, 6 pts.")
    assert og.team_share_text("BUF", team, 0.004)[0].endswith("<1% to make the playoffs")
    assert og.team_share_text("BUF", team, 1.0)[0].endswith("100% to make the playoffs")
    title, description = og.team_share_text("BUF", {"team_name": "Buffalo Sabres"})
    assert title == "Buffalo Sabres on PuckPulse" and description.startswith("Playoff odds")
    for text in (title, description):
        assert "bet" not in text.lower()


CURVE = {"available": True, "playoff": False,
         "points": [[0, 0.55], [600, 0.54], [600, 0.33], [3600, 0.4], [3733, 0.0]],
         "goals": [{"second": 600, "team": "away", "scorer": "M. Celebrini", "before": 0.54, "after": 0.33},
                   {"second": 3733, "team": "away", "scorer": "M. Celebrini", "before": 0.4, "after": 0.0}],
         "swing": {"second": 3733, "team": "away", "scorer": "M. Celebrini", "before": 0.4, "after": 0.0}}


def test_draws_the_win_probability_curve_once_the_game_is_on():
    png = og.render_game(FINAL, 0.5, CURVE)
    assert Image.open(io.BytesIO(png)).size == (1200, 630)
    assert png != og.render_game(FINAL, 0.5)
    assert og.render_game(PRE, 0.5, CURVE) == og.render_game(PRE, 0.5)  # not before puck drop
    assert og.render_game(FINAL, 0.5, {"available": False}) == og.render_game(FINAL, 0.5)


def test_share_text_names_the_biggest_swing():
    _, description = og.share_text(FINAL, 0.5, CURVE)
    assert description == "Biggest swing: M. Celebrini (SEA), OT 2:13 · SEA 60% → 100%. Box score and highlights on PuckPulse."


def test_teams_that_look_alike_get_told_apart():
    assert og._chart_colors("FLA", "OTT")[0] == og.DIM
    assert og._chart_colors("SJS", "MTL") == (og._rgb("#006D75"), og._rgb("#AF1E2D"))
    assert og._chart_colors("TOR", "BOS")[0] == (255, 255, 255)  # navy is too dark: its edge color
