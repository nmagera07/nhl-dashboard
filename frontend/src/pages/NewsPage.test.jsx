import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import NewsPage from "./NewsPage.jsx";
import TopHeadlines from "../components/TopHeadlines.jsx";
import TeamNews from "../components/TeamNews.jsx";

const NEWS = {
  sources: ["ESPN", "NHL.com"],
  headlines: [
    { title: "Rangers lean on Garand", url: "https://espn.test/1", source: "ESPN", published: new Date().toISOString(), summary: "Two days after losing Shesterkin.", teams: ["NYR"] },
    { title: "Penguins respond", url: "https://nhl.test/2", source: "NHL.com", published: new Date().toISOString(), summary: "", teams: ["PIT"] },
  ],
};
const INJURIES = { source: "ESPN", teams: {
  PIT: [{ player: "Justin Brazeau", position: "RW", status: "Injured Reserve", injury: "Lower Body", expected_return: "2026-10-22", note: "Placed on IR Sunday." }],
  ANA: [{ player: "Ryan Poehling", position: "C", status: "Day-To-Day", injury: "Lower Body", expected_return: null, note: null }],
  BOS: [],
} };
const MOVES = { source: "ESPN", transactions: [{ date: "2026-10-11", team: "VGK", description: "Placed LW Victor Olofsson on injured reserve." }] };
const STANDINGS = [
  { team_abbrev: "PIT", team_name: "Pittsburgh Penguins" }, { team_abbrev: "ANA", team_name: "Anaheim Ducks" },
];

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
    const u = String(url);
    const body = u.includes("/injuries") ? INJURIES : u.includes("/transactions") ? MOVES : NEWS;
    return Promise.resolve({ json: async () => body });
  });
}

const renderIn = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("News", () => {
  afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

  it("lists headlines that open the original story, with source and summary", async () => {
    mockApi();
    renderIn(<NewsPage standings={STANDINGS} />);

    const link = await screen.findByRole("link", { name: "Rangers lean on Garand" });
    expect(link).toHaveAttribute("href", "https://espn.test/1");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("Two days after losing Shesterkin.")).toBeInTheDocument();
    expect(screen.getByText(/From ESPN, NHL.com/)).toBeInTheDocument();
  });

  it("shows injuries by team, favorite team first and open, others collapsed", async () => {
    localStorage.setItem("nhl-dash:favorite-team", "PIT");
    mockApi();
    renderIn(<NewsPage standings={STANDINGS} />);

    await userEvent.click(screen.getByRole("button", { name: "Injuries" }));

    const teams = await screen.findAllByText(/Pittsburgh Penguins|Anaheim Ducks/, { selector: ".injury-team-name" });
    expect(teams.map((t) => t.textContent)).toEqual(["Pittsburgh Penguins ★", "Anaheim Ducks"]); // yours first
    expect(teams.map((t) => t.closest("details").open)).toEqual([true, false]);
    expect(screen.getByText("Justin Brazeau")).toBeInTheDocument();
    expect(screen.getByText(/Lower Body · expected back Oct 22/)).toBeInTheDocument();
    expect(screen.queryByText("Boston Bruins")).not.toBeInTheDocument(); // no injuries, no row
  });

  it("shows transactions", async () => {
    mockApi();
    renderIn(<NewsPage standings={STANDINGS} />);

    await userEvent.click(screen.getByRole("button", { name: "Transactions" }));

    expect(await screen.findByText("Placed LW Victor Olofsson on injured reserve.")).toBeInTheDocument();
  });

  it("puts headlines on the Scores page", async () => {
    mockApi();
    renderIn(<TopHeadlines />);
    expect(await screen.findByRole("link", { name: "More news ›" })).toBeInTheDocument();
  });

  it("leaves the Scores page alone when news is down (and nothing was saved)", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("down"));
    const { container } = renderIn(<TopHeadlines />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });

  it("gives a team page its headlines and injury report", async () => {
    mockApi();
    renderIn(<TeamNews abbrev="PIT" />);

    expect(await screen.findByText("Latest news")).toBeInTheDocument();
    const injuries = within(screen.getByRole("region", { name: "Injuries" }));
    expect(injuries.getByText("Justin Brazeau")).toBeInTheDocument();
    expect(injuries.getByText("Injured Reserve")).toHaveClass("injury-status-ir");
  });
});
