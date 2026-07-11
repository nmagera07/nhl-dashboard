import { useState, useEffect } from "react";

// Shared fetch-and-status pattern used across pages: loading -> ready/error.
// - `transform` optionally reshapes the parsed response (e.g. defaulting a
//   non-array response to []) before it's stored.
// - `onSuccess` is an optional side effect run once data arrives (e.g.
//   seeding a derived default like the standings page's active division).
// - Pass a falsy `url` to skip fetching entirely (status stays "idle").
//
// Note: this effect only ever calls setState inside the async .then/.catch
// callbacks, never synchronously in the effect body -- that's what keeps it
// clean under the react-hooks/set-state-in-effect lint rule. Pages that
// need to refetch when their own identity changes (e.g. RosterPage
// navigating from one team to another) rely on a remount via a `key` prop
// rather than this hook resetting itself back to "loading" mid-lifecycle.
export function useFetchWithStatus(url, { initialData = null, transform, onSuccess } = {}) {
  const [data, setData] = useState(initialData);
  const [status, setStatus] = useState(url ? "loading" : "idle");

  useEffect(() => {
    if (!url) return;
    fetch(url)
      .then((res) => res.json())
      .then((raw) => {
        const value = transform ? transform(raw) : raw;
        setData(value);
        setStatus("ready");
        if (onSuccess) onSuccess(value);
      })
      .catch(() => setStatus("error"));
  }, [url]);

  return { data, status };
}
