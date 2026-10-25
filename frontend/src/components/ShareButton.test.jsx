import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import ShareButton from "./ShareButton.jsx";

describe("ShareButton", () => {
  afterEach(() => { delete navigator.share; vi.restoreAllMocks(); });

  it("opens PuckPulse's share menu with links to each app, filled in", async () => {
    render(<ShareButton url="https://puckpulse.io/s/2026-10-24" title="Swing of the Night: Rakell ties it" label="Share" />);
    await userEvent.click(screen.getByRole("button", { name: "Share" }));

    const x = screen.getByRole("menuitem", { name: "Post on X" });
    expect(x).toHaveAttribute("href", "https://x.com/intent/tweet?text=Swing%20of%20the%20Night%3A%20Rakell%20ties%20it&url=https%3A%2F%2Fpuckpulse.io%2Fs%2F2026-10-24");
    expect(x).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("menuitem", { name: "Reddit" }).getAttribute("href")).toContain("reddit.com/submit?url=https%3A%2F%2Fpuckpulse.io%2Fs%2F2026-10-24");
    expect(screen.queryByRole("menuitem", { name: "More…" })).not.toBeInTheDocument(); // no system sheet here
  });

  it("copies the game's preview link", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<ShareButton gameId={2026020150} title="PIT @ COL" />);
    await userEvent.click(screen.getByRole("button", { name: "Share this game" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith("https://puckpulse.io/g/2026020150");
    expect(await screen.findByText("Link copied")).toBeInTheDocument();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("offers the game's card image and the phone's own sheet", async () => {
    navigator.share = vi.fn().mockResolvedValue();
    render(<ShareButton gameId={2026020150} title="PIT @ COL" />);
    await userEvent.click(screen.getByRole("button", { name: "Share this game" }));
    expect(screen.getByRole("menuitem", { name: "Save image" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "More…" }));
    expect(navigator.share).toHaveBeenCalledWith({ title: "PIT @ COL", url: "https://puckpulse.io/g/2026020150" });
  });

  it("closes on Escape", async () => {
    render(<ShareButton gameId={2026020150} title="PIT @ COL" />);
    await userEvent.click(screen.getByRole("button", { name: "Share this game" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
