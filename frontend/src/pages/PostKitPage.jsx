import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";

const pct = (p) => `${Math.round(p * 100)}%`;

// The morning post kit (opened from the creator's "Swing of the Night is
// ready" notification): the night's card, the post text to tweak, and one
// tap to post it on X, save the image, or copy the text. Not linked anywhere.
export default function PostKitPage() {
  const [params] = useSearchParams();
  const day = /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : null;
  const { data, status } = useFetchWithStatus(day ? `${API_BASE}/swing-of-the-night?date=${day}` : null);
  const [text, setText] = useState(null);
  const [copied, setCopied] = useState(false);
  const link = `https://puckpulse.io/s/${day}`;
  const image = `${API_BASE}/og/swing/${day}.png`;

  useEffect(() => {
    document.title = "Post kit | PuckPulse";
  }, []);

  if (!day) return <main className="page"><p className="muted">No date in this link.</p></main>;
  if (status !== "ready" && !data) return <main className="page"><p className="muted">Loading…</p></main>;
  if (!data?.available) return <main className="page"><p className="muted">No Swing of the Night for {day}.</p></main>;

  const g = data.goal;
  const label = new Date(`${day}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
  const draft = `Swing of the Night (${label}): ${g.scorer || g.team} ${g.effect} with ${g.when}. ${g.team} went from ${pct(g.before)} to ${pct(g.after)} to win.`;
  const post = text ?? draft;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${post} ${link}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this", `${post} ${link}`);
    }
  };
  const save = async () => {
    try {
      const blob = await (await fetch(image)).blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `puckpulse-swing-${day}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      window.open(image, "_blank", "noopener");
    }
  };

  return (
    <main className="page post-kit">
      <div className="page-header"><h1>Today&apos;s post</h1></div>
      <img className="post-kit-card" src={image} alt={`Swing of the Night card: ${draft}`} />
      <label className="post-kit-label" htmlFor="post-kit-text">Post text <span>({post.length + 24} of 280 with the link)</span></label>
      <textarea id="post-kit-text" rows={4} value={post} onChange={(e) => setText(e.target.value)} />
      <div className="post-kit-actions">
        <a className="post-kit-primary" href={`https://x.com/intent/tweet?text=${encodeURIComponent(post)}&url=${encodeURIComponent(link)}`}
           target="_blank" rel="noopener noreferrer">Post on X</a>
        <button type="button" onClick={save}>Save image</button>
        <button type="button" onClick={copy}>{copied ? "Copied" : "Copy text"}</button>
      </div>
      <p className="muted post-kit-note">The link shows this card on X. Or save the image and attach it yourself.</p>
    </main>
  );
}
