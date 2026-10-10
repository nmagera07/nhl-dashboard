import { Link, useLocation } from "react-router-dom";
import { SECTIONS, sectionFor } from "./navSections.js";

function TopNav({ search, onSearchChange }) {
  const { pathname } = useLocation();
  const active = sectionFor(pathname);

  return (
    <header className="topnav">
      <div className="topnav-inner">
        <Link className="brand" to="/" aria-label="PuckPulse home">
          <img className="brand-icon" src="/logo-mark.svg" alt="" />
          <span className="brand-name">Puck<span className="brand-accent">Pulse</span></span>
        </Link>
        {/* Desktop navigation; phones use the bottom TabBar instead. */}
        <nav className="nav-tabs" aria-label="Sections">
          {SECTIONS.map((section) => (
            <Link
              key={section.key}
              to={section.to}
              className={section.key === active ? "nav-tab nav-tab-active" : "nav-tab"}
              aria-current={section.key === active ? "page" : undefined}
            >
              {section.label}
            </Link>
          ))}
        </nav>
        {pathname === "/standings" && (
          <input
            className="search-input"
            placeholder="Find a team..."
            aria-label="Find a team"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        )}
      </div>
    </header>
  );
}

export default TopNav;
