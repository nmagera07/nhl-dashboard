export function formatSeasonLabel(seasonId) {
  const str = String(seasonId);
  return `${str.slice(2, 4)}-${str.slice(6, 8)}`;
}
