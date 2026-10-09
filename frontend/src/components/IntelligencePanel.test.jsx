import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IntelligencePanel from "./IntelligencePanel.jsx";

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
  await userEvent.click(screen.getByRole("button", { name: /ask nhl intelligence/i }));
  return screen.getByRole("dialog", { name: /nhl intelligence chat/i });
}

async function ask(text) {
  await userEvent.type(screen.getByRole("textbox", { name: /question for nhl intelligence/i }), text);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("IntelligencePanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens a drawer showing what it's asking about, with page-specific suggestions", async () => {
    render(<IntelligencePanel context={{ page: "game", game_id: 1 }} label="this game" />);

    const drawer = await open();

    expect(within(drawer).getByText("Asking about: this game")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "What was the turning point?" })).toBeInTheDocument();
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

    await userEvent.click(screen.getByRole("button", { name: "What was the turning point?" }));

    expect(await screen.findByText("It turned in the second.")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).message).toBe("What was the turning point?");
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

  it("starts a fresh conversation when the page changes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(answer("Team answer."));
    const { rerender } = render(<IntelligencePanel context={{ page: "team", team_abbrev: "PIT" }} label="Pittsburgh" />);
    await open();
    await ask("Hi");
    await screen.findByText("Team answer.");

    rerender(<IntelligencePanel context={{ page: "team", team_abbrev: "BOS" }} label="Boston" />);

    expect(screen.queryByText("Team answer.")).not.toBeInTheDocument();
    expect(screen.getByText("Asking about: Boston")).toBeInTheDocument();
  });

  it("shows the API's message when a request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "NHL Intelligence is taking a breather." }),
    });
    render(<IntelligencePanel context={{ page: "standings" }} label="the league" />);
    await open();

    await ask("Who leads?");

    expect(await screen.findByText("NHL Intelligence is taking a breather.")).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    render(<IntelligencePanel context={{ page: "standings" }} label="the league" />);
    await open();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask nhl intelligence/i })).toBeInTheDocument();
  });
});
