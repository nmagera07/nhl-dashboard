import { useCallback, useState } from "react";
import { loadBets, saveBets } from "../utils/myBets.js";

// The viewer's tracked bets (utils/myBets.js), saved on every change.
export function useMyBets() {
  const [bets, setBets] = useState(loadBets);

  const update = useCallback((change) => {
    setBets((current) => {
      const next = change(current);
      saveBets(next);
      return next;
    });
  }, []);

  // Track a bet, or stop tracking it if it's already there.
  const toggle = useCallback((bet) => update((current) => (
    current.some((b) => b.id === bet.id) ? current.filter((b) => b.id !== bet.id) : [...current, bet]
  )), [update]);

  const remove = useCallback((id) => update((current) => current.filter((b) => b.id !== id)), [update]);

  // results: {betId: result} from grading.
  const record = useCallback((results) => update((current) => current.map((b) => (results[b.id] ? { ...b, result: results[b.id] } : b))), [update]);

  return { bets, toggle, remove, record };
}
