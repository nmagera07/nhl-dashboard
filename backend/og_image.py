"""
Link preview images for games (1200x630 PNG, the size iMessage, Discord,
Reddit, Slack, and X expect): each team in its color with its win chance
before the game, or its score once it's live or final.

Drawn with Pillow in Inter (assets/fonts, SIL Open Font License). Team
logos are SVG only, which Pillow can't draw, so teams are their colors and
abbreviations.
"""

import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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


def render_game(game, home_win_prob=None):
    """PNG bytes for a game: game is the NHL box score/landing dict."""
    img = _background()
    draw = ImageDraw.Draw(img)
    icon = Image.open(os.path.join(ASSETS, "puckpulse-mark.png")).convert("RGBA").resize((98, 68))
    img.paste(icon, (60, 49), icon)
    draw.text((172, 83), "Puck", font=_font(48), fill=TEXT, anchor="lm")
    draw.text((172 + draw.textlength("Puck", font=_font(48)), 83), "Pulse", font=_font(48), fill=ACCENT, anchor="lm")
    status = status_line(game)
    draw.text((WIDTH - 64, 83), status, font=_font(34, "Bold"), fill=LIVE if status.startswith("LIVE") else TEXT,
              anchor="rm")

    away, home = game["awayTeam"], game["homeTeam"]
    state = game.get("gameState")
    if state in ("FINAL", "OFF", "LIVE", "CRIT"):
        big = (str(away.get("score", 0)), str(home.get("score", 0)))
        small = (None, None)
        footer = "Scores, box score, and highlights at puckpulse.io"
    elif home_win_prob is not None:
        big = (f"{round((1 - home_win_prob) * 100)}%", f"{round(home_win_prob * 100)}%")
        small = ("to win", "to win")
        footer = "Win chances by PuckPulse · lines, goalies, and fair odds at puckpulse.io"
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


def share_text(game, home_win_prob=None):
    """(title, description) for a game's link preview."""
    away, home = game["awayTeam"]["abbrev"], game["homeTeam"]["abbrev"]
    status = status_line(game)
    state = game.get("gameState")
    if state in ("FINAL", "OFF", "LIVE", "CRIT"):
        a, h = game["awayTeam"].get("score", 0), game["homeTeam"].get("score", 0)
        title = f"{away} {a} @ {home} {h} · {status}"
        verb = "Follow along" if status.startswith("LIVE") else "Box score and highlights"
        return title, f"{verb} on PuckPulse."
    title = f"{away} @ {home} · {status}"
    if home_win_prob is None:
        return title, "Preview, projected lines, and goalies on PuckPulse."
    fav, pct = (home, home_win_prob) if home_win_prob >= 0.5 else (away, 1 - home_win_prob)
    return title, f"PuckPulse gives {fav} a {round(pct * 100)}% chance to win. Lines, goalies, and fair odds."
