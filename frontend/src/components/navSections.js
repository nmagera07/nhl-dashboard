// The app's top-level sections, shared by the desktop header and the
// mobile tab bar. Detail pages belong to the section you'd reach them from:
// games under Scores, teams under Standings, the model's track record
// under Playoffs, players under Players.
export const SECTIONS = [
  { key: "scores", label: "Scores", to: "/" },
  { key: "bets", label: "Bets", to: "/bets" },
  { key: "standings", label: "Standings", to: "/standings" },
  { key: "playoffs", label: "Playoffs", to: "/playoffs" },
  { key: "players", label: "Players", to: "/players" },
  { key: "news", label: "News", to: "/news" },
];

export function sectionFor(pathname) {
  if (pathname.startsWith("/standings") || pathname.startsWith("/teams")) return "standings";
  if (pathname.startsWith("/playoffs") || pathname.startsWith("/track-record") || pathname.startsWith("/draft-lottery")) return "playoffs";
  if (pathname.startsWith("/players") || pathname.startsWith("/leaderboard") || pathname.startsWith("/compare")) return "players";
  if (pathname.startsWith("/news")) return "news";
  if (pathname.startsWith("/bets") || pathname.startsWith("/report-card")) return "bets";
  return "scores";
}
