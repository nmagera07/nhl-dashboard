// A shared game link, puckpulse.io/g/{game id}: link previews (iMessage,
// Discord, Reddit, X...) read a page's HTML without running JavaScript, and
// the app's HTML is the same for every page, so this returns the game's own
// preview tags (title, description, and an image the API draws), then
// sends people straight on to the game page.
//
// staticwebapp.config.json rewrites /g/* here; the game id comes from the
// original URL (or /api/share/{id} directly).

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
  const id = gameId(req);
  let meta = {
    title: "PuckPulse: NHL scores, playoff odds, and fair betting odds",
    description: "Live NHL scores, playoff odds, goal alerts, and tonight's lines next to fair odds. Free.",
    image: `${SITE}/og-card.png`,
    url: id ? `${SITE}/games/${id}` : SITE,
  };
  if (id) {
    try {
      const response = await fetch(`${API}/games/${id}/share`, { signal: AbortSignal.timeout(6000) });
      if (response.ok) meta = { ...meta, ...(await response.json()) };
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
