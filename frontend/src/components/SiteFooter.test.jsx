import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import SiteFooter from "./SiteFooter.jsx";

describe("SiteFooter", () => {
  it("credits Nate with his profiles, opening in a new tab", () => {
    render(<SiteFooter />);
    expect(screen.getByRole("link", { name: "Nate Magera" })).toHaveAttribute("href", "https://www.linkedin.com/in/nate-magera");
    for (const [label, href] of [["LinkedIn", "https://www.linkedin.com/in/nate-magera"], ["X", "https://x.com/natemagera"],
      ["GitHub", "https://github.com/nmagera07"]]) {
      const link = screen.getByRole("link", { name: `Nate Magera on ${label}` });
      expect(link).toHaveAttribute("href", href);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link.getAttribute("rel")).toContain("noopener");
    }
    expect(screen.getByText(/Not affiliated with or endorsed by the NHL/)).toBeInTheDocument();
  });

  it("says it's an Atelier AI project", () => {
    render(<SiteFooter />);
    expect(screen.getByRole("link", { name: "Atelier AI" })).toHaveAttribute("href", "https://github.com/atelier-ai-labs");
  });

  describe("feedback", () => {
    afterEach(() => vi.restoreAllMocks());

    it("sends an idea with the page it came from, then thanks you", async () => {
      const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
      render(<SiteFooter />);
      await userEvent.click(screen.getByRole("button", { name: "Suggest a feature or report a bug" }));

      const dialog = screen.getByRole("dialog", { name: "Send feedback" });
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      await userEvent.type(screen.getByLabelText(/your idea/i), "A playoff bracket view");
      await userEvent.type(screen.getByLabelText(/how to reach you/i), "@fan");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));

      expect(await screen.findByText("Thanks!")).toBeInTheDocument();
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toMatch(/\/feedback$/);
      expect(JSON.parse(init.body)).toEqual({ kind: "idea", message: "A playoff bracket view", contact: "@fan", page: "/", website: null });
      expect(dialog).toBeInTheDocument();
    });

    it("can switch to a bug report, shows errors, and closes on Escape", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, status: 429, json: async () => ({}) });
      render(<SiteFooter />);
      await userEvent.click(screen.getByRole("button", { name: "Suggest a feature or report a bug" }));
      await userEvent.click(screen.getByRole("button", { name: "Report a bug" }));
      await userEvent.type(screen.getByLabelText(/your bug report/i), "Scores page is blank");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/try again in a bit/i);
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
