"""news.py: parsing each source, merging headlines, and the /news, /injuries, /transactions endpoints."""

from datetime import datetime, timezone

import pytest

import api
import news

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)

NHL_STORIES = {"items": [
    {"headline": "Kraken edge Capitals", "slug": "kraken-capitals-recap", "contentDate": "2026-10-12T01:21:00Z",
     "summary": "WASHINGTON -- Jared\xa0McCann broke a tie.", "tags": [{"slug": "teamid-55"}, {"slug": "teamid-15"}, {"slug": "news"}]},
    {"headline": "Mammoth win", "slug": "mammoth-win", "contentDate": "2026-10-11T01:00:00Z", "summary": "", "tags": [{"slug": "teamid-68"}]},
    {"headline": None, "slug": "broken"},
]}

ESPN_RSS = """<rss><channel>
<item><title>Blackhawks captain Bedard on brink of return</title><link>https://www.espn.com/nhl/story/_/id/1/bedard</link>
<pubDate>Sun, 11 Oct 2026 18:02:37 EST</pubDate><description><![CDATA[<p>Connor Bedard could play Tuesday.</p>]]></description></item>
<item><title>A wild finish in a game nobody saw</title><link>https://www.espn.com/nhl/story/_/id/2/x</link><pubDate>Sun, 11 Oct 2026 10:00:00 EST</pubDate></item>
</channel></rss>"""

SPORTSNET_RSS = """<rss><channel>
<item><title>NHL Featured</title><link>https://www.sportsnet.ca/?sn-collection=nhl</link><pubDate>Mon, 07 Jul 2025 12:34:34 EDT</pubDate></item>
<item><title>Canadiens fans chant for Red Wings star Larkin</title><link>https://www.sportsnet.ca/nhl/article/we-want-larkin</link>
<pubDate>Sun, 11 Oct 2026 00:27:01 EDT</pubDate></item>
</channel></rss>"""


class TestParsing:
    def test_nhl_stories_use_team_ids_and_build_the_nhl_com_link(self):
        stories = news.parse_nhl_stories(NHL_STORIES)

        assert [s["title"] for s in stories] == ["Kraken edge Capitals", "Mammoth win"]
        assert stories[0]["url"] == "https://www.nhl.com/news/kraken-capitals-recap"
        assert stories[0]["teams"] == ["SEA", "WSH"] and stories[1]["teams"] == ["UTA"]
        assert stories[0]["summary"] == "WASHINGTON -- Jared McCann broke a tie."

    def test_rss_items_get_utc_times_plain_summaries_and_team_tags(self):
        espn = news.parse_rss(ESPN_RSS, "ESPN")

        assert espn[0]["published"] == "2026-10-11T23:02:37Z"
        assert espn[0]["summary"] == "Connor Bedard could play Tuesday." and espn[0]["teams"] == ["CHI"]
        assert espn[1]["teams"] == []  # "a wild finish" isn't the Minnesota Wild

    def test_espn_news_skips_videos_and_paywalled_stories_and_uses_its_team_tags(self):
        data = {"articles": [
            {"headline": "Rangers lean on Garand", "published": "2026-10-12T01:24:57Z", "type": "HeadlineNews",
             "description": "Two days after losing Shesterkin.", "links": {"web": {"href": "https://www.espn.com/nhl/story/_/id/1/x"}},
             "categories": [{"type": "team", "description": "New York Rangers"}, {"type": "league", "description": "NHL"}]},
            {"headline": "Highlights", "published": "2026-10-12T00:54:12Z", "type": "Media", "links": {"web": {"href": "https://x"}}},
            {"headline": "ESPN+ insider piece", "published": "2026-10-12T00:00:00Z", "type": "Story", "premium": True,
             "links": {"web": {"href": "https://y"}}},
            {"headline": "Kraken recap", "published": "2026-10-12T00:09:42Z", "type": "Recap",
             "links": {"web": {"href": "http://www.espn.com/nhl/recap?gameId=1"}}, "categories": []},
        ]}

        items = news.parse_espn_news(data)

        assert [i["title"] for i in items] == ["Rangers lean on Garand", "Kraken recap"]
        assert items[0]["teams"] == ["NYR"] and items[1]["teams"] == ["SEA"]  # from the title when untagged
        assert items[1]["url"].startswith("https://")

    def test_summaries_lose_markup_artifacts(self):
        assert news._clean_summary("A look at the game. \\+ In 5-on-5 play,   it was\xa0close.") == "A look at the game. In 5-on-5 play, it was close."

    def test_sportsnet_keeps_articles_only_and_matches_two_word_nicknames(self):
        items = news.parse_rss(SPORTSNET_RSS, "Sportsnet", link_must_contain="/nhl/article/")

        assert [i["title"] for i in items] == ["Canadiens fans chant for Red Wings star Larkin"]
        assert items[0]["teams"] == ["DET", "MTL"]

    def test_team_names_match_with_or_without_accents(self):
        assert news.team_from_name("Montreal Canadiens") == "MTL" == news.team_from_name("Montréal Canadiens")
        assert news.teams_mentioned("Maple Leafs top Golden Knights") == ["TOR", "VGK"]


