"""projected_lineups: tonight's lineups from NHL.com's projected lineups articles."""

from datetime import date

import projected_lineups as pl

ARTICLE = """## **BLUE JACKETS (3-3-0) at WILD (5-2-1)**

**Blue Jackets projected lineup**

Matthew Knies -- Adam Fantilli -- Kent Johnson

Valeri Nichushkin -- Sean Monahan -- Conor Garland

Cole Sillinger -- Charlie Coyle -- Mathieu Olivier

Ryan Lomberg -- Luca Del Bel Belluz -- Danton Heinen

Zach Werenski -- Damon Severson

Jake Christiansen -- Denton Mateychuk

Emil Andrae --Erik Gudbranson

Cam Talbot

Jet Greaves

***Scratched:** Carson Soucy, Dmitri Voronkov*

***Injured:** Dante Fabbro (broken hand), Ivan Provorov (lower body)*

**Avalanche projected lineup**

Artturi Lehkonen -- Nathan MacKinnon -- Martin Necas

Gabriel Landeskog -- Brock Nelson -- Nazem Kadri

Jaden Schwartz -- Fedor Svechkov -- T.J. Hughes

Parker Kelly -- Gavin Brindley

Devon Toews -- Cale Makar

Brett Kulak -- Sam Malinski

Josh Manson -- Brent Burns

Noah Juulsen

Mackenzie Blackwood

Scott Wedgewood

***Scratched:** None*

***Injured:** None*

**Status report**

Talbot could start after Greaves made 29 saves.
"""


def test_article_addresses_come_from_full_team_names_and_the_date():
    assert pl.article_slug("Montréal Canadiens", "St. Louis Blues", date(2026, 10, 18)) == \
        "montreal-canadiens-st-louis-blues-game-preview-october-18-2026"


def test_parses_lines_pairs_goalies_scratches_and_injuries():
    teams = pl.parse(ARTICLE)
    cbj = teams["Blue Jackets"]
    assert cbj["forwards"][0] == ["Matthew Knies", "Adam Fantilli", "Kent Johnson"]  # LW, C, RW as written
    assert len(cbj["forwards"]) == 4 and len(cbj["defense"]) == 3
    assert cbj["defense"][2] == ["Emil Andrae", "Erik Gudbranson"]  # "--" with no space after it
    assert cbj["goalies"] == ["Cam Talbot", "Jet Greaves"]  # projected starter first
    assert cbj["scratched"] == ["Carson Soucy", "Dmitri Voronkov"]
    assert cbj["injured"] == [{"name": "Dante Fabbro", "detail": "broken hand"},
                              {"name": "Ivan Provorov", "detail": "lower body"}]


def test_an_11_forward_7_defense_night():
    col = pl.parse(ARTICLE)["Avalanche"]
    assert col["forwards"][3] == ["Parker Kelly", "Gavin Brindley"]
    assert col["defense"] == [["Devon Toews", "Cale Makar"], ["Brett Kulak", "Sam Malinski"],
                              ["Josh Manson", "Brent Burns"], ["Noah Juulsen"]]
    assert col["goalies"] == ["Mackenzie Blackwood", "Scott Wedgewood"]
    assert col["scratched"] == [] and col["injured"] == []


def test_lineup_is_none_before_the_article_is_posted():
    assert pl.lineup("Columbus Blue Jackets", "Minnesota Wild", date(2026, 10, 18), get=lambda url: None) is None


def test_lineup_lists_the_away_team_first():
    story = {"contentDate": "2026-10-18T17:58:00Z", "parts": [{"type": "photo"}, {"type": "markdown", "content": ARTICLE}]}
    found = pl.lineup("Columbus Blue Jackets", "Colorado Avalanche", date(2026, 10, 18), get=lambda url: story)
    assert found["away"]["goalies"][0] == "Cam Talbot" and found["home"]["goalies"][0] == "Mackenzie Blackwood"
    assert found["url"].endswith("columbus-blue-jackets-colorado-avalanche-game-preview-october-18-2026")
