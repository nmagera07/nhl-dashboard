import { useCallback, useMemo, useSyncExternalStore } from "react";
import { track } from "../utils/analytics.js";

// The teams the viewer follows, remembered in this browser (no accounts).
// The first is their main team ("My team"): the standings open on its
// division, News filters to it, and its games lead the scoreboard. The
// others ride along: their games are pinned too, they get a tab on the My
// team card, a star in the standings, and goal alerts.
//
// useSyncExternalStore keeps every component that reads it in sync: the
// Follow button on the team page, the Scores card, and the standings stars
// all update together, and so do other open tabs (via the "storage" event).
const KEY = "nhl-dash:followed-teams";
const OLD_KEY = "nhl-dash:favorite-team"; // one team, before following several (still written: the main team)
const CHANGE_EVENT = "nhl-dash:favorite-team-change";
export const MAX_FOLLOWED = 5;

function read() {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (saved != null) return saved;
    const old = window.localStorage.getItem(OLD_KEY);
    return old ? JSON.stringify([old]) : "[]";
  } catch {
    return "[]"; // storage blocked (private mode, disabled cookies)
  }
}

function parse(raw) {
  try {
    const teams = JSON.parse(raw);
    return Array.isArray(teams) ? teams.filter((t) => typeof t === "string" && /^[A-Z]{3}$/.test(t)).slice(0, MAX_FOLLOWED) : [];
  } catch {
    return [];
  }
}

function write(teams) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(teams));
    if (teams[0]) window.localStorage.setItem(OLD_KEY, teams[0]);
    else window.localStorage.removeItem(OLD_KEY);
  } catch {
    // Can't persist; nothing else to do.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

// [teams, { follow, unfollow, makeMain, restore }]: follow adds a team at the
// end (the main team if it's the first), makeMain moves (or adds) it to the
// front, restore puts back an earlier list (undoing an unfollow).
export function useFollowedTeams() {
  const raw = useSyncExternalStore(subscribe, read, () => "[]");
  const teams = useMemo(() => parse(raw), [raw]);
  const actions = useMemo(() => {
    const current = () => parse(read());
    return {
      follow(abbrev) {
        const now = current();
        if (now.includes(abbrev) || now.length >= MAX_FOLLOWED) return;
        track("follow-team", { team: abbrev });
        write([...now, abbrev]);
      },
      unfollow(abbrev) {
        write(current().filter((t) => t !== abbrev));
      },
      makeMain(abbrev) {
        const now = current();
        if (!now.includes(abbrev)) track("follow-team", { team: abbrev });
        write([abbrev, ...now.filter((t) => t !== abbrev)].slice(0, MAX_FOLLOWED));
      },
      restore(teams) {
        write(parse(JSON.stringify(teams)));
      },
    };
  }, []);
  return [teams, actions];
}

// [main team or null, setter]: the setter makes a team the main one, or
// with null stops following the main one.
export function useFavoriteTeam() {
  const [teams, { makeMain, unfollow }] = useFollowedTeams();
  const main = teams[0] || null;
  const setFavorite = useCallback((abbrev) => (abbrev ? makeMain(abbrev) : main && unfollow(main)), [makeMain, unfollow, main]);
  return [main, setFavorite];
}