class TestMerge:
    def test_newest_first_last_week_only_and_no_duplicate_titles(self):
        a = [{"title": "Big Trade!", "url": "https://a", "published": "2026-10-12T10:00:00Z"}, {"title": "Old news", "url": "https://b", "published": "2026-09-01T00:00:00Z"}]
        b = [{"title": "big trade", "url": "https://c", "published": "2026-10-12T09:00:00Z"}, {"title": "Newer", "url": "https://d", "published": "2026-10-12T11:00:00Z"}]

        assert [i["title"] for i in news.merge_headlines([a, b, None], now=NOW)] == ["Newer", "Big Trade!"]


    def test_one_recap_per_game_across_outlets_but_different_angles_stay(self):
        items = [[
            {"title": "Kraken overcome Ovechkin’s first goal of season, edge Capitals", "url": "https://e", "published": "2026-10-12T01:21:00Z"},
            {"title": "Kraken overcome Alex Ovechkin's first goal of the season to beat the Capitals 5-3", "url": "https://e", "published": "2026-10-12T00:09:00Z"},
            {"title": "Kraken overcome Alex Ovechkin’s first goal of season to beat Capitals", "url": "https://e", "published": "2026-10-12T00:07:00Z"},
            {"title": "Garand makes 19 saves, Rangers defeat Canucks", "url": "https://e", "published": "2026-10-12T00:47:00Z"},
            {"title": "Without Shesterkin, Rangers lean on Garand in win", "url": "https://e", "published": "2026-10-12T01:24:00Z"},
        ]]
        titles = [i["title"] for i in news.merge_headlines(items, now=NOW)]
        assert titles == ["Without Shesterkin, Rangers lean on Garand in win", "Kraken overcome Ovechkin’s first goal of season, edge Capitals",
                          "Garand makes 19 saves, Rangers defeat Canucks"]


    def test_only_https_links_get_through(self):
        items = [[{"title": "Fine", "url": "https://x.test/a", "published": "2026-10-12T10:00:00Z"},
                  {"title": "Sneaky", "url": "javascript:alert(1)", "published": "2026-10-12T11:00:00Z"},
                  {"title": "Plain", "url": "http://x.test/b", "published": "2026-10-12T11:30:00Z"}]]
        assert [i["title"] for i in news.merge_headlines(items, now=NOW)] == ["Fine"]


