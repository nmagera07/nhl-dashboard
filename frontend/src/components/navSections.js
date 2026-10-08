// The app's three top-level sections, shared by the desktop header and the
// mobile tab bar. Detail pages belong to the section you'd reach them from:
// games under Scores, teams under Standings, players under Players.
export const SECTIONS = [
  { key: "scores", label: "Scores", to: "/" },
  { key: "standings", label: "Standings", to: "/standings" },
  { key: "players", label: "Players", to: "/players" },
];

export function sectionFor(pathname) {
  if (pathname.startsWith("/standings") || pathname.startsWith("/teams")) return "standings";
  if (pathname.startsWith("/players") || pathname.startsWith("/leaderboard")) return "players";
  return "scores";
}
