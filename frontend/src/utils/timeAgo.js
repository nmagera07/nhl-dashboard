// "5m ago", "3h ago", "Yesterday", "Oct 9": how fresh a headline is.
export function timeAgo(iso, now = Date.now()) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.round((now - then) / 60000));
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  if (hours < 48) return "Yesterday";
  return new Date(then).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// "2026-10-16" -> "Oct 16", for expected return dates.
export function shortDate(isoDate) {
  if (!isoDate) return null;
  const [y, m, d] = isoDate.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
