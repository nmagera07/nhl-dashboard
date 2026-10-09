// Renders the small subset of Markdown the AI uses in answers: paragraphs,
// headings, bullet and numbered lists, **bold**, and `code`. Builds React
// elements directly (never innerHTML), so model output can't inject markup.

function inline(text, keyPrefix) {
  const parts = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    parts.push(token.startsWith("**") ? <strong key={key}>{token.slice(2, -2)}</strong> : <code key={key}>{token.slice(1, -1)}</code>);
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

const BULLET = /^\s*[*\-•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

export default function ChatMarkdown({ text }) {
  const blocks = [];
  let list = null;
  const flush = () => {
    if (list) blocks.push(list);
    list = null;
  };

  text.split("\n").forEach((rawLine, i) => {
    const line = rawLine.trimEnd();
    const bullet = line.match(BULLET);
    const numbered = !bullet && line.match(NUMBERED);
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        flush();
        list = { type, items: [] };
      }
      list.items.push((bullet || numbered)[1]);
      return;
    }
    flush();
    if (!line.trim()) return;
    const heading = line.match(HEADING);
    blocks.push(heading ? { type: "h", text: heading[1], i } : { type: "p", text: line, i });
  });
  flush();

  return (
    <div className="chat-markdown">
      {blocks.map((block, b) => {
        if (block.type === "ul" || block.type === "ol") {
          const List = block.type;
          return (
            <List key={b}>
              {block.items.map((item, j) => <li key={j}>{inline(item, `${b}-${j}`)}</li>)}
            </List>
          );
        }
        if (block.type === "h") return <p key={b} className="chat-markdown-heading"><strong>{inline(block.text.replace(/\*\*/g, ""), `${b}`)}</strong></p>;
        return <p key={b}>{inline(block.text, `${b}`)}</p>;
      })}
    </div>
  );
}
