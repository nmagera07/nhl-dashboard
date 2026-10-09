// What each stat abbreviation means, in plain English. Keys are the term
// as shown, except where one abbreviation means different things for teams
// and players (TEAM_PTS vs PTS, TEAM_L vs L).
export const GLOSSARY = {
  // Records and standings
  GP: { name: "Games played" },
  W: { name: "Wins" },
  L: { name: "Losses" },
  TEAM_L: { name: "Regulation losses", detail: "Losses in regulation time, worth 0 points." },
  OT: { name: "Overtime/shootout losses", detail: "Losing in overtime or a shootout still earns 1 point." },
  OTL: { name: "Overtime/shootout losses", detail: "Losing in overtime or a shootout still earns 1 point." },
  TEAM_PTS: { name: "Points", detail: "2 for a win, 1 for an overtime or shootout loss." },
  GF: { name: "Goals for", detail: "Goals scored." },
  GA: { name: "Goals against", detail: "Goals allowed." },
  DIFF: { name: "Goal differential", detail: "Goals for minus goals against." },
  L10: { name: "Last 10 games", detail: "Record over the last 10: wins, regulation losses, overtime losses." },
  STRK: { name: "Streak", detail: "Current run of wins (W), regulation losses (L), or overtime losses (OT)." },
  "PO%": { name: "Playoff odds", detail: "How often the team makes the playoffs in 10,000 simulations of the rest of the season." },
  PACE: { name: "Points pace", detail: "Points the team would finish with at its current rate over a full season." },
  "7D": { name: "7-day change", detail: "How much the playoff odds moved over the last week, in percentage points." },

  // Advanced (MoneyPuck, 5-on-5)
  "xG%": { name: "Expected goals share", detail: "xGF ÷ (xGF + xGA) at 5-on-5. Above 50% means a team creates better chances than it allows." },
  xGF: { name: "Expected goals for", detail: "How many goals a team's shots should produce, based on shot location, type, and situation." },
  xGA: { name: "Expected goals against", detail: "How many goals the shots a team allows should produce." },
  SF: { name: "Shots for", detail: "Shots on goal taken." },
  SA: { name: "Shots against", detail: "Shots on goal faced." },
  PDO: { name: "PDO (luck meter)", detail: "Shooting % + save % at 5-on-5. About 100 is average; far above or below usually evens out." },
  "CORSI%": { name: "Corsi %", detail: "Share of all shot attempts (on goal, missed, or blocked) while on the ice, 5-on-5. A puck-possession stat." },
  "FENWICK%": { name: "Fenwick %", detail: "Like Corsi %, but leaving out blocked shots." },
  "IND_XG": { name: "Individual expected goals", detail: "Expected goals from the player's own shots." },
  "ONICE_XG": { name: "On-ice expected goals", detail: "Expected goals for and against while the player was on the ice, 5-on-5." },

  // Skaters
  G: { name: "Goals" },
  A: { name: "Assists" },
  P: { name: "Points", detail: "Goals plus assists." },
  PTS: { name: "Points", detail: "Goals plus assists." },
  "+/-": { name: "Plus/minus", detail: "+1 when on the ice for an even-strength or shorthanded goal for, −1 for one against." },
  SOG: { name: "Shots on goal" },
  SHOTS: { name: "Shots on goal" },
  PIM: { name: "Penalty minutes" },
  HIT: { name: "Hits" },
  BLK: { name: "Blocked shots" },
  TOI: { name: "Time on ice" },

  // Goalies
  SV: { name: "Saves" },
  "SV%": { name: "Save percentage", detail: "Share of shots on goal the goalie stopped." },
  GAA: { name: "Goals against average", detail: "Goals allowed per 60 minutes played." },
  SO: { name: "Shutouts", detail: "Games without allowing a goal." },
};

export function glossaryEntry(term) {
  return GLOSSARY[term] || null;
}
