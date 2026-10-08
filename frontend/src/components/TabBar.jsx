import { Link, useLocation } from "react-router-dom";
import { SECTIONS, sectionFor } from "./navSections.js";

const ICONS = {
  // Puck
  scores: (
    <>
      <ellipse cx="12" cy="10" rx="8" ry="3.5" />
      <path d="M4 10v4c0 1.9 3.6 3.5 8 3.5s8-1.6 8-3.5v-4" />
    </>
  ),
  // Ranked list
  standings: (
    <>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <path d="M4 6h1M4 12h1M4 18h1" />
    </>
  ),
  // Person
  players: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c.8-3.7 3.6-5.5 7-5.5s6.2 1.8 7 5.5" />
    </>
  ),
};

// Bottom navigation on phones, within thumb reach like a native app.
// Hidden on wider screens, where TopNav shows the same sections.
function TabBar() {
  const { pathname } = useLocation();
  const active = sectionFor(pathname);

  return (
    <nav className="tabbar" aria-label="Sections">
      {SECTIONS.map((section) => (
        <Link
          key={section.key}
          to={section.to}
          className={section.key === active ? "tabbar-item tabbar-item-active" : "tabbar-item"}
          aria-current={section.key === active ? "page" : undefined}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[section.key]}</svg>
          <span>{section.label}</span>
        </Link>
      ))}
    </nav>
  );
}

export default TabBar;
