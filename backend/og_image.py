"""
Link preview images for games (1200x630 PNG, the size iMessage, Discord,
Reddit, Slack, and X expect): each team in its color with its win chance
before the game, or its score once it's live or final -- with the win
probability curve (win_probability.py) and its biggest swing when we have it.

Drawn with Pillow in Inter (assets/fonts, SIL Open Font License). Team
logos are SVG only, which Pillow can't draw, so teams are their colors and
abbreviations.
"""

import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import win_probability as wp

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
WIDTH, HEIGHT = 1200, 630
BG = (10, 11, 15)
TEXT = (232, 238, 247)
DIM = (139, 147, 163)
ACCENT = (76, 194, 255)
LIVE = (255, 77, 94)
EASTERN = ZoneInfo("America/New_York")

# Each team's main color, and for the darkest ones a second color for the
# panel's edge so it doesn't disappear into the background.
TEAM_COLORS = {
    "ANA": ("#F47A38", None), "BOS": ("#FFB81C", None), "BUF": ("#003087", "#FFB81C"), "CGY": ("#C8102E", None),
    "CAR": ("#CE1126", None), "CHI": ("#CF0A2C", None), "COL": ("#6F263D", "#236192"), "CBJ": ("#002654", "#CE1126"),
    "DAL": ("#006847", None), "DET": ("#CE1126", None), "EDM": ("#041E42", "#FF4C00"), "FLA": ("#C8102E", None),
    "LAK": ("#111111", "#A2AAAD"), "MIN": ("#154734", "#A6192E"), "MTL": ("#AF1E2D", None), "NSH": ("#FFB81C", None),
    "NJD": ("#CE1126", None), "NYI": ("#00539B", "#F47D30"), "NYR": ("#0038A8", "#CE1126"), "OTT": ("#DA1A32", None),
    "PHI": ("#F74902", None), "PIT": ("#FCB514", None), "SJS": ("#006D75", None), "SEA": ("#001628", "#99D9D9"),
    "STL": ("#002F87", "#FCB514"), "TBL": ("#002868", "#FFFFFF"), "TOR": ("#00205B", "#FFFFFF"), "UTA": ("#6CACE4", None),
    "VAN": ("#00205B", "#00843D"), "VGK": ("#B4975A", None), "WSH": ("#C8102E", None), "WPG": ("#041E42", "#AC162C"),
}


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _font(size, weight="ExtraBold"):
    return ImageFont.truetype(os.path.join(ASSETS, "fonts", f"Inter-{weight}.ttf"), size)


def _text_on(color):
    """Dark text on light team colors (Pittsburgh gold), white otherwise."""
    r, g, b = color
    return (14, 16, 22) if (0.299 * r + 0.587 * g + 0.114 * b) > 165 else (255, 255, 255)


def _background():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    glow = Image.new("RGB", (WIDTH, HEIGHT), BG)
    ImageDraw.Draw(glow).ellipse((700, -420, 1500, 300), fill=(22, 52, 74))
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(120)), 0.9)


def status_line(game):
    """'Tonight · 9:00 PM ET', 'LIVE · 2nd period', or 'Final' (with OT/SO)."""
    state = game.get("gameState")
    if state in ("FINAL", "OFF"):
        last = (game.get("gameOutcome") or {}).get("lastPeriodType")
        return f"Final{' · ' + last if last in ('OT', 'SO') else ''}"
    if state in ("LIVE", "CRIT"):
        period = (game.get("periodDescriptor") or {}).get("number")
        names = {1: "1st", 2: "2nd", 3: "3rd"}
        return f"LIVE · {names.get(period, 'OT')}" if period else "LIVE"
    start = game.get("startTimeUTC")
    if not start:
        return "Upcoming"
    local = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(EASTERN)
    today = datetime.now(EASTERN).date()
    day = "Tonight" if local.date() == today else local.strftime("%a %b %-d")
    return f"{day} · {local.strftime('%-I:%M %p')} ET"


