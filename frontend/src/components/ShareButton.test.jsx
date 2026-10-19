import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import ShareButton from "./ShareButton.jsx";

describe("ShareButton", () => {
  afterEach(() => { delete navigator.share; });

  it("opens the share sheet with the game's preview link where there is one", async () => {
    navigator.share = vi.fn().mockResolvedValue();
    render(<ShareButton gameId={2026020150} title="PIT @ COL" />);
    await userEvent.click(screen.getByRole("button", { name: "Share this game" }));
    expect(navigator.share).toHaveBeenCalledWith({ title: "PIT @ COL", url: "https://puckpulse.io/g/2026020150" });
  });

  it("copies the link elsewhere", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<ShareButton gameId={2026020150} title="PIT @ COL" />);
    await userEvent.click(screen.getByRole("button", { name: "Share this game" }));
    expect(writeText).toHaveBeenCalledWith("https://puckpulse.io/g/2026020150");
    expect(await screen.findByText("Link copied")).toBeInTheDocument();
  });
});