class TestInjuriesAndTransactions:
    def test_injuries_by_team_worst_first_without_internal_codes(self):
        data = {"injuries": [{"displayName": "Pittsburgh Penguins", "injuries": [
            {"athlete": {"displayName": "B Player", "position": {"abbreviation": "RW"}}, "status": "Day-To-Day",
             "details": {"type": "Upper Body"}, "shortComment": "B Player left the game early.", "date": "2026-10-11T05:00Z"},
            {"athlete": {"displayName": "A Player", "position": {"abbreviation": "LW"}}, "status": "Injured Reserve",
             "details": {"type": "Personal", "returnDate": "2026-10-16"}, "shortComment": "ir-nr"},
        ]}, {"displayName": "Not A Team", "injuries": []}]}

        by_team = news.parse_injuries(data)

        assert list(by_team) == ["PIT"]
        assert [r["player"] for r in by_team["PIT"]] == ["A Player", "B Player"]
        assert by_team["PIT"][0]["note"] is None and by_team["PIT"][0]["expected_return"] == "2026-10-16"

    def test_transactions_map_espn_teams_to_ours(self):
        data = {"transactions": [{"date": "2026-10-11T07:00Z", "team": {"displayName": "New Jersey Devils"}, "description": "Recalled F X."}]}
        assert news.parse_transactions(data) == [{"date": "2026-10-11", "team": "NJD", "description": "Recalled F X."}]


class TestCache:
    def test_a_failed_refresh_serves_the_last_good_copy_then_gives_up(self, monkeypatch):
        news.clear_cache()
        clock = [0.0]
        monkeypatch.setattr(news, "_now", lambda: clock[0])

        assert news._cached("s", 60, lambda: "fresh") == "fresh"
        clock[0] = 120

        def down():
            raise ConnectionError("source down")

        assert news._cached("s", 60, down) == "fresh"
        clock[0] = news.MAX_STALE_SECONDS + 200
        assert news._cached("s", 60, down) is None
        news.clear_cache()


class TestEndpoints:
    @pytest.fixture(autouse=True)
    def offline_sources(self, monkeypatch):
        news.clear_cache()
        monkeypatch.setattr(news, "SOURCES", {"NHL.com": lambda: news.parse_nhl_stories(NHL_STORIES), "ESPN": lambda: [],
                                              "Sportsnet": lambda: (_ for _ in ()).throw(ConnectionError("down"))})
        monkeypatch.setattr(news, "MAX_HEADLINE_AGE", news.timedelta(days=3650))
        yield
        news.clear_cache()

    def test_news_lists_the_sources_that_answered(self, client):
        body = client.get("/news?limit=5").json()

        assert body["sources"] == ["ESPN", "NHL.com"]  # Sportsnet failed on its own
        assert body["headlines"][0]["title"] == "Kraken edge Capitals"

    def test_news_filters_by_team(self, client):
        assert [h["title"] for h in client.get("/news?team=uta").json()["headlines"]] == ["Mammoth win"]

    def test_unknown_team_is_a_404(self, client):
        assert client.get("/news?team=XYZ").status_code == 404

    def test_all_sources_down_is_a_503(self, client, monkeypatch):
        monkeypatch.setattr(news, "SOURCES", {"ESPN": lambda: (_ for _ in ()).throw(ConnectionError("down"))})
        assert client.get("/news").status_code == 503

    def test_injuries_for_one_team(self, client, monkeypatch):
        monkeypatch.setattr(news, "_get", lambda url: type("R", (), {"json": lambda self: {"injuries": [
            {"displayName": "Pittsburgh Penguins", "injuries": []}]}})())
        assert client.get("/injuries?team=PIT").json() == {"source": "ESPN", "teams": {"PIT": []}}
        assert api._daily_cacheable("/injuries")


def test_stories_carry_their_photo_in_two_sizes():
    import news
    story = {"items": [{"slug": "x", "headline": "H", "contentDate": "2026-10-20T12:00:00Z", "tags": [],
                        "thumbnail": {"templateUrl": "https://media.d3.nhle.com/image/private/{formatInstructions}/prd/abc"}}]}
    (item,) = news.parse_nhl_stories(story)
    assert item["image"].endswith("/t_ratio16_9-size40/prd/abc") and item["thumb"].endswith("/t_ratio16_9-size20/prd/abc")
    (bare,) = news.parse_nhl_stories({"items": [{**story["items"][0], "thumbnail": {"templateUrl": "https://evil.example/{formatInstructions}"}}]})
    assert "image" not in bare  # only the NHL's own image host


