import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PostKitPage from "./PostKitPage.jsx";
import { clearResponseCache } from "../utils/responseCache.js";

const SWING = { available: true, date: "2026-10-24", goal: { scorer: "R. Rakell", team: "PIT", effect: "ties it",
  when: "1:06 left in the 3rd", before: 0.0706, after: 0.5473 } };

describe("PostKitPage", () => {
  beforeEach(() => clearResponseCache());
  afterEach(() => vi.restoreAllMocks());

  it("lays out the post: card, text to tweak, and Post on X", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => SWING });
    render(<MemoryRouter initialEntries={["/post-kit?date=2026-10-24"]}><Routes><Route path="/post-kit" element={<PostKitPage />} /></Routes></MemoryRouter>);
    const text = await screen.findByLabelText(/Post text/);
    expect(text).toHaveValue("Swing of the Night (Oct 24): R. Rakell ties it with 1:06 left in the 3rd. PIT went from 7% to 55% to win.");
    expect(screen.getByRole("img").getAttribute("src")).toMatch(/\/og\/swing\/2026-10-24\.png$/);
    const x = screen.getByRole("link", { name: "Post on X" }).getAttribute("href");
    expect(x).toContain("url=https%3A%2F%2Fpuckpulse.io%2Fs%2F2026-10-24");
    expect(x).toContain(encodeURIComponent("R. Rakell ties it"));
  });
});
