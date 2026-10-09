import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatAbbr from "./StatAbbr.jsx";
import StatGlossary from "./StatGlossary.jsx";

describe("StatAbbr", () => {
  it("explains the stat on hover", async () => {
    render(<StatAbbr term="xGF" />);

    await userEvent.hover(screen.getByText("xGF"));

    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("Expected goals for");
    expect(tip).toHaveTextContent(/shot location/);
    expect(screen.getByText("xGF")).toHaveAttribute("aria-describedby", tip.id);

    await userEvent.unhover(screen.getByText("xGF"));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("works from the keyboard, and Escape closes it", async () => {
    render(<StatAbbr term="GAA" />);

    await userEvent.tab();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Goals against average");

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("can show a different label for a context-specific term", async () => {
    render(<StatAbbr term="TEAM_PTS">PTS</StatAbbr>);

    await userEvent.hover(screen.getByText("PTS"));

    expect(screen.getByRole("tooltip")).toHaveTextContent("2 for a win");
  });

  it("renders unknown terms as plain text", () => {
    render(<StatAbbr term="ZZZ" />);
    expect(screen.getByText("ZZZ").tagName).not.toBe("ABBR");
  });
});

describe("StatGlossary", () => {
  it("lists every term on the page, collapsed until opened", async () => {
    render(<StatGlossary terms={["GF", "PDO", "TEAM_L", "ZZZ"]} labels={{ TEAM_L: "L" }} />);

    const summary = screen.getByText("What do these stats mean?");
    expect(screen.getByText("Goals for").closest("details")).not.toHaveAttribute("open");

    await userEvent.click(summary);

    expect(screen.getByText("Goals for").closest("details")).toHaveAttribute("open");
    expect(screen.getAllByRole("term").map((t) => t.textContent)).toEqual(["GF", "PDO", "L"]);
  });
});
