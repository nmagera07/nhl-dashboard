import { useState } from "react";
import { track } from "../utils/analytics.js";

// Shares a game's link preview page (puckpulse.io/g/{id}, which apps show
// as a card with the matchup and win chances). Phones get the share sheet;
// elsewhere the link is copied.
export default function ShareButton({ gameId, title }) {
  const [copied, setCopied] = useState(false);
  const url = `https://puckpulse.io/g/${gameId}`;
  const share = async () => {
    track("share-game");
    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        return;
      } catch (err) {
        if (err?.name === "AbortError") return; // closed the share sheet
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this link", url);
    }
  };
  return (
    <button type="button" className="share-button" onClick={share} aria-label="Share this game">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V4M8 8l4-4 4 4M6 12v6a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-6" /></svg>
      {copied ? "Link copied" : "Share"}
    </button>
  );
}
