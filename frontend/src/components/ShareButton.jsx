import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../config.js";
import { track } from "../utils/analytics.js";

const enc = encodeURIComponent;
const isTouch = () => typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

// Where to share: each opens that app's own "new post" page with the link
// (and the text, where the app takes one) filled in.
function targets(url, text) {
  return [
    { key: "x", label: "Post on X", href: `https://x.com/intent/tweet?text=${enc(text)}&url=${enc(url)}` },
    { key: "reddit", label: "Reddit", href: `https://www.reddit.com/submit?url=${enc(url)}&title=${enc(text)}` },
    { key: "bluesky", label: "Bluesky", href: `https://bsky.app/intent/compose?text=${enc(`${text} ${url}`)}` },
    { key: "facebook", label: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}` },
    { key: "whatsapp", label: "WhatsApp", href: `https://wa.me/?text=${enc(`${text} ${url}`)}` },
    ...(isTouch() ? [{ key: "sms", label: "Text message", href: `sms:?&body=${enc(`${text} ${url}`)}` }] : []),
  ];
}

// PuckPulse's own share menu (instead of the phone's share sheet): post to
// X, Reddit, Bluesky, Facebook, WhatsApp, or a text; copy the link; save the
// card image; or "More…" for the phone's sheet. Shares a link preview page:
// a game's (puckpulse.io/g/{id}) by default, or any url (Swing of the Night's
// /s/{date}, a comparison's /c/{a}-{b}); image is that page's card.
export default function ShareButton({ gameId, url: link, title, image, event = "share-game", label = "Share this game" }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const ref = useRef(null);
  const url = link || `https://puckpulse.io/g/${gameId}`;
  const card = image || (gameId ? `${API_BASE}/og/game/${gameId}.png` : null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => (e.type === "keydown" ? e.key === "Escape" : !ref.current?.contains(e.target)) && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const done = (how) => {
    track(event, { how });
    setOpen(false);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this link", url);
    }
    done("copy");
  };

  const saveImage = async () => {
    try {
      const blob = await (await fetch(card)).blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `puckpulse-${url.split("/").pop().replace(/[^\w-]/g, "") || "card"}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      window.open(card, "_blank", "noopener");
    }
    done("image");
  };

  const more = async () => {
    done("more");
    try {
      await navigator.share({ title, url });
    } catch {
      // closed the sheet
    }
  };

  return (
    <div className="share" ref={ref}>
      <button type="button" className="share-button" onClick={() => setOpen((o) => !o)} aria-label={label}
              aria-haspopup="menu" aria-expanded={open}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V4M8 8l4-4 4 4M6 12v6a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-6" /></svg>
        {copied ? "Link copied" : "Share"}
      </button>
      {open && (
        <div className="share-menu" role="menu" aria-label="Share to">
          {targets(url, title).map((t) => (
            <a key={t.key} role="menuitem" href={t.href} target="_blank" rel="noopener noreferrer" onClick={() => done(t.key)}>
              {t.label}
            </a>
          ))}
          <button type="button" role="menuitem" onClick={copy}>Copy link</button>
          {card && <button type="button" role="menuitem" onClick={saveImage}>Save image</button>}
          {typeof navigator !== "undefined" && navigator.share && <button type="button" role="menuitem" onClick={more}>More…</button>}
        </div>
      )}
    </div>
  );
}
