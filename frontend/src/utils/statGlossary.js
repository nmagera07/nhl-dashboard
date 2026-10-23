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

  // Advanced (5-on-5; PuckPulse xG, NHL stats)
  "xG%": { name: "Expected goals share", detail: "xGF ÷ (xGF + xGA) at 5-on-5. Above 50% means a team creates better chances than it allows." },
  xGF: { name: "Expected goals for", detail: "How many goals a team's shots should produce, based on shot location, type, and situation." },
  xGA: { name: "Expected goals against", detail: "How many goals the shots a team allows should produce." },
  SF: { name: "Shots for", detail: "Shots on goal taken." },
  SA: { name: "Shots against", detail: "Shots on goal faced." },
  PDO: { name: "PDO (luck meter)", detail: "Shooting % + save % at 5-on-5. About 100 is average; far above or below usually evens out." },
  "CORSI%": { name: "Corsi %", detail: "Share of all shot attempts (on goal, missed, or blocked) while on the ice, 5-on-5. A puck-possession stat." },
  "IND_XG": { name: "Individual expected goals", detail: "Expected goals from the player's own shots." },
  "ONICE_XG": { name: "On-ice expected goals", detail: "Expected goals for and against while the player was on the ice, 5-on-5." },

  // Goalies (all situations; PuckPulse xG)
  GSAX: { name: "Goals saved above expected", detail: "Expected goals against minus goals allowed: how many more goals an average goalie would have given up on the same shots. Above 0 is better than average." },
  GSAX60: { name: "GSAx per 60", detail: "Goals saved above expected per 60 minutes, so goalies with different workloads compare fairly." },
  WAR: { name: "Wins above replacement", detail: "Wins a player has added this season over a call-up-level replacement. An estimate from PuckPulse's model: box-score stats for skaters, saves above expected for goalies. Goalies swing the most wins, so compare within a position." },
  HD_GSAX: { name: "High-danger GSAx", detail: "GSAx on shots worth 0.20 expected goals or more, mostly from the slot and crease: the hardest saves." },

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
  ATOI: { name: "Average time on ice", detail: "Minutes per game, all situations. How much the coach plays him." },

  // Goalies
  SV: { name: "Saves" },
  "SV%": { name: "Save percentage", detail: "Share of shots on goal the goalie stopped." },
  GAA: { name: "Goals against average", detail: "Goals allowed per 60 minutes played." },
  SO: { name: "Shutouts", detail: "Games without allowing a goal." },
};

export function glossaryEntry(term) {
  return GLOSSARY[term] || null;
}
