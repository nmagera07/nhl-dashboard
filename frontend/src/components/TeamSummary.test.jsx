import { render, screen, within } from "@testing-library/react";
import TeamSummary from "./TeamSummary.jsx";

function team(overrides) {
  return {
    team_abbrev: "PIT",
    team_name: "Pittsburgh Penguins",
    division: "Metropolitan",
    logo_url: null,
    points: 98,
    wins: 41,
    losses: 25,
    ot_losses: 16,
    point_pctg: 0.598,
    home_wins: 20,
    home_losses: 13,
    road_wins: 21,
    road_losses: 12,
    l10_wins: 5,
    l10_losses: 5,
    l10_ot_losses: 0,
    division_sequence: 2,
    conference_sequence: 7,
    league_sequence: 10,
    wildcard_sequence: null,
    ...overrides,
  };
}

describe("TeamSummary", () => {
  it("renders nothing when no team is selected", () => {
    const { container } = render(<TeamSummary team={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("top-3 in division counts as a playoff spot, regardless of wildcard standing", () => {
    render(<TeamSummary team={team({ division_sequence: 3, wildcard_sequence: null })} />);
    expect(screen.getByText("In playoff spot")).toBeInTheDocument();
  });

  it("outside top-3 in division but top-2 wildcard also counts as a playoff spot", () => {
    render(<TeamSummary team={team({ division_sequence: 5, wildcard_sequence: 2 })} />);
    expect(screen.getByText("In playoff spot")).toBeInTheDocument();
  });

  it("outside top-3 in division and outside top-2 wildcard is not a playoff spot", () => {
    render(<TeamSummary team={team({ division_sequence: 5, wildcard_sequence: 3 })} />);
    expect(screen.getByText("Outside looking in")).toBeInTheDocument();
  });

  it("a null wildcard_sequence never qualifies on its own -- only division rank can", () => {
    render(<TeamSummary team={team({ division_sequence: 4, wildcard_sequence: null })} />);
    expect(screen.getByText("Outside looking in")).toBeInTheDocument();
  });

  it("formats point percentage as a whole-number-plus-one-decimal string", () => {
    render(<TeamSummary team={team({ point_pctg: 0.598 })} />);
    expect(screen.getByText(/59\.8%/)).toBeInTheDocument();
  });

  it("shows an em dash for a missing point percentage instead of NaN%", () => {
    render(<TeamSummary team={team({ point_pctg: null })} />);
    const pointPct = screen.getByText("Point %").closest("div");
    expect(within(pointPct).getByText("—")).toBeInTheDocument();
  });

  it("shows the season at a glance: points, record, differential, and home/road splits", () => {
    render(<TeamSummary team={team({ goal_differential: 12 })} />);

    expect(screen.getByRole("heading", { name: "Pittsburgh Penguins" })).toBeInTheDocument();
    expect(screen.getByText("98")).toBeInTheDocument();
    expect(screen.getByText("41-25-16")).toBeInTheDocument();
    expect(screen.getByText("+12")).toBeInTheDocument();
    expect(screen.getByText("20-13")).toBeInTheDocument();
    expect(screen.getByText("21-12")).toBeInTheDocument();
  });
});
