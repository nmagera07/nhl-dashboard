import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { glossaryEntry } from "../utils/statGlossary.js";

const TOOLTIP_WIDTH = 260;

// A stat abbreviation (xGF, GAA, PDO...) that explains itself: hover, focus,
// or tap it to see the full name and what it means. The tooltip renders in
// a portal with fixed positioning, so tables that scroll sideways (and clip
// their overflow) can't cut it off.
function StatAbbr({ term, children }) {
  const entry = glossaryEntry(term);
  const ref = useRef(null);
  const [position, setPosition] = useState(null);
  const id = useId();

  const open = () => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const left = Math.min(Math.max(8, rect.left + rect.width / 2 - TOOLTIP_WIDTH / 2), window.innerWidth - TOOLTIP_WIDTH - 8);
    setPosition({ top: rect.bottom + 8, left });
  };
  const close = () => setPosition(null);

  // A scroll or resize moves the abbreviation out from under the tooltip.
  useEffect(() => {
    if (!position) return undefined;
    const hide = () => setPosition(null);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [position]);

  const label = children ?? term;
  if (!entry) return label;

  return (
    <>
      <abbr
        ref={ref}
        className="stat-abbr"
        tabIndex={0}
        aria-describedby={position ? id : undefined}
        onMouseEnter={open}
        onMouseLeave={close}
        onFocus={open}
        onBlur={close}
        onClick={open} // taps on touch screens
        onKeyDown={(e) => e.key === "Escape" && close()}
      >
        {label}
      </abbr>
      {position &&
        createPortal(
          <span role="tooltip" id={id} className="stat-tooltip" style={{ top: position.top, left: position.left, width: TOOLTIP_WIDTH }}>
            <strong>{entry.name}</strong>
            {entry.detail && <span>{entry.detail}</span>}
          </span>,
          // Inside the app container, so it picks up the app's font and colors.
          document.querySelector(".dashboard") || document.body
        )}
    </>
  );
}

export default StatAbbr;
