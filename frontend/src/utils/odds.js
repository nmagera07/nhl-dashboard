// American odds: +150 pays $150 on a $100 bet; -150 risks $150 to win $100.
export const formatPrice = (price) => (price == null ? "—" : price > 0 ? `+${price}` : `−${Math.abs(price)}`);

export const formatSpread = (spread) => (spread > 0 ? `+${spread}` : `−${Math.abs(spread)}`);

export const formatPct = (p) => `${Math.round(p * 100)}%`;

// Expected return per $1 as a signed percent: 0.062 -> "+6%".
export const formatEv = (ev) => `${ev >= 0 ? "+" : "−"}${Math.abs(Math.round(ev * 100))}%`;
