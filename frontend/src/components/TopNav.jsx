import { Link, useLocation } from "react-router-dom";
import { SECTIONS, sectionFor } from "./navSections.js";

function ThemeToggle({ theme, toggle }) {
  const next = theme === "light" ? "dark" : "light";
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {theme === "light" ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
        ) : (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        )}
      </svg>
    </button>
  );
}

function TopNav({ search, onSearchChange, theme = "dark", onToggleTheme = () => {} }) {
  const { pathname } = useLocation();
  // Pick'em lives under Scores (and the phone tab bar), with its own link here on desktop.
  const onPickem = pathname.startsWith("/pickem");
  const active = onPickem ? "pickem" : sectionFor(pathname);

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
          <Link to="/pickem" className={onPickem ? "nav-tab nav-tab-active" : "nav-tab"} aria-current={onPickem ? "page" : undefined}>
            Pick&apos;em
          </Link>
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
        <ThemeToggle theme={theme} toggle={onToggleTheme} />
      </div>
    </header>
  );
}

export default TopNav;
