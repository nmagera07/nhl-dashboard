// The site's public routes and teams, in one place: the sitemap
// (public/sitemap.xml, checked by site.test.js), page titles (usePageTitle),
// and the /t/{abbrev} share links all read from here.

export const SITE = "https://puckpulse.io";

export const TEAMS = {
  ANA: "Anaheim Ducks", BOS: "Boston Bruins", BUF: "Buffalo Sabres", CGY: "Calgary Flames",
  CAR: "Carolina Hurricanes", CHI: "Chicago Blackhawks", COL: "Colorado Avalanche", CBJ: "Columbus Blue Jackets",
  DAL: "Dallas Stars", DET: "Detroit Red Wings", EDM: "Edmonton Oilers", FLA: "Florida Panthers",
  LAK: "Los Angeles Kings", MIN: "Minnesota Wild", MTL: "Montréal Canadiens", NSH: "Nashville Predators",
  NJD: "New Jersey Devils", NYI: "New York Islanders", NYR: "New York Rangers", OTT: "Ottawa Senators",
  PHI: "Philadelphia Flyers", PIT: "Pittsburgh Penguins", SJS: "San Jose Sharks", SEA: "Seattle Kraken",
  STL: "St. Louis Blues", TBL: "Tampa Bay Lightning", TOR: "Toronto Maple Leafs", UTA: "Utah Mammoth",
  VAN: "Vancouver Canucks", VGK: "Vegas Golden Knights", WSH: "Washington Capitals", WPG: "Winnipeg Jets",
};

// Indexable top-level pages (no per-game/player pages, no redirects).
export const PAGES = [
  { path: "/", title: null },
  { path: "/standings", title: "NHL Standings" },
  { path: "/playoffs", title: "NHL Playoff Odds" },
  { path: "/players", title: "NHL Player Leaders" },
  { path: "/news", title: "NHL News" },
  { path: "/track-record", title: "Prediction Track Record" },
  { path: "/report-card", title: "Report Card" },
  { path: "/draft-lottery", title: "NHL Draft Lottery Odds" },
  { path: "/pickem", title: "Pick'em" },
  { path: "/bets", title: "Bets", index: false }, // kept out of the sitemap: launch leads with non-betting pages
];

export const SITEMAP_PATHS = [...PAGES.filter((p) => p.index !== false).map((p) => p.path), ...Object.keys(TEAMS).map((t) => `/teams/${t}`)];

export const BRAND = "PuckPulse";
export const DEFAULT_TITLE = "PuckPulse: NHL scores, playoff odds, and an AI hockey analyst";

// The document title for a path ("Standings | PuckPulse", "Buffalo Sabres playoff odds | PuckPulse").
export function titleFor(pathname) {
  const path = pathname.replace(/\/+$/, "") || "/";
  const team = path.match(/^\/teams\/([A-Za-z]{3})$/);
  if (team) {
    const name = TEAMS[team[1].toUpperCase()];
    return name ? `${name} playoff odds & stats | ${BRAND}` : DEFAULT_TITLE;
  }
  if (/^\/games\/\d+$/.test(path)) return `Game | ${BRAND}`;
  if (/^\/players\/\d+$/.test(path)) return `Player | ${BRAND}`;
  const page = PAGES.find((p) => p.path === path);
  return page && page.title ? `${page.title} | ${BRAND}` : DEFAULT_TITLE;
}

export function sitemapXml(paths = SITEMAP_PATHS) {
  const urls = paths.map((p) => `  <url><loc>${SITE}${p === "/" ? "/" : p}</loc></url>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}
