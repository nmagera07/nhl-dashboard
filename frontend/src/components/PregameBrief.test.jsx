import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import PregameBrief from "./PregameBrief.jsx";

function mockBrief(body) {
  globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(body) }));
}

const BRIEF = {
  available: true,
  model: "Google Gemini",
  written_at: "2026-10-28T21:30:04Z",
  text: "- Tristan Jarry is **confirmed** for EDM.\n- EDM lists Zach Hyman (neck) on injured reserve.\n"
    + "- EDM is -180 at DraftKings, with a fair price of -166.",
};

describe("PregameBrief", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("is collapsed until opened, then shows the bullets as plain text", async () => {
    mockBrief(BRIEF);
    render(<PregameBrief gameId={2026020200} />);
    const summary = await screen.findByText("Pregame brief");
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining("/games/2026020200/brief"));
    expect(screen.getByText("Tristan Jarry is confirmed for EDM.")).not.toBeVisible();

    await userEvent.click(summary);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "Tristan Jarry is confirmed for EDM.",
      "EDM lists Zach Hyman (neck) on injured reserve.",
      "EDM is -180 at DraftKings, with a fair price of -166.",
    ]);
    expect(screen.getByText(/PuckPulse AI \(Google Gemini\)/)).toHaveTextContent(/not betting advice\. 21\+/);
  });

  it("stays hidden until a brief has been written", async () => {
    mockBrief({ available: false });
    const { container } = render(<PregameBrief gameId={2026020200} />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
