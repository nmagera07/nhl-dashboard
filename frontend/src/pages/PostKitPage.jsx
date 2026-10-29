import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { API_BASE } from "../config.js";
import { useFetchWithStatus } from "../hooks/useFetchWithStatus.js";

const pct = (p) => `${Math.round(p * 100)}%`;

// The post as Swing of the Night alone would write it (when the drafting agent made nothing that morning).
function swingPost(day, swing) {
  const g = swing.goal;
  const label = new Date(`${day}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
  return {
    text: `Swing of the Night (${label}): ${g.scorer || g.team} ${g.effect} with ${g.when}. ${g.team} went from ${pct(g.before)} to ${pct(g.after)} to win.`,
    link: `https://puckpulse.io/s/${day}`,
    image: `${API_BASE}/og/swing/${day}.png`,
    reddit: null,
  };
}

async function copyText(value, done) {
  try {
    await navigator.clipboard.writeText(value);
    done();
  } catch {
    window.prompt("Copy this", value);
  }
}

// The morning post kit (opened from the creator's "Today's post is ready"
// notification): the drafting agent's post (post_drafts.py) or, without one,
// Swing of the Night: the card, the post text to tweak, one tap to post it on
// X, save the image, or copy the text, and a Reddit title. Not linked anywhere.
export default function PostKitPage() {
  const [params] = useSearchParams();
  const day = /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : null;
  const { data: kit, status: kitStatus } = useFetchWithStatus(day ? `${API_BASE}/post-kit/${day}` : null);
  const drafted = kit?.available ? kit : null;
  const checkedDraft = Boolean(kit) || kitStatus === "error";
  const { data: swing, status } = useFetchWithStatus(day && checkedDraft && !drafted ? `${API_BASE}/swing-of-the-night?date=${day}` : null);
  const [text, setText] = useState(null);
  const [copied, setCopied] = useState("");

  useEffect(() => {
    document.title = "Post kit | PuckPulse";
  }, []);

  if (!day) return <main className="page"><p className="muted">No date in this link.</p></main>;
  if (!checkedDraft || (!drafted && status !== "ready" && !swing)) return <main className="page"><p className="muted">Loading…</p></main>;
  const post = drafted
    ? { text: drafted.x_text, link: drafted.link, image: drafted.image, reddit: drafted.reddit_title }
    : swing?.available ? swingPost(day, swing) : null;
  if (!post) return <main className="page"><p className="muted">Nothing to post for {day}.</p></main>;

  const body = text ?? post.text;
  const flash = (what) => () => {
    setCopied(what);
    window.setTimeout(() => setCopied(""), 2000);
  };
  const save = async () => {
    try {
      const blob = await (await fetch(post.image)).blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `puckpulse-${day}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      window.open(post.image, "_blank", "noopener");
    }
  };

  return (
    <main className="page post-kit">
      <div className="page-header"><h1>Today&apos;s post</h1></div>
      {post.image && <img className="post-kit-card" src={post.image} alt={`Card for: ${post.text}`} />}
      <label className="post-kit-label" htmlFor="post-kit-text">Post text <span>({body.length + 24} of 280 with the link)</span></label>
      <textarea id="post-kit-text" rows={4} value={body} onChange={(e) => setText(e.target.value)} />
      <div className="post-kit-actions">
        <a className="post-kit-primary" href={`https://x.com/intent/tweet?text=${encodeURIComponent(body)}&url=${encodeURIComponent(post.link)}`}
           target="_blank" rel="noopener noreferrer">Post on X</a>
        {post.image && <button type="button" onClick={save}>Save image</button>}
        <button type="button" onClick={() => copyText(`${body} ${post.link}`, flash("post"))}>{copied === "post" ? "Copied" : "Copy text"}</button>
      </div>
      <p className="muted post-kit-note">
        {post.image ? "The link shows this card on X. Or save the image and attach it yourself." : "The link shows the page's preview on X."}
      </p>
      {post.reddit && (
        <section className="post-kit-reddit">
          <p className="post-kit-label">Reddit title</p>
          <p className="post-kit-reddit-title">{post.reddit}</p>
          <div className="post-kit-actions">
            <a href={`https://www.reddit.com/submit?url=${encodeURIComponent(post.link)}&title=${encodeURIComponent(post.reddit)}`}
               target="_blank" rel="noopener noreferrer">Post on Reddit</a>
            <button type="button" onClick={() => copyText(post.reddit, flash("reddit"))}>{copied === "reddit" ? "Copied" : "Copy title"}</button>
          </div>
        </section>
      )}
      {drafted && <p className="muted post-kit-note">Drafted by PuckPulse AI{drafted.model ? ` (${drafted.model})` : ""}. Check it before posting.</p>}
    </main>
  );
}
