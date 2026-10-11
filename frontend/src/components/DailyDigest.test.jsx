import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DailyDigest from "./DailyDigest.jsx";
import { todayISO, shiftDate } from "../utils/dates.js";

const FACTS = {
  team_names: { PIT: "Penguins", CBJ: "Blue Jackets", STL: "Blues" },
  last_night: [{ away: "PIT", away_score: 2, home: "CBJ", home_score: 3, ended: "SO" }],
  playoff_odds_moves: { rising: [{ team: "CBJ", from_pct: 46.5, to_pct: 52.6, change: 6.1 }] },
  game_of_the_night: { away: "CBJ", home: "STL", time: "7:00 PM ET", model_home_win_pct: 50 },
};

function mockDigest(digest) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue({ json: async () => digest });
}

describe("DailyDigest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("shows today's AI-written digest and who wrote it", async () => {
    mockDigest({ digest_date: todayISO(), text: "**Columbus wins in a shootout.**\n### Last night\n- Blue Jackets 3, Penguins 2 (SO)", model: "Google Gemini", facts: FACTS });
    render(<DailyDigest />);

    expect(await screen.findByText("Columbus wins in a shootout.", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/written by google gemini/i)).toBeInTheDocument();
  });

  it("falls back to the facts when the AI couldn't write it", async () => {
    mockDigest({ digest_date: todayISO(), text: null, model: null, facts: FACTS });
    render(<DailyDigest />);

    expect(await screen.findByText("Penguins 2, Blue Jackets 3 (SO)")).toBeInTheDocument();
    expect(screen.getByText("Blue Jackets: 47% → 53%")).toBeInTheDocument();
    expect(screen.getByText(/game of the night: blue jackets at blues, 7:00 pm et \(the model gives the blues a 50% chance to win\)/i)).toBeInTheDocument();
    expect(screen.getByText(/straight from the data/i)).toBeInTheDocument();
  });

  it("hides a stale digest from an earlier day", async () => {
    mockDigest({ digest_date: shiftDate(todayISO(), -1), text: "Old news.", facts: FACTS });
    const { container } = render(<DailyDigest />);

    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });

  it("starts collapsed to its headline, so it doesn't push the scores down", async () => {
    mockDigest({ digest_date: todayISO(), text: "**Columbus wins in a shootout.**\n### Last night\n- Blue Jackets 3, Penguins 2 (SO)", model: "Gemini", facts: FACTS });
    const { container } = render(<DailyDigest />);

    const details = await screen.findByText("☀️ Morning digest").then((el) => el.closest("details"));
    expect(details).not.toHaveAttribute("open");
    expect(container.querySelector(".daily-digest-teaser")).toHaveTextContent("Columbus wins in a shootout.");
  });

  it("remembers that it was opened today", async () => {
    mockDigest({ digest_date: todayISO(), text: "**Headline.**", model: "Gemini", facts: FACTS });
    const first = render(<DailyDigest />);
    await userEvent.click(await screen.findByText("☀️ Morning digest"));
    expect(screen.getByText("☀️ Morning digest").closest("details")).toHaveAttribute("open");
    first.unmount();

    render(<DailyDigest />);

    expect((await screen.findByText("☀️ Morning digest")).closest("details")).toHaveAttribute("open");
  });

  it("uses the first result as the headline when the AI couldn't write it", async () => {
    mockDigest({ digest_date: todayISO(), text: null, facts: { ...FACTS, last_night: [{ ...FACTS.last_night[0], line: "Blue Jackets 3, Penguins 2 (SO)" }] } });
    const { container } = render(<DailyDigest />);

    await screen.findByText("☀️ Morning digest");
    expect(container.querySelector(".daily-digest-teaser")).toHaveTextContent("Blue Jackets 3, Penguins 2 (SO)");
  });
});
