// A shared game link, puckpulse.io/g/{game id}: link previews (iMessage,
// Discord, Reddit, X...) read a page's HTML without running JavaScript, and
// the app's HTML is the same for every page, so this returns the game's own
// preview tags (title, description, and an image the API draws), then
// sends people straight on to the game page.
//
// staticwebapp.config.json rewrites /g/* here; the game id comes from the
// original URL (or /api/share/{id} directly). /t/{team abbrev} works the
// same way for a team, sending people on to the team page, and
// /s/{YYYY-MM-DD} for that night's Swing of the Night, on to its game, and
// /c/{player}-{player} for a player comparison, on to the compare page.

const API = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io";
const SITE = "https://puckpulse.io";

const escape = (text) =>
  String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function gameId(req) {
  const fromRoute = req.params && req.params.id;
  const original = req.headers["x-ms-original-url"] || "";
  const fromUrl = (original.match(/\/g\/(\d+)/) || [])[1];
  const id = fromRoute || fromUrl || (req.query && req.query.id);
  return /^\d{6,12}$/.test(String(id || "")) ? String(id) : null;
}

// The 32 teams a /t/ link may name (matches frontend/src/seo/site.js).
const TEAMS = new Set(("ANA BOS BUF CGY CAR CHI COL CBJ DAL DET EDM FLA LAK MIN MTL NSH NJD NYI NYR OTT " +
  "PHI PIT SJS SEA STL TBL TOR UTA VAN VGK WSH WPG").split(" "));

// "BUF" for /t/BUF (or /api/share/t/BUF, ?team=BUF); null for anything not a known team.
function teamAbbrev(req) {
  const original = req.headers["x-ms-original-url"] || "";
  const fromUrl = (original.match(/\/t\/([A-Za-z]{3})(?:[/?#]|$)/) || [])[1];
  const abbrev = String(fromUrl || (req.query && req.query.team) || "").toUpperCase();
  return TEAMS.has(abbrev) ? abbrev : null;
}

// "2026-10-20" for /s/2026-10-20; null for anything that isn't a date.
function swingDate(req) {
  const original = req.headers["x-ms-original-url"] || "";
  const day = (original.match(/\/s\/(\d{4}-\d{2}-\d{2})(?:[/?#]|$)/) || [])[1];
  return day && !Number.isNaN(Date.parse(day)) ? day : null;
}

// [a, b] player ids for /c/8478402-8447400; null for anything else.
function comparePair(req) {
  const original = req.headers["x-ms-original-url"] || "";
  const m = original.match(/\/c\/(\d{6,10})-(\d{6,10})(?:[/?#]|$)/);
  return m ? [m[1], m[2]] : null;
}

function isTeamLink(req) {
  return /\/t\//.test(req.headers["x-ms-original-url"] || "") || Boolean(req.query && req.query.team);
}

// Only the preview's words and picture come from the API; where the link
// goes (url) is always built here, so nothing upstream can redirect it.
function previewText(data) {
  const out = {};
  for (const key of ["title", "description"]) if (typeof data[key] === "string") out[key] = data[key];
  if (typeof data.image === "string" && data.image.startsWith(`${API}/og/`)) out.image = data.image;
  return out;
}

function page({ title, description, image, url }) {
  const tags = [
    ["og:type", "website"], ["og:site_name", "PuckPulse"], ["og:title", title], ["og:description", description],
    ["og:url", url], ["og:image", image], ["og:image:width", "1200"], ["og:image:height", "630"],
  ].map(([property, content]) => `<meta property="${property}" content="${escape(content)}">`);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>${escape(title)} · PuckPulse</title>
<meta name="description" content="${escape(description)}">
${tags.join("\n")}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="${escape(image)}">
<link rel="canonical" href="${escape(url)}">
<meta http-equiv="refresh" content="0; url=${escape(url)}">
</head><body><p><a href="${escape(url)}">Open on PuckPulse</a></p></body></html>`;
}

module.exports = async function (context, req) {
  const pair = comparePair(req);
  const swing = pair ? null : swingDate(req);
  const team = !pair && !swing && isTeamLink(req) ? teamAbbrev(req) : null;
  const id = pair || swing || isTeamLink(req) ? null : gameId(req);
  let meta = {
    title: "PuckPulse: NHL scores, playoff odds, and an AI hockey analyst",
    description: "Live NHL scores, playoff odds for every team, goal alerts, and an AI hockey analyst you can ask anything. Free.",
    image: `${SITE}/og-card.png`,
    url: id ? `${SITE}/games/${id}` : team ? `${SITE}/teams/${team}` : pair ? `${SITE}/compare?a=${pair[0]}&b=${pair[1]}` : SITE,
  };
  if (pair) {
    try {
      const response = await fetch(`${API}/compare/${pair[0]}/${pair[1]}/share`, { signal: AbortSignal.timeout(8000) });
      if (response.ok) meta = { ...meta, ...previewText(await response.json()) };
    } catch (error) {
      context.log.warn(`share compare ${pair.join("-")}: ${error}`);
    }
  } else if (swing) {
    try {
      const response = await fetch(`${API}/swing/${swing}/share`, { signal: AbortSignal.timeout(8000) });
      if (response.ok) {
        const data = await response.json();
        meta = { ...meta, ...previewText(data) };
        // The game is the only thing taken from the API, and only as a number on our own site.
        if (/^\d{6,12}$/.test(String(data.game_id || ""))) meta.url = `${SITE}/games/${data.game_id}`;
      }
    } catch (error) {
      context.log.warn(`share swing ${swing}: ${error}`);
    }
  } else if (team) {
    try {
      const response = await fetch(`${API}/teams/${team}/share`, { signal: AbortSignal.timeout(6000) });
      if (response.ok) meta = { ...meta, ...previewText(await response.json()) };
    } catch (error) {
      context.log.warn(`share team ${team}: ${error}`);
    }
  } else if (id) {
    try {
      const response = await fetch(`${API}/games/${id}/share`, { signal: AbortSignal.timeout(6000) });
      if (response.ok) meta = { ...meta, ...previewText(await response.json()) };
    } catch (error) {
      context.log.warn(`share ${id}: ${error}`); // the site's card still beats a bare link
    }
  }
  context.res = {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300" },
    body: page(meta),
  };
};

module.exports.TEAMS = TEAMS;
