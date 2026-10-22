import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act, fireEvent } from "@testing-library/react";
import IntelligencePanel from "./IntelligencePanel.jsx";
import { keyboardInsets } from "../hooks/useKeepAboveKeyboard.js";
import { resetWarmUp } from "../utils/warmUp.js";

const URL = "https://nhl-intelligence.bravecoast-a5240643.westus2.azurecontainerapps.io/chat/stream";

function sseStream(...events) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      events.forEach((e) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(e)}\n\n`)));
      controller.close();
    },
  });
}

function answer(text, model = "Groq") {
  return {
    ok: true,
    body: sseStream(
      { type: "delta", text },
      { type: "done", evidence: [{ label: "Team standings", endpoint: "/standings" }], model }
    ),
  };
}

async function open() {
  await userEvent.click(screen.getByRole("button", { name: /ask puckpulse/i }));
  return screen.getByRole("dialog", { name: /puckpulse ai chat/i });
}

async function ask(text) {
  await userEvent.type(screen.getByRole("textbox", { name: /question for puckpulse ai/i }), text);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("IntelligencePanel", () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens a drawer showing what it's asking about, with page-specific suggestions", async () => {
    render(<IntelligencePanel context={{ page: "game", game_id: 1 }} label="this game" />);

    const drawer = await open();

    expect(within(drawer).getByText("On: this game")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "How did this game go?" })).toBeInTheDocument();
  });

  it("builds the answer from streamed pieces, dropping text the model took back", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url) =>
      Promise.resolve(String(url).endsWith("/chat/stream")
        ? {
            ok: true,
            body: sseStream(
              { type: "delta", text: "Let me check." },
              { type: "reset" },
              { type: "status", text: "Checking the league leaders…" },
              { type: "delta", text: "Crosby leads " },
              { type: "delta", text: "with 9 points." },
              { type: "done", evidence: [], model: "Google Gemini" }
            ),
          }
        : { ok: true, json: async () => ({}) })
    );
    render(<IntelligencePanel context={{ page: "standings" }} label="the standings" />);
    await open();

    await ask("Who leads in points?");

    expect(await screen.findByText("Crosby leads with 9 points.")).toBeInTheDocument();
    expect(screen.queryByText(/let me check/i)).not.toBeInTheDocument();
  });

  it("sends the page context and shows the answer with its evidence and provider", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer("Chicago's record trails the leaders."));
    render(<IntelligencePanel context={{ page: "team", team_abbrev: "CHI" }} label="Chicago Blackhawks" />);
    await open();

    await ask("What stands out?");

    expect(await screen.findByText("Chicago's record trails the leaders.")).toBeInTheDocument();
    expect(screen.getByText("What stands out?")).toBeInTheDocument(); // the question stays in the thread
    expect(screen.getByText(/evidence: team standings/i)).toBeInTheDocument();
    expect(screen.getByText("Answered by Groq")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(URL, expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ message: "What stands out?", context: { page: "team", team_abbrev: "CHI" }, history: [] }),
    }));
  });

  it("a suggestion asks that question", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer("It turned in the second."));
    render(<IntelligencePanel context={{ page: "game", game_id: 1 }} label="this game" />);
    await open();

    await userEvent.click(screen.getByRole("button", { name: "How did this game go?" }));

    expect(await screen.findByText("It turned in the second.")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).message).toBe("How did this game go?");
  });

  it("sends earlier exchanges so follow-ups work", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(answer("They won 3-2."))
      .mockResolvedValueOnce(answer("Their power play went 1 for 3."));
    render(<IntelligencePanel context={{ page: "game", game_id: 1 }} label="this game" />);
    await open();

    await ask("How did it go?");
    await screen.findByText("They won 3-2.");
    await ask("What about the power play?");
    await screen.findByText("Their power play went 1 for 3.");

    expect(JSON.parse(fetchMock.mock.calls[1][1].body).history).toEqual([
      { role: "user", content: "How did it go?" },
      { role: "assistant", content: "They won 3-2." },
    ]);
  });

  it("renders bold text and bullet lists instead of raw markdown", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(answer("**Final:** TBL 3-2\n* Carlson scored twice\n* Hildeby made 34 saves"));
    render(<IntelligencePanel context={{ page: "standings" }} label="the league" />);
    await open();

    await ask("Summary?");

    expect(await screen.findByText("Final:", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Carlson scored twice", "Hildeby made 34 saves"]);
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it("keeps the conversation across pages, marking where the next answers come from", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(answer("Team answer.")).mockResolvedValueOnce(answer("Boston answer."));
    const { rerender } = render(<IntelligencePanel context={{ page: "team", team_abbrev: "PIT" }} label="Pittsburgh" />);
    await open();
    await ask("Hi");
    await screen.findByText("Team answer.");

    rerender(<IntelligencePanel context={{ page: "team", team_abbrev: "BOS" }} label="Boston" />);

    expect(screen.getByText("Team answer.")).toBeInTheDocument();
    expect(screen.getByText("Now on: Boston")).toBeInTheDocument();
    expect(screen.getByText("On: Boston")).toBeInTheDocument();
    await ask("And them?");
    await screen.findByText("Boston answer.");
    const sent = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(sent.context).toEqual({ page: "team", team_abbrev: "BOS" });
    expect(sent.history).toEqual([{ role: "user", content: "Hi" }, { role: "assistant", content: "Team answer." }]);  // no marker
  });

  it("survives a reload within the tab, and New chat clears it", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(answer("Saved answer."));
    const first = render(<IntelligencePanel context={{ page: "standings" }} label="Scores" />);
    await open();
    await ask("Who won?");
    await screen.findByText("Saved answer.");
    first.unmount();

    render(<IntelligencePanel context={{ page: "standings" }} label="Scores" />);
    await open();
    expect(screen.getByText("Saved answer.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("Saved answer.")).not.toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem("pp-chat-v1"))).toEqual([]);
  });

  it("when every provider is busy, counts down and tries once more", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({ ok: true, body: sseStream({ type: "error", message: "busy", retry_after: 1 }) })
      .mockResolvedValueOnce(answer("Second try worked."));
    render(<IntelligencePanel context={{ page: "standings" }} label="Scores" />);
    await open();

    await ask("Who won?");

    expect(await screen.findByText(/busy right now\. Trying again in 1s/)).toBeInTheDocument();
    expect(await screen.findByText("Second try worked.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("wakes the AI service soon after the page loads", async () => {
    vi.useFakeTimers();
    try {
      resetWarmUp();
      const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true });
      render(<IntelligencePanel context={{ page: "standings" }} label="Scores" />);
      expect(fetchMock).not.toHaveBeenCalled();

      await act(() => vi.advanceTimersByTimeAsync(2000));

      expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/nhl-intelligence.*\/health$/), expect.anything());
    } finally {
      vi.useRealTimers();
    }
  });

  it("says it's waking up when the first answer is slow", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.spyOn(globalThis, "fetch").mockImplementation((url) =>
        String(url).endsWith("/chat/stream") ? new Promise(() => {}) : Promise.resolve({ ok: true }));
      render(<IntelligencePanel context={{ page: "standings" }} label="Scores" />);
      await open();
      await ask("Who won?");
      expect(screen.getByText("Thinking…")).toBeInTheDocument();

      await act(() => vi.advanceTimersByTimeAsync(4000));

      expect(screen.getByText(/Waking up PuckPulse AI/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("starter questions fit the section and the reader's team", async () => {
    render(<IntelligencePanel context={{ page: "standings" }} label="Bets" topic="bets" favoriteTeamName="Penguins" />);
    await open();
    expect(screen.getByRole("button", { name: "Any value bets tonight?" })).toBeInTheDocument();
  });

  it("shows the API's message when a request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "PuckPulse AI is taking a breather." }),
    });
    render(<IntelligencePanel context={{ page: "standings" }} label="the league" />);
    await open();

    await ask("Who leads?");

    expect(await screen.findByText("PuckPulse AI is taking a breather.")).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    render(<IntelligencePanel context={{ page: "standings" }} label="the league" />);
    await open();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask puckpulse/i })).toBeInTheDocument();
  });

  it("shows what the agent is doing while it works", async () => {
    let finish;
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          const encoder = new TextEncoder();
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "status", text: "Simulating 2,000 seasons…" })}\n\n`));
          finish = () => {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "delta", text: "Odds rise to 73%." })}\n\n`));
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "done", evidence: [], model: "Gemini" })}\n\n`));
            controller.close();
          };
        },
      }),
    });
    render(<IntelligencePanel context={{ page: "team", team_abbrev: "PIT" }} label="Pittsburgh" />);
    await open();

    await ask("What if they win 4?");

    expect(await screen.findByRole("status")).toHaveTextContent("Simulating 2,000 seasons…");
    finish();
    expect(await screen.findByText("Odds rise to 73%.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("doesn't pull a reader who scrolled up back down while the answer streams", async () => {
    let more;
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          const encoder = new TextEncoder();
          const send = (e) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(e)}\n\n`));
          send({ type: "delta", text: "First part. " });
          more = () => { send({ type: "delta", text: "Second part." }); send({ type: "done", evidence: [], model: "Gemini" }); controller.close(); };
        },
      }),
    });
    render(<IntelligencePanel context={{ page: "standings" }} label="Standings" />);
    const drawer = await open();
    await ask("Who leads?");
    await screen.findByText(/First part/);

    const thread = drawer.querySelector(".intelligence-thread");
    Object.defineProperty(thread, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(thread, "clientHeight", { configurable: true, value: 300 });
    thread.scrollTop = 100; // the reader scrolls up to re-read
    fireEvent.scroll(thread);
    await act(async () => more());
    await screen.findByText(/Second part/);

    expect(thread.scrollTop).toBe(100);
  });

  it("the keyboard's covered strip and the visible height come from the visual viewport", () => {
    expect(keyboardInsets({ height: 330, offsetTop: 0 }, 664)).toEqual({ bottom: "334px", height: "330px" });
    // iOS also scrolls the page up: the covered strip shrinks by that much.
    expect(keyboardInsets({ height: 330, offsetTop: 120 }, 664)).toEqual({ bottom: "214px", height: "330px" });
    expect(keyboardInsets({ height: 664, offsetTop: 0 }, 664)).toEqual({ bottom: "0px", height: "664px" });
  });
});
