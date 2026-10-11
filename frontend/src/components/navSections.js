// The app's top-level sections, shared by the desktop header and the
// mobile tab bar. Detail pages belong to the section you'd reach them from:
// games under Scores, teams under Standings, the model's track record
// under Playoffs, players under Players.
export const SECTIONS = [
  { key: "scores", label: "Scores", to: "/" },
  { key: "standings", label: "Standings", to: "/standings" },
  { key: "playoffs", label: "Playoffs", to: "/playoffs" },
  { key: "players", label: "Players", to: "/players" },
];

export function sectionFor(pathname) {
  if (pathname.startsWith("/standings") || pathname.startsWith("/teams")) return "standings";
  if (pathname.startsWith("/playoffs") || pathname.startsWith("/track-record")) return "playoffs";
  if (pathname.startsWith("/players") || pathname.startsWith("/leaderboard")) return "players";
  return "scores";
}
