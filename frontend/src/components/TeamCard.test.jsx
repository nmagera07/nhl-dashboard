import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeamCard from "./TeamCard.jsx";

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

describe("TeamCard", () => {
  it("renders nothing when no team is selected", () => {
    const { container } = render(<TeamCard team={null} onViewRoster={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("top-3 in division counts as a playoff spot, regardless of wildcard standing", () => {
    render(<TeamCard team={team({ division_sequence: 3, wildcard_sequence: null })} onViewRoster={vi.fn()} />);
    expect(screen.getByText("IN PLAYOFF SPOT")).toBeInTheDocument();
  });

  it("outside top-3 in division but top-2 wildcard also counts as a playoff spot", () => {
    render(<TeamCard team={team({ division_sequence: 5, wildcard_sequence: 2 })} onViewRoster={vi.fn()} />);
    expect(screen.getByText("IN PLAYOFF SPOT")).toBeInTheDocument();
  });

  it("outside top-3 in division and outside top-2 wildcard is not a playoff spot", () => {
    render(<TeamCard team={team({ division_sequence: 5, wildcard_sequence: 3 })} onViewRoster={vi.fn()} />);
    expect(screen.getByText("OUTSIDE LOOKING IN")).toBeInTheDocument();
  });

  it("a null wildcard_sequence never qualifies on its own -- only division rank can", () => {
    render(<TeamCard team={team({ division_sequence: 4, wildcard_sequence: null })} onViewRoster={vi.fn()} />);
    expect(screen.getByText("OUTSIDE LOOKING IN")).toBeInTheDocument();
  });

  it("formats point percentage as a whole-number-plus-one-decimal string", () => {
    render(<TeamCard team={team({ point_pctg: 0.598 })} onViewRoster={vi.fn()} />);
    expect(screen.getByText(/59\.8%/)).toBeInTheDocument();
  });

  it("shows an em dash for a missing point percentage instead of NaN%", () => {
    render(<TeamCard team={team({ point_pctg: null })} onViewRoster={vi.fn()} />);
    expect(screen.getByText(/41-25-16 · —/)).toBeInTheDocument();
  });

  it("clicking View Roster calls onViewRoster with the team's abbreviation", async () => {
    const onViewRoster = vi.fn();
    render(<TeamCard team={team({ team_abbrev: "BOS" })} onViewRoster={onViewRoster} />);

    await userEvent.click(screen.getByRole("button", { name: /view roster/i }));

    expect(onViewRoster).toHaveBeenCalledWith("BOS");
  });
});