def _panel(draw, box, team, big, small):
    main, edge = TEAM_COLORS.get(team, ("#1f2430", None))
    fill = _rgb(main)
    draw.rounded_rectangle(box, radius=36, fill=fill, outline=_rgb(edge) if edge else None, width=6 if edge else 0)
    ink = _text_on(fill)
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    draw.text((cx, y0 + 95), team, font=_font(120), fill=ink, anchor="mm")
    if big is not None:
        draw.text((cx, y0 + 225), big, font=_font(96), fill=ink, anchor="mm")
    if small:
        draw.text((cx, y1 - 32), small, font=_font(26, "Bold"), fill=ink, anchor="mm")


def _header(img, draw, game, status=None):
    icon = Image.open(os.path.join(ASSETS, "puckpulse-mark.png")).convert("RGBA").resize((98, 68))
    img.paste(icon, (60, 49), icon)
    draw.text((172, 83), "Puck", font=_font(48), fill=TEXT, anchor="lm")
    draw.text((172 + draw.textlength("Puck", font=_font(48)), 83), "Pulse", font=_font(48), fill=ACCENT, anchor="lm")
    status = status or status_line(game)
    draw.text((WIDTH - 64, 83), status, font=_font(34, "Bold"), fill=LIVE if status.startswith("LIVE") else TEXT,
              anchor="rm")


def _chart_colors(away, home):
    """Each team's color on the dark chart: the edge color for the darkest teams, and grey for
    the away team when the two would look alike (FLA and OTT are both red)."""
    def bright(team):
        main, edge = TEAM_COLORS.get(team, ("#8b93a3", None))
        return _rgb(edge or main)
    a, h = bright(away), bright(home)
    if sum((x - y) ** 2 for x, y in zip(a, h)) < 90 ** 2:
        a = DIM
    return a, h


def _swing_line(curve, away, home, arrow="→"):
    swing = curve.get("swing")
    if not swing:
        return None
    team = home if swing["team"] == "home" else away
    before, after = (swing["before"], swing["after"]) if swing["team"] == "home" else (1 - swing["before"], 1 - swing["after"])
    who = swing.get("scorer") or team
    return f"Biggest swing: {who} ({team}), {wp.clock_label(swing['second'], curve.get('playoff', False))} · " \
           f"{team} {round(before * 100)}% {arrow} {round(after * 100)}%"


