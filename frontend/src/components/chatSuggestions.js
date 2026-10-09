// Starter questions per page type: things the page's data can actually
// answer (see intelligence/app/compact.py for what each page sends).
export const SUGGESTIONS = {
  standings: [
    "Who's in the wild-card race in each conference?",
    "Which team is hottest over its last 10 games?",
    "Which team has a good goal differential but is outside a playoff spot?",
  ],
  team: [
    "What's driving this team's start?",
    "Is their record backed up by their goal differential?",
    "How's the goaltending?",
  ],
  player: [
    "How does this season compare to his last five?",
    "Is he on pace for a career year?",
    "What stands out about his career?",
  ],
  game: [
    "How did this game go?",
    "What was the turning point?",
    "Who dominated, and does the shot count back it up?",
  ],
};
