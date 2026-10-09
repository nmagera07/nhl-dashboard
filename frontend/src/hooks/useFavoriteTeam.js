import { useCallback, useSyncExternalStore } from "react";

// The viewer's favorite team, remembered in this browser (no accounts).
// useSyncExternalStore keeps every component that reads it in sync: the
// star on the team page, the Scores card, and the standings markers all
// update together, and so do other open tabs (via the "storage" event).
const KEY = "nhl-dash:favorite-team";
const CHANGE_EVENT = "nhl-dash:favorite-team-change";

function read() {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null; // storage blocked (private mode, disabled cookies)
  }
}

function subscribe(onChange) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

export function useFavoriteTeam() {
  const favorite = useSyncExternalStore(subscribe, read, () => null);
  const setFavorite = useCallback((abbrev) => {
    try {
      if (abbrev) window.localStorage.setItem(KEY, abbrev);
      else window.localStorage.removeItem(KEY);
    } catch {
      // Can't persist; nothing else to do.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);
  return [favorite, setFavorite];
}
