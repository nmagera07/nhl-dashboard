import { render, screen } from "@testing-library/react";
import StandingsPage from "./StandingsPage.jsx";

function renderView(view) {
  return render(
    <StandingsPage
      divisions={["Metropolitan"]}
      activeDivision="Metropolitan"
      onSelectDivision={vi.fn()}
      isSearching={false}
      visibleRows={[]}
      onSelectTeam={vi.fn()}
      playoffOddsByTeam={{}}
      playoffOddsStatus="ready"
      view={view}
      onViewChange={vi.fn()}
      sortBy={null}
      sortDir="desc"
      onSort={vi.fn()}
    />
  );
}

describe("StandingsPage", () => {
  // MoneyPuck's data is free for non-commercial use on condition of credit.
  it("credits MoneyPuck wherever its advanced stats are shown", () => {
    renderView("advanced");
    expect(screen.getByRole("link", { name: "MoneyPuck.com" })).toHaveAttribute("href", "https://moneypuck.com");
  });

  it("doesn't show the credit on the standard view, which has no MoneyPuck data", () => {
    renderView("standard");
    expect(screen.queryByText(/MoneyPuck/)).not.toBeInTheDocument();
  });
});