def test_feed_text_is_unescaped_even_when_double_encoded():
    import news
    rss = """<rss><channel><item><title>Tkachuk isn&amp;#8217;t ready</title>
    <link>https://www.sportsnet.ca/nhl/article/x</link><pubDate>Tue, 20 Oct 2026 12:00:00 GMT</pubDate>
    <description>It&amp;#8217;s &amp;amp; more</description></item></channel></rss>"""
    (item,) = news.parse_rss(rss, "Sportsnet")
    assert item["title"] == "Tkachuk isn’t ready" and item["summary"] == "It’s & more"


ROTOWIRE_RSS = """<rss><channel>
<item><guid>nhl1</guid><title>Jesper Wallstedt: Slated to face Oilers</title>
<link>https://www.rotowire.com//hockey/player/jesper-wallstedt-6464</link>
<description>Wallstedt is expected to guard the road crease Tuesday.

        Visit RotoWire.com for more analysis on this update.</description>
<pubDate>Tue, 20 Oct 2026 11:42:00 AM PDT</pubDate></item>
<item><guid>nhl2</guid><title>No colon here</title><link>https://www.rotowire.com/x</link><pubDate>Tue, 20 Oct 2026 11:40:00 AM PDT</pubDate></item>
<item><guid>nhl3</guid><title>T.J. Brodie: Back in lineup</title><link>https://www.rotowire.com/y</link><pubDate>Mon, 19 Oct 2026 07:05:00 PM EDT</pubDate></item>
</channel></rss>"""


def _rotowire(text):
    return lambda url: type("R", (), {"text": text})()


class TestFantasy:
    @pytest.fixture(autouse=True)
    def offline(self, monkeypatch):
        news.clear_cache()
        news._updates.clear()
        monkeypatch.setattr(news, "_get", _rotowire(ROTOWIRE_RSS))
        monkeypatch.setattr(news, "FANTASY_SOURCES", {"DobberHockey": lambda: [], "RotoBaller": lambda: []})
        yield
        news._updates.clear()

    def test_parses_player_updates_and_their_non_standard_dates(self):
        updates = news.parse_rotowire(ROTOWIRE_RSS)
        assert [u["player"] for u in updates] == ["Jesper Wallstedt", "T.J. Brodie"]
        first = updates[0]
        assert first["title"] == "Slated to face Oilers" and first["published"] == "2026-10-20T18:42:00Z"
        assert first["summary"] == "Wallstedt is expected to guard the road crease Tuesday."
        assert first["url"] == "https://www.rotowire.com/hockey/player/jesper-wallstedt-6464"
        assert updates[1]["published"] == "2026-10-19T23:05:00Z"

    def test_polling_keeps_a_running_list_and_drops_old_updates(self, monkeypatch):
        assert news.poll_fantasy_updates(now=datetime(2026, 10, 21, tzinfo=timezone.utc)) == 2
        assert news.poll_fantasy_updates(now=datetime(2026, 10, 21, tzinfo=timezone.utc)) == 0
        later = ROTOWIRE_RSS.replace("nhl1", "nhl9").replace("Slated to face Oilers", "Starting Thursday")
        monkeypatch.setattr(news, "_get", _rotowire(later))
        news.poll_fantasy_updates(now=datetime(2026, 10, 21, tzinfo=timezone.utc))
        assert len(news._updates) == 3  # the feed moved on; the old update stays
        news.poll_fantasy_updates(now=datetime(2026, 10, 23, 12, tzinfo=timezone.utc))
        assert set(news._updates) == {"nhl1", "nhl9"}  # Brodie's is more than 3 days old

    def test_a_failed_poll_keeps_what_we_have(self, monkeypatch):
        news.poll_fantasy_updates(now=datetime(2026, 10, 21, tzinfo=timezone.utc))
        monkeypatch.setattr(news, "_get", lambda url: (_ for _ in ()).throw(ConnectionError("down")))
        assert news.poll_fantasy_updates() is None and len(news._updates) == 2

    def test_player_keys_match_across_spellings(self):
        assert news.player_key("T.J. Brodie") == news.player_key("TJ Brodie") == "tj brodie"
        assert news.player_key("Juraj Slafkovský") == "juraj slafkovsky"

    def test_endpoint_tags_each_update_with_the_players_team(self, client, db_router, monkeypatch):
        monkeypatch.setattr(news, "MAX_UPDATE_AGE", news.timedelta(days=3650))
        db_router.when("from players", [{"first_name": "Jesper", "last_name": "Wallstedt", "team_abbrev": "MIN", "position_code": "G"},
                                        {"first_name": "TJ", "last_name": "Brodie", "team_abbrev": "CHI", "position_code": "D"},
                                        {"first_name": "TJ", "last_name": "Brodie", "team_abbrev": "TOR", "position_code": "D"}])
        body = client.get("/fantasy").json()
        assert [(u["player"], u["team"]) for u in body["updates"]] == [("Jesper Wallstedt", "MIN"), ("T.J. Brodie", None)]
        assert body["sources"] == ["RotoWire", "DobberHockey", "RotoBaller"]

    def test_endpoint_503s_when_every_source_is_down(self, client, monkeypatch):
        monkeypatch.setattr(news, "_get", lambda url: (_ for _ in ()).throw(ConnectionError("down")))
        monkeypatch.setattr(news, "FANTASY_SOURCES", {"DobberHockey": lambda: news._get("x")})
        assert client.get("/fantasy").status_code == 503