def _render_curve(img, draw, game, curve, footer=None, highlight=None):
    """Score across the top, the win probability curve below it, the biggest swing at the bottom."""
    away, home = game["awayTeam"], game["homeTeam"]
    a_color, h_color = _chart_colors(away["abbrev"], home["abbrev"])
    for x, team, color, anchor in ((64, away, a_color, "lm"), (WIDTH - 64, home, h_color, "rm")):
        draw.text((x, 180), team["abbrev"], font=_font(76), fill=color, anchor=anchor)
    score = f"{away.get('score', 0)}  –  {home.get('score', 0)}"
    draw.text((WIDTH // 2, 180), score, font=_font(92), fill=TEXT, anchor="mm")

    left, right, top, bottom = 150, WIDTH - 64, 250, 520
    points = curve["points"]
    end = max(wp.REGULATION_SECONDS, points[-1][0])
    x = lambda s: left + (right - left) * s / end
    y = lambda p: top + (bottom - top) * (1 - p)
    mid = y(0.5)
    for s in (1200, 2400) + ((wp.REGULATION_SECONDS,) if end > wp.REGULATION_SECONDS else ()):
        draw.line((x(s), top, x(s), bottom), fill=(33, 37, 47), width=2)
    draw.line((left, mid, right, mid), fill=(46, 52, 66), width=2)
    draw.text((left - 18, top + 14), home["abbrev"], font=_font(28, "Bold"), fill=h_color, anchor="rm")
    draw.text((left - 18, bottom - 14), away["abbrev"], font=_font(28, "Bold"), fill=a_color, anchor="rm")

    line = [(x(s), y(p)) for s, p in points]
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).polygon(line + [(line[-1][0], mid), (line[0][0], mid)], fill=(255, 255, 255, 255))
    for color, box in ((h_color, (0, 0, WIDTH, int(mid))), (a_color, (0, int(mid), WIDTH, HEIGHT))):
        layer = Image.new("RGBA", img.size, (*color, 0))
        mask = Image.new("L", img.size, 0)
        mask.paste(shade.getchannel("A").crop(box), box[:2])
        layer.putalpha(mask.point(lambda v: v * 70 // 255))
        img.paste(layer, (0, 0), layer)
    draw.line(line, fill=TEXT, width=5, joint="curve")
    for g in curve.get("goals", []):
        cx, cy = x(g["second"]), y(g["after"])
        r = 16 if highlight and g["second"] == highlight["second"] and g["team"] == highlight["side"] else 10
        if r > 10:  # the moment the card is about: a ring around its dot
            draw.ellipse((cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8), outline=TEXT, width=3)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=h_color if g["team"] == "home" else a_color,
                     outline=BG, width=3)

    # "to", not an arrow: the bundled Inter has no arrow glyph.
    footer = footer or _swing_line(curve, away["abbrev"], home["abbrev"], "to") or "Win probability by PuckPulse"
    draw.text((64, 580), footer, font=_font(28, "Bold"), fill=DIM, anchor="lm")


def render_game(game, home_win_prob=None, curve=None):
    """
    PNG bytes for a game: game is the NHL box score/landing dict; curve is
    /games/{id}/win-probability's result, drawn once the game is on.
    """
    img = _background()
    draw = ImageDraw.Draw(img)
    _header(img, draw, game)

    away, home = game["awayTeam"], game["homeTeam"]
    started = game.get("gameState") in ("FINAL", "OFF", "LIVE", "CRIT")
    if started and curve and curve.get("available") and curve.get("points"):
        _render_curve(img, draw, game, curve)
    else:
        if started:
            big = (str(away.get("score", 0)), str(home.get("score", 0)))
            small = (None, None)
            footer = "Scores, box score, and highlights at puckpulse.io"
        elif home_win_prob is not None:
            big = (f"{round((1 - home_win_prob) * 100)}%", f"{round(home_win_prob * 100)}%")
            small = ("to win", "to win")
            footer = "Win chances by PuckPulse · preview, lines, and goalies at puckpulse.io"
        else:
            big, small = (None, None), (None, None)
            footer = "Preview, lines, and goalies at puckpulse.io"
        _panel(draw, (64, 160, 544, 500), away["abbrev"], big[0], small[0])
        _panel(draw, (656, 160, 1136, 500), home["abbrev"], big[1], small[1])
        draw.text((WIDTH // 2, 330), "@", font=_font(64), fill=DIM, anchor="mm")
        draw.text((64, 562), footer, font=_font(28, "Bold"), fill=DIM, anchor="lm")

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def render_swing(swing, headline):
    """
    Swing of the Night's card: the game's score and win-probability curve
    with the moment ringed, "SWING OF THE NIGHT · Oct 20" up top and what
    happened along the bottom. swing is api._swing_of_the_night()'s result.
    """
    game = {"gameState": "OFF",
            "awayTeam": {"abbrev": swing["game"]["away"], "score": swing["game"]["away_score"]},
            "homeTeam": {"abbrev": swing["game"]["home"], "score": swing["game"]["home_score"]}}
    goal = swing["goal"]
    day = datetime.fromisoformat(swing["date"])
    img = _background()
    draw = ImageDraw.Draw(img)
    _header(img, draw, game, status=f"SWING OF THE NIGHT · {day.strftime('%b %-d')}")
    footer = f"{headline} · {goal['team']} {round(goal['before'] * 100)}% to {round(goal['after'] * 100)}%"
    _render_curve(img, draw, game, {"points": swing["points"], "goals": swing["goals"], "playoff": swing["playoff"]},
                  footer=footer, highlight=goal)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


GOOD = (52, 211, 153)


def _headshot(url, size, get=None):
    """A player's NHL headshot as a round RGBA image, or None (no URL, or the fetch failed)."""
    if not url:
        return None
    import requests

    try:
        response = (get or requests.get)(url, timeout=6)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert("RGBA").resize((size, size))
    except Exception:  # noqa: BLE001 -- a missing face shouldn't cost the card
        return None
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    img.putalpha(mask)
    return img


def render_compare(a, b, get=None):
    """
    A "Player vs Player" card: both players (headshot, name, team or era),
    then compare_card.summary()'s rows side by side, the better number of
    each in green. a, b: compare_card.summary() results.
    """
    img = _background()
    draw = ImageDraw.Draw(img)
    _header(img, draw, {}, status="PLAYER COMPARISON")
    for x, p, anchor in ((300, a, "mm"), (900, b, "mm")):
        face = _headshot(p.get("headshot"), 120, get)
        if face:
            img.paste(face, (x - 60, 128), face)
        else:
            draw.ellipse((x - 60, 128, x + 60, 248), fill=(33, 37, 47))
            draw.text((x, 188), p["last"][:1], font=_font(60), fill=DIM, anchor="mm")
        name_font = _font(44 if len(p["name"]) <= 18 else 36)
        draw.text((x, 282), p["name"], font=name_font, fill=TEXT, anchor=anchor)
        draw.text((x, 322), p["subtitle"], font=_font(24, "Bold"), fill=DIM, anchor=anchor)
    draw.text((WIDTH // 2, 200), "vs", font=_font(44), fill=DIM, anchor="mm")
    y = 372
    for (label, va, sa, high), (_, vb, sb, _) in zip(a["rows"], b["rows"]):
        better = None if va is None or vb is None or va == vb else ("a" if (va > vb) == high else "b")
        draw.line((64, y - 6, WIDTH - 64, y - 6), fill=(33, 37, 47), width=2)
        draw.text((300, y + 24), sa, font=_font(36), fill=GOOD if better == "a" else TEXT, anchor="mm")
        draw.text((WIDTH // 2, y + 24), label, font=_font(22, "Bold"), fill=DIM, anchor="mm")
        draw.text((900, y + 24), sb, font=_font(36), fill=GOOD if better == "b" else TEXT, anchor="mm")
        y += 58
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _season_label(season_id):
    s = str(season_id)
    return f"{s[:4]}-{s[6:]}"


def render_time_machine(tm, target_label, get=None):
    """
    A time machine card: the player, "his 1985-86 in today's game", the
    simulated points (median, likely range) beside the histogram with the
    likely range lit, and his real season underneath. tm: time_machine.run()'s
    result; target_label: "today's game" or "1985-86".
    """
    img = _background()
    draw = ImageDraw.Draw(img)
    _header(img, draw, {}, status="TIME MACHINE")
    player, source = tm["player"], tm["source"]
    face = _headshot(player.get("headshot"), 104, get)
    if face:
        img.paste(face, (64, 146), face)
    else:
        draw.ellipse((64, 146, 168, 250), fill=(33, 37, 47))
        draw.text((116, 198), player["name"].split()[-1][:1], font=_font(52), fill=DIM, anchor="mm")
    name_font = _font(46 if len(player["name"]) <= 18 else 38)
    draw.text((192, 184), player["name"], font=name_font, fill=TEXT, anchor="lm")
    draw.text((192, 228), f"His {_season_label(source['season_id'])} in {target_label}", font=_font(26, "Bold"),
              fill=ACCENT, anchor="lm")

    points = tm["points"]
    median = f"~{points['median']}"
    draw.text((64, 380), median, font=_font(128), fill=TEXT, anchor="ls")
    draw.text((76 + draw.textlength(median, font=_font(128)), 380), "points", font=_font(36, "Bold"), fill=DIM, anchor="ls")
    draw.text((64, 428), f"likely {points['low']}\u2013{points['high']} over 82 games", font=_font(30, "Bold"), fill=TEXT,
              anchor="ls")
    draw.text((64, 470), f"{tm['goals']['median']} goals, {tm['assists']['median']} assists", font=_font(26, "Bold"),
              fill=DIM, anchor="ls")

    # The histogram: every bar a slice of the 10,000 seasons; the likely range lit.
    bins, width = tm["histogram"], tm["bin_width"]
    left, right, top, bottom = 640, WIDTH - 64, 170, 440
    tallest = max(n for _, n in bins)
    step = (right - left) / len(bins)
    for i, (start, n) in enumerate(bins):
        h = max(3, (n / tallest) * (bottom - top))
        lit = start + width > points["low"] and start <= points["high"]
        x0 = left + i * step + 2
        draw.rounded_rectangle((x0, bottom - h, x0 + step - 4, bottom), radius=3, fill=ACCENT if lit else (44, 50, 64))
    draw.text((left, bottom + 30), str(bins[0][0]), font=_font(22, "Bold"), fill=DIM, anchor="ls")
    draw.text((right, bottom + 30), str(bins[-1][0] + width - 1), font=_font(22, "Bold"), fill=DIM, anchor="rs")
    draw.text(((left + right) / 2, bottom + 30), "points in 10,000 simulated seasons", font=_font(22, "Bold"), fill=DIM,
              anchor="ms")

    draw.line((64, 530, WIDTH - 64, 530), fill=(33, 37, 47), width=2)
    real = (f"His real {_season_label(source['season_id'])}: {source['points']} points in {source['games_played']} games, "
            f"when teams scored {source['scoring']:.2f} a game")
    draw.text((64, 578), real, font=_font(26, "Bold"), fill=DIM, anchor="ls")
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def share_text(game, home_win_prob=None, curve=None):
    """(title, description) for a game's link preview; curve adds its biggest swing once the game is on."""
    away, home = game["awayTeam"]["abbrev"], game["homeTeam"]["abbrev"]
    status = status_line(game)
    state = game.get("gameState")
    if state in ("FINAL", "OFF", "LIVE", "CRIT"):
        a, h = game["awayTeam"].get("score", 0), game["homeTeam"].get("score", 0)
        title = f"{away} {a} @ {home} {h} · {status}"
        verb = "Follow along" if status.startswith("LIVE") else "Box score and highlights"
        swing = _swing_line(curve, away, home) if curve and curve.get("available") else None
        return title, f"{swing}. {verb} on PuckPulse." if swing else f"{verb} on PuckPulse."
    title = f"{away} @ {home} · {status}"
    if home_win_prob is None:
        return title, "Preview, projected lines, and goalies on PuckPulse."
    fav, pct = (home, home_win_prob) if home_win_prob >= 0.5 else (away, 1 - home_win_prob)
    return title, f"PuckPulse gives {fav} a {round(pct * 100)}% chance to win. Preview, projected lines, and goalies."


def team_share_text(abbrev, team, playoff_pct=None):
    """(title, description) for a team's link preview. playoff_pct is the stored 0-1 fraction."""
    name = (team or {}).get("team_name") or abbrev
    wins, losses, otl = (team or {}).get("wins"), (team or {}).get("losses"), (team or {}).get("ot_losses")
    record = f"{wins}-{losses}-{otl or 0}" if wins is not None and losses is not None else None
    if playoff_pct is not None:
        pct = playoff_pct * 100
        shown = "<1" if 0 < pct < 1 else (">99" if 99 < pct < 100 else f"{pct:.1f}".rstrip("0").rstrip("."))
        title = f"{name}: {shown}% to make the playoffs"
    else:
        title = f"{name} on PuckPulse"
    parts = [f"{record}, {team['points']} pts." if record and team.get("points") is not None else None,
             "Playoff odds, schedule, roster, and stats on PuckPulse."]
    return title, " ".join(p for p in parts if p)
