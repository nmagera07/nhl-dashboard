// Phones fit all five tabs (four divisions and NHL) in one row with this short label.
const SHORT = { Metropolitan: "METRO" };

function DivisionTabs({ divisions, active, onSelect, disabled }) {
  return (
    <div className={disabled ? "division-tabs division-tabs-disabled" : "division-tabs"}>
      {divisions.map((div) => (
        <button
          key={div}
          className={div === active ? "division-tab division-tab-active" : "division-tab"}
          onClick={() => onSelect(div)}
          aria-label={SHORT[div] ? div.toUpperCase() : undefined}
          disabled={disabled}
        >
          {SHORT[div] ? (
            <>
              <span className="division-tab-long">{div.toUpperCase()}</span>
              <span className="division-tab-short">{SHORT[div]}</span>
            </>
          ) : div.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export default DivisionTabs;
