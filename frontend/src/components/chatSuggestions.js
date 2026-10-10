// Starter questions per page type. Each leans on what that page's data or the
// agent's tools can actually answer (see intelligence/app/tools.py): standings,
// schedules, odds history, players, and the playoff-odds model's simulations.
export const SUGGESTIONS = {
  standings: [
    "Who's in the wild-card race in each conference?",
    "What does Detroit need over its next 10 games to make the playoffs?",
    "Who has the easiest remaining schedule?",
  ],
  team: [
    "What happens to their playoff odds if they win their next 5?",
    "How hard is their upcoming schedule?",
    "How have their playoff odds moved this season?",
  ],
  player: [
    "How does this season compare to his last five?",
    "Is he on pace for a career year?",
    "What do his advanced stats say?",
  ],
  game: [
    "How did this game go?",
    "What was the turning point?",
    "Who dominated, and does the shot count back it up?",
  ],
};
