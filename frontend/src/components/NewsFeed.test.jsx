import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import NewsFeed from "./NewsFeed.jsx";

const story = (n, extra = {}) => ({ title: `Story ${n}`, url: `https://nhl.test/${n}`, source: "NHL.com",
                                    published: new Date().toISOString(), summary: `Summary ${n}`, teams: ["PIT"], ...extra });

describe("NewsFeed", () => {
  it("leads with the top story's big photo and summary, then cards with thumbnails", () => {
    const { container } = render(<NewsFeed headlines={[
      story(1, { image: "https://media.d3.nhle.com/big.jpg", thumb: "https://media.d3.nhle.com/small.jpg" }),
      story(2, { thumb: "https://media.d3.nhle.com/small2.jpg" }),
      story(3, { teams: ["PIT", "COL", "NYR", "TOR"] }),
    ]} />);
    expect(container.querySelector(".feed-lead-photo")).toHaveAttribute("src", "https://media.d3.nhle.com/big.jpg");
    expect(screen.getByText("Summary 1")).toBeInTheDocument();
    expect(screen.queryByText("Summary 2")).not.toBeInTheDocument();  // the list stays titles only
    expect(container.querySelectorAll(".feed-item-photo")).toHaveLength(1);  // story 3 has no photo
    expect(screen.getByText("+1")).toBeInTheDocument();  // more than 3 teams collapse
    expect(screen.getByRole("link", { name: /^Story 2/ })).toHaveAttribute("target", "_blank");
  });

  it("says so when there are no headlines", () => {
    render(<NewsFeed headlines={[]} />);
    expect(screen.getByText("No headlines right now.")).toBeInTheDocument();
  });
});
