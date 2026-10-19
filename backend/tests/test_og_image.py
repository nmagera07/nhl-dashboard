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


def test_light_team_colors_get_dark_text():
    assert og._text_on(og._rgb("#FCB514")) != (255, 255, 255)  # Pittsburgh gold
    assert og._text_on(og._rgb("#002654")) == (255, 255, 255)
