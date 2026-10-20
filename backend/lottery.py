"""
The NHL draft lottery (the format since 2022): the 16 teams that miss the
playoffs, ordered worst first, hold 1,000 combinations between them, and
two draws decide the first two picks. Everyone else picks in reverse order
of the standings.

  - Draw 1: the winner moves to No. 1, but no team moves up more than 10
    spots. So only the 11 worst teams can win No. 1; if a team ranked 12th
    to 16th wins, it moves up 10 and the worst team keeps No. 1. (That's
    why the worst team's chance at No. 1 is 25.5%, not its 18.5% share.)
  - Draw 2: among the other 15, the winner moves to No. 2, or up 10 spots
    if that's as far as it can go.
  Each move pushes the teams it passes down one spot.

Exact: every pair of draw winners is enumerated (16 x 15), so there's no
sampling noise. Not modeled: the rule that a team can win the lottery at
most twice in five years.
"""

COMBINATIONS = (185, 135, 115, 95, 85, 75, 65, 60, 50, 35, 30, 25, 20, 15, 5, 5)  # of 1,000, worst team first
MAX_JUMP = 10


def _move(order, team, target):
    """
    order with team moved up to `target` (0-based), or 10 spots if that's as
    far as it can go. Winning never moves a team down: the worst team, still
    at No. 1 because a 12th-16th team won draw 1, keeps No. 1 if it then
    wins draw 2 too.
    """
    order = list(order)
    at = order.index(team)
    to = max(target, at - MAX_JUMP)
    if to >= at:
        return order
    order.pop(at)
    order.insert(to, team)
    return order


def final_order(order, first, second):
    """The pick order (worst first) after draw 1 is won by `first` and draw 2 by `second`."""
    return _move(_move(order, first, 0), second, 1)


def pick_chances(order):
    """
    {team: [chance of pick 1, pick 2, ... pick 16]} for the 16 non-playoff
    teams in `order` (worst first).
    """
    if len(order) != len(COMBINATIONS):
        raise ValueError(f"the lottery needs {len(COMBINATIONS)} teams, got {len(order)}")
    chances = {team: [0.0] * len(order) for team in order}
    total = sum(COMBINATIONS)
    for i, first in enumerate(order):
        p_first = COMBINATIONS[i] / total
        rest = total - COMBINATIONS[i]
        for j, second in enumerate(order):
            if j == i:
                continue
            p = p_first * COMBINATIONS[j] / rest
            for pick, team in enumerate(final_order(order, first, second)):
                chances[team][pick] += p
    return chances
