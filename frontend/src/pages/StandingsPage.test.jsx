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
  // MoneyPuck's data is free for non-commercial use on condition of credit.
  it("credits MoneyPuck wherever its advanced stats are shown", () => {
    renderView("advanced");
    expect(screen.getByRole("link", { name: "MoneyPuck.com" })).toHaveAttribute("href", "https://moneypuck.com");
  });

  it("credits MoneyPuck on the standard view too, since playoff odds use its xG", () => {
    renderView("standard");
    expect(screen.getByText(/playoff odds \(PO%\) blend goals with expected goals/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "MoneyPuck.com" })).toBeInTheDocument();
  });

  it("links to the playoff race from the standard view", () => {
    renderView("standard");
    expect(screen.getByRole("link", { name: /see the playoff race/i })).toHaveAttribute("href", "/playoffs");
  });
});
