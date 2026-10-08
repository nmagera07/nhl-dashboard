// Calendar-date helpers for the Scores page. Dates are "YYYY-MM-DD" strings
// in the viewer's local time zone (the same day the NHL schedule shows).

const pad = (n) => String(n).padStart(2, "0");

function toISO(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fromISO(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function todayISO(now = new Date()) {
  return toISO(now);
}

export function isValidISODate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return false;
  return toISO(fromISO(value)) === value;
}

export function shiftDate(iso, days) {
  const d = fromISO(iso);
  d.setDate(d.getDate() + days);
  return toISO(d);
}

// "Today", "Yesterday", "Tomorrow", or e.g. "Mon, Oct 12".
export function relativeDayLabel(iso, today = todayISO()) {
  if (iso === today) return "Today";
  if (iso === shiftDate(today, -1)) return "Yesterday";
  if (iso === shiftDate(today, 1)) return "Tomorrow";
  return fromISO(iso).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

export function longDateLabel(iso) {
  return fromISO(iso).toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

// --- Months ("YYYY-MM") for the calendar picker ---

export function monthOf(iso) {
  return iso.slice(0, 7);
}

export function shiftMonth(ym, months) {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 1 + months, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

export function monthLabel(ym) {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString([], { month: "long", year: "numeric" });
}

// Calendar grid for a month, Sunday-first: leading nulls for the days
// before the 1st, then each date as "YYYY-MM-DD".
export function monthGrid(ym) {
  const [y, m] = ym.split("-").map(Number);
  const leading = new Date(y, m - 1, 1).getDay();
  const count = new Date(y, m, 0).getDate();
  return [
    ...Array(leading).fill(null),
    ...Array.from({ length: count }, (_, i) => `${ym}-${pad(i + 1)}`),
  ];
}
