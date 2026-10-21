import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import StandingsPage from "./StandingsPage.jsx";

function renderView(view) {
  return render(
    <MemoryRouter>
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
    </MemoryRouter>
  );
}

describe("StandingsPage", () => {
  it("says where the advanced stats come from", () => {
    renderView("advanced");
    expect(screen.getByText(/advanced stats .* from PuckPulse's own expected goals/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "MoneyPuck.com" })).not.toBeInTheDocument();
  });

  it("says the playoff odds use our own xG on the standard view", () => {
    renderView("standard");
    expect(screen.getByText(/playoff odds \(PO%\) blend goals with PuckPulse's own expected goals/i)).toBeInTheDocument();
  });

  it("links to the playoff race from the standard view", () => {
    renderView("standard");
    expect(screen.getByRole("link", { name: /see the playoff race/i })).toHaveAttribute("href", "/playoffs");
  });
});
