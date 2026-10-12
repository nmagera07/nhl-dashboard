// "+1.5" / "−0.3" / "0.0" (a real minus sign, and no "−0.0"); "—" for no value.
export function formatSigned(value, digits = 1) {
  if (value == null) return "—";
  const text = Math.abs(value).toFixed(digits);
  if (Number(text) === 0) return (0).toFixed(digits);
  return `${value > 0 ? "+" : "−"}${text}`;
}

// 1190 -> "19:50" (minutes:seconds). "—" for no value.
export function formatToi(seconds) {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
