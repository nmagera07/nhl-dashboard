import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IntelligencePanel from "./IntelligencePanel.jsx";

describe("IntelligencePanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends the current page context and displays a grounded answer", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "Chicago's recent record trails the division leaders.",
        evidence: [{ label: "Team standings", endpoint: "/standings/CHI" }],
      }),
    });

    render(<IntelligencePanel context={{ page: "team", team_abbrev: "CHI" }} />);
    await userEvent.click(screen.getByRole("button", { name: /ask nhl intelligence/i }));
    await userEvent.type(
      screen.getByRole("textbox", { name: /question for nhl intelligence/i }),
      "What stands out?"
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/recent record trails/i)).toBeInTheDocument();
    expect(screen.getByText(/evidence: team standings/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "https://nhl-intelligence-kaxll7b4fq-uk.a.run.app/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          message: "What stands out?",
          context: { page: "team", team_abbrev: "CHI" },
        }),
      })
    );
  });

  it("shows the API detail when a request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "The dashboard API is unavailable." }),
    });

    render(<IntelligencePanel context={{ page: "standings" }} />);
    await userEvent.click(screen.getByRole("button", { name: /ask nhl intelligence/i }));
    await userEvent.type(
      screen.getByRole("textbox", { name: /question for nhl intelligence/i }),
      "Who leads?"
    );
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("The dashboard API is unavailable.")).toBeInTheDocument();
  });
});
