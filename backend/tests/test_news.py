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
