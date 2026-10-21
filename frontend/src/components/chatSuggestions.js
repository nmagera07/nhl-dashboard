// Starter questions for the chat, by section of the app, worded the way fans
// ask and leaning on what PuckPulse AI's tools can answer (see
// intelligence/app/tools.py). `team` is the reader's favorite team's name,
// when they've picked one, so the first question is about their team.
export function suggestionsFor({ page, topic, team }) {
  if (page === "team") {
    return ["Who's in goal tonight, and what are the lines?", "What happens to their playoff odds if they win their next 5?",
      "How hard is their upcoming schedule?"];
  }
  if (page === "player") {
    return ["How's his season going?", "What do his advanced stats say?", "How does this season compare to his last five?"];
  }
  if (page === "game") return ["How did this game go?", "Who's in goal, and who's favored?", "Who dominated, and does the shot count back it up?"];
  const mine = (question, fallback) => (team ? question.replace("{team}", team) : fallback);
  switch (topic) {
    case "bets":
      return ["Any value bets tonight?", "What's a puck line?", "How has PuckPulse done against the sportsbooks?"];
    case "news":
      return [mine("What's the latest on the {team}?", "What's the latest fantasy news?"), "Who should I pick up in fantasy this week?",
        mine("Who's injured on the {team}?", "Any big injuries right now?")];
    case "standings":
    case "playoffs":
      return [mine("What do the {team} need to make the playoffs?", "Who's in the wild-card race?"),
        "Who has the easiest schedule left?", "Who's projected to pick first in the draft?"];
    case "players":
      return ["Who leads the league in assists?", "Who's the best goalie this season?", "Compare McDavid and MacKinnon"];
    default: // scores
      return ["Who won last night?", "What's on tonight, and who's favored?",
        mine("How are the {team} doing?", "Who's the best goalie this season?")];
  }
}
