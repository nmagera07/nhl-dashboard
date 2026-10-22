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


def _header(img, draw, game):
    icon = Image.open(os.path.join(ASSETS, "puckpulse-mark.png")).convert("RGBA").resize((98, 68))
    img.paste(icon, (60, 49), icon)
    draw.text((172, 83), "Puck", font=_font(48), fill=TEXT, anchor="lm")
    draw.text((172 + draw.textlength("Puck", font=_font(48)), 83), "Pulse", font=_font(48), fill=ACCENT, anchor="lm")
    status = status_line(game)
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


def _render_curve(img, draw, game, curve):
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
        draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=h_color if g["team"] == "home" else a_color,
                     outline=BG, width=3)

    # "to", not an arrow: the bundled Inter has no arrow glyph.
    footer = _swing_line(curve, away["abbrev"], home["abbrev"], "to") or "Win probability by PuckPulse"
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
