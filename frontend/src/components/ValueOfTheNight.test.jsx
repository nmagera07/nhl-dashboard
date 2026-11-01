import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import ValueOfTheNight from "./ValueOfTheNight.jsx";

const PICK = { game_id: 7, away: "PIT", home: "COL", market: "moneyline", side: "home", line: null, price: -150,
               book: "DraftKings", ev: 0.036, edge: 0.04, ours: 0.62, model: 0.66, market_prob: 0.58, value: true };
const RECORD = { nights: 13, wins: 7, losses: 6, pushes: 0, units: 3.16, value_nights: 4, beat_close: 5, clv_count: 12, clv: -0.009 };
const LAST = { pick: { ...PICK, away: "PHI", home: "WSH", market: "puck_line", line: -1.5, price: 110 }, result: { outcome: "win", units: 1.1 } };
const game = (state) => ({ id: 7, gameState: state });

const renderCard = (data, props = {}) => render(
  <ValueOfTheNight data={data} game={game("FUT")} today="2026-10-29" tracked={new Set()} onTrack={() => {}} {...props} />,
);

describe("ValueOfTheNight", () => {
  it("shows the pick, why, and the season's record", () => {
    renderCard({ available: true, pick: PICK, result: null, record: RECORD, last: LAST });
    expect(screen.getByText("Value of the night")).toBeInTheDocument();
    expect(screen.getByText("−150").closest("p")).toHaveTextContent("COL −150");
    expect(screen.getByText(/best at DraftKings/)).toHaveTextContent("To win · best at DraftKings · PIT @ COL");
    expect(screen.getByRole("img", { name: "Expected return +4%; value starts at +2%" })).toBeInTheDocument();
    expect(screen.getByText(/PuckPulse 62% vs. the books/)).toHaveTextContent("PuckPulse 62% vs. the books' 58%. Picked from the morning lines.");
    expect(screen.getByText("Season").nextSibling).toHaveTextContent("7-6");
    expect(screen.getByText("Units").nextSibling).toHaveTextContent("+3.16u");
    expect(screen.getByText("Beat the close").nextSibling).toHaveTextContent("5/12");
    expect(screen.getByText(/Last pick/)).toHaveTextContent("Last pick: WSH −1.5 +110, won.");
  });

  it("shares the night's /v/ link with its card", async () => {
    renderCard({ available: true, date: "2026-10-29", pick: PICK, record: RECORD });
    await userEvent.click(screen.getByRole("button", { name: "Share" }));
    const x = screen.getByRole("menuitem", { name: "Post on X" }).getAttribute("href");
    expect(x).toContain(encodeURIComponent("https://puckpulse.io/v/2026-10-29"));
    expect(x).toContain(encodeURIComponent("PuckPulse's value of the night: COL −150"));
  });

  it("labels a night without value as the closest", () => {
    renderCard({ available: true, pick: { ...PICK, value: false, ev: -0.01 }, record: RECORD });
    expect(screen.getByText("Closest to value tonight")).toBeInTheDocument();
    expect(screen.getByText(/Nothing cleared the value bar tonight/)).toBeInTheDocument();
  });

  it("fills the meter toward the +2% value bar, never past it or below empty", () => {
    const width = (ev) => {
      const { container, unmount } = renderCard({ available: true, pick: { ...PICK, value: false, ev }, record: RECORD });
      const w = container.querySelector(".votn-meter span").style.width;
      unmount();
      return w;
    };
    expect([width(0.008), width(0.05), width(-0.03)]).toEqual(["40%", "100%", "0%"]);
  });

  it("tracks the pick in My bets, until puck drop", async () => {
    const onTrack = vi.fn();
    const { rerender } = renderCard({ available: true, pick: PICK, record: RECORD }, { onTrack });
    await userEvent.click(screen.getByRole("button", { name: "Track" }));
    expect(onTrack).toHaveBeenCalledWith(expect.objectContaining({ id: "7:moneyline:home", date: "2026-10-29", price: -150 }));
    rerender(<ValueOfTheNight data={{ available: true, pick: PICK, record: RECORD }} game={game("LIVE")} today="2026-10-29" tracked={new Set()} onTrack={onTrack} />);
    expect(screen.queryByRole("button", { name: "Track" })).not.toBeInTheDocument();
  });

  it("is hidden without a morning snapshot", () => {
    const { container } = renderCard({ available: false });
    expect(container).toBeEmptyDOMElement();
  });
});
