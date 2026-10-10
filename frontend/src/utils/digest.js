// When the AI couldn't write the digest, the same facts as a plain list.
export function factsAsMarkdown(facts) {
  const name = (abbrev) => facts.team_names?.[abbrev] || abbrev;
  const lines = [];
  if (facts.last_night?.length) {
    lines.push("### Last night");
    facts.last_night.forEach((g) =>
      lines.push(`- ${name(g.away)} ${g.away_score}, ${name(g.home)} ${g.home_score}${g.ended ? ` (${g.ended})` : ""}`)
    );
  }
  const moves = [...(facts.playoff_odds_moves?.rising || []), ...(facts.playoff_odds_moves?.falling || [])];
  if (moves.length) {
    lines.push("### Playoff race");
    moves.forEach((m) => lines.push(`- ${name(m.team)}: ${Math.round(m.from_pct)}% → ${Math.round(m.to_pct)}%`));
  }
  const game = facts.game_of_the_night;
  if (game) {
    lines.push("### Tonight");
    lines.push(`- Game of the night: ${name(game.away)} at ${name(game.home)}, ${game.time} (model: ${name(game.home)} ${game.model_home_win_pct}%)`);
  }
  return lines.join("\n");
}