class TestGoalieReports:
    GOALIES = {"Jesper Wallstedt": "MIN", "Devon Levi": "EDM", "Carter Hart": "VGK"}

    @pytest.fixture(autouse=True)
    def updates(self, monkeypatch):
        rows = [
            ("1", "Jesper Wallstedt", "Wallstedt is expected to guard the road crease Tuesday.", "2026-10-20T15:00:00Z"),
            ("2", "Devon Levi", "Levi will patrol the home crease against Minnesota on Tuesday.", "2026-10-20T16:00:00Z"),
            ("3", "Carter Hart", "Hart will start Tuesday's home matchup.", "2026-10-20T14:00:00Z"),
            ("4", "Carter Hart", "Hart will get the night off Tuesday after all.", "2026-10-20T17:00:00Z"),
            ("5", "Connor McDavid", "McDavid will start on the top line.", "2026-10-20T16:30:00Z"),
            ("6", "Devon Levi", "Levi stopped 30 of 32 shots in Monday's win.", "2026-10-20T03:30:00Z"),  # 11:30 PM Monday ET
            ("7", "Jesper Wallstedt", "Wallstedt will start Wednesday.", "2026-10-21T15:00:00Z"),
        ]
        monkeypatch.setattr(news, "_updates", {i: {"id": i, "player": p, "title": "", "summary": text, "published": when,
                                                   "url": f"https://rw.test/{i}", "source": "RotoWire"} for i, p, text, when in rows})

    def test_each_teams_latest_report_on_the_day(self):
        from datetime import date
        reports = news.goalie_reports(date(2026, 10, 20), self.GOALIES.get)
        assert {t: (r["name"], r["status"]) for t, r in reports.items()} == {
            "MIN": ("Jesper Wallstedt", "expected"), "EDM": ("Devon Levi", "confirmed")}  # Hart scratched late; McDavid isn't a goalie

    def test_the_day_is_eastern(self):
        from datetime import date
        assert news.goalie_reports(date(2026, 10, 19), self.GOALIES.get) == {}  # the 11:30 PM recap isn't a start
        assert news.goalie_reports(date(2026, 10, 21), self.GOALIES.get)["MIN"]["status"] == "confirmed"
