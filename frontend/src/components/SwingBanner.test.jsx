import { render, screen } from "@testing-library/react";
import SwingBanner from "./SwingBanner.jsx";
import { goalClip } from "../utils/highlights.js";

const SCORING = [
  { periodDescriptor: { number: 2 }, goals: [{ timeInPeriod: "05:00", highlightClipSharingUrl: "https://www.nhl.com/video/early" }] },
  { periodDescriptor: { number: 3 }, goals: [{ timeInPeriod: "18:54", highlightClipSharingUrl: "https://www.nhl.com/video/rakell-ties-it" },
                                             { timeInPeriod: "19:30", highlightClipSharingUrl: "https://evil.example/video/x" }] },
];
const SWING = { date: "2026-10-24", game: { id: 2026020172 },
  goal: { scorer: "R. Rakell", team: "PIT", side: "home", second: 2400 + 1134, when: "1:06 left in the 3rd", effect: "ties it", before: 0.0706, after: 0.5473 } };

describe("SwingBanner", () => {
  it("finds the goal's clip by period and time (nhl.com links only)", () => {
    expect(goalClip(SCORING, 2400 + 1134)).toBe("https://www.nhl.com/video/rakell-ties-it");
    expect(goalClip(SCORING, 1500)).toBe("https://www.nhl.com/video/early");
    expect(goalClip(SCORING, 2400 + 1170)).toBeNull(); // not an nhl.com link
    expect(goalClip(SCORING, 100)).toBeNull();
  });

  it("tells the moment, links the clip, and jumps to the chart", () => {
    const onShowChart = vi.fn();
    render(<SwingBanner swing={SWING} game={{ id: 2026020172, summary: { scoring: SCORING } }} onShowChart={onShowChart} />);
    expect(screen.getByText("R. Rakell ties it with 1:06 left in the 3rd")).toBeInTheDocument();
    expect(screen.getByText("PIT went from 7% to 55% to win")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "▶ Watch the goal" })).toHaveAttribute("href", "https://www.nhl.com/video/rakell-ties-it");
    screen.getByRole("button", { name: "See it on the chart" }).click();
    expect(onShowChart).toHaveBeenCalled();
  });
});
