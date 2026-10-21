import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
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
});
