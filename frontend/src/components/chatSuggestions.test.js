import { describe, it, expect } from "vitest";
import { suggestionsFor } from "./chatSuggestions.js";

describe("suggestionsFor", () => {
  it("leads the scores page with last night and tonight, then the reader's team", () => {
    expect(suggestionsFor({ page: "standings", topic: "scores", team: "Penguins" }))
      .toEqual(["Who won last night?", "What's on tonight, and who's favored?", "How are the Penguins doing?"]);
  });

  it("falls back to a league question without a favorite team", () => {
    expect(suggestionsFor({ page: "standings", topic: "scores" })[2]).toBe("Who's the best goalie this season?");
    expect(suggestionsFor({ page: "standings", topic: "standings" })[0]).toBe("Who's in the wild-card race?");
  });

  it("fits each section and page", () => {
    expect(suggestionsFor({ page: "standings", topic: "bets" })[0]).toBe("Any value bets tonight?");
    expect(suggestionsFor({ page: "standings", topic: "news", team: "Penguins" })[2]).toBe("Who's injured on the Penguins?");
    expect(suggestionsFor({ page: "team" })[0]).toMatch(/in goal tonight/);
    expect(suggestionsFor({ page: "game" })).toHaveLength(3);
  });
});
