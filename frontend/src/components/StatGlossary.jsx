import { glossaryEntry } from "../utils/statGlossary.js";

// "What do these stats mean?" -- the full list for a page, collapsed by
// default. The tap-friendly counterpart to the hover tooltips on phones.
function StatGlossary({ terms, labels = {} }) {
  const entries = terms.map((term) => [term, glossaryEntry(term)]).filter(([, entry]) => entry);
  if (!entries.length) return null;
  return (
    <details className="stat-glossary">
      <summary>What do these stats mean?</summary>
      <dl>
        {entries.map(([term, entry]) => (
          <div key={term}>
            <dt>{labels[term] || term}</dt>
            <dd>
              <strong>{entry.name}</strong>
              {entry.detail && <> — {entry.detail}</>}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export default StatGlossary;
