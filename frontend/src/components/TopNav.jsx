function TopNav({ section, onNavigate, search, onSearchChange }) {
  return (
    <div className="topnav">
      <div className="brand">
        <span className="brand-dot" />
        <span className="brand-name">NHL Standings</span>
      </div>
      <div className="nav-tabs">
        <button
          className={section === "standings" ? "nav-tab nav-tab-active" : "nav-tab"}
          onClick={() => onNavigate("standings")}
        >
          Standings
        </button>
        <button
          className={section === "players" ? "nav-tab nav-tab-active" : "nav-tab"}
          onClick={() => onNavigate("players")}
        >
          Player Stats
        </button>
      </div>
      <div className="nav-right">
        {section === "standings" && (
          <input
            className="search-input"
            placeholder="Find a team..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        )}
        <span className="live-badge">
          <span className="live-dot" /> LIVE
        </span>
      </div>
    </div>
  );
}

export default TopNav;
