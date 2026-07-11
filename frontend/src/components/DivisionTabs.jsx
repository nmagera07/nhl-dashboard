function DivisionTabs({ divisions, active, onSelect, disabled }) {
  return (
    <div className={disabled ? "division-tabs division-tabs-disabled" : "division-tabs"}>
      {divisions.map((div) => (
        <button
          key={div}
          className={div === active ? "division-tab division-tab-active" : "division-tab"}
          onClick={() => onSelect(div)}
          disabled={disabled}
        >
          {div.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

export default DivisionTabs;
