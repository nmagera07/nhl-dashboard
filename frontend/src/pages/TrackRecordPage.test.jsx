import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TrackRecordPage from "./TrackRecordPage.jsx";

const RECORD = {
  games: 14, picks: 13, favorite_correct: 10, favorite_won: 0.7692, brier: 0.2212, coin_flip_brier: 0.25, pending: 3,
  calibration: [
    { label: "50-55%", games: 6, predicted: 0.525, actual: 0.6667 },
    { label: "65%+", games: 1, predicted: 0.69, actual: 0 },
  ],
  recent: [
    { game_id: 83, game_date: "2026-10-10", home: "VGK", away: "LAK", home_win_prob: 0.62, home_score: 2, away_score: 1, ended: "OT", favorite_won: true },
    { game_id: 81, game_date: "2026-10-10", home: "CHI", away: "CAR", home_win_prob: 0.37, home_score: 2, away_score: 5, ended: "REG", favorite_won: true },
    { game_id: 80, game_date: "2026-10-10", home: "COL", away: "TOR", home_win_prob: 0.69, home_score: 3, away_score: 6, ended: "REG", favorite_won: false },
    { game_id: 79, game_date: "2026-10-10", home: "STL", away: "CBJ", home_win_prob: 0.5, home_score: 5, away_score: 3, ended: "REG", favorite_won: null },
  ],
};

function renderWith(body) {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) });
  render(<MemoryRouter><TrackRecordPage /></MemoryRouter>);
}

describe("TrackRecordPage", () => {
  it("shows the scorecard with counts, Brier vs a coin flip, and a small-sample warning", async () => {
    renderWith(RECORD);

    expect(await screen.findByText("77%")).toBeInTheDocument();
    expect(screen.getByText("10 of 13 games")).toBeInTheDocument();
    expect(screen.getByText("0.221")).toBeInTheDocument();
    expect(screen.getByText("Coin flip: 0.250 · lower is better")).toBeInTheDocument();
    expect(screen.getByText("3 waiting on results")).toBeInTheDocument();
    expect(screen.getByText(/Early days: with only 14 games/)).toBeInTheDocument();
  });

  it("draws calibration bars at what happened, with a marker at what the model said", async () => {
    renderWith(RECORD);

    const bar = await screen.findByRole("img", { name: "Said 53%, favorite won 67% of 6 games" });
    expect(bar.querySelector(".calibration-fill").style.width).toBe("67%");
    expect(bar.querySelector(".calibration-marker").style.left).toBe("53%");
    expect(screen.getByText("Said 69% · won 0% · 1 game")).toBeInTheDocument();
  });

  it("lists recent picks from the favorite's side, linked to the game", async () => {
    renderWith(RECORD);

    await screen.findByText("Recent picks");
    const rows = screen.getAllByRole("link").filter((a) => a.classList.contains("pick-row"));
    expect(rows.map((r) => within(r).getByText(/%|Toss-up/).textContent)).toEqual(["VGK 62%", "CAR 63%", "COL 69%", "Toss-up"]);
    expect(rows[0]).toHaveAttribute("href", "/games/83");
    expect(within(rows[0]).getByText("LAK 1, VGK 2 (OT)")).toBeInTheDocument();
    expect(within(rows[2]).getByLabelText("wrong")).toHaveTextContent("✗");
    expect(within(rows[3]).getByLabelText("no pick")).toHaveTextContent("–");
  });

  it("explains that nothing is graded yet", async () => {
    renderWith({ games: 0, picks: 0, favorite_correct: 0, favorite_won: null, brier: null, coin_flip_brier: 0.25, calibration: [], recent: [], pending: 5 });

    expect(await screen.findByText(/No graded games yet/)).toBeInTheDocument();
  });

  it("shows an error when the API fails", async () => {
    renderWith({ detail: "Internal Server Error" });

    expect(await screen.findByText("Couldn't load the track record.")).toBeInTheDocument();
  });
});
