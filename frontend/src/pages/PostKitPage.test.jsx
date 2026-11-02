import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PostKitPage from "./PostKitPage.jsx";
import { clearResponseCache } from "../utils/responseCache.js";

const SWING = { available: true, date: "2026-10-24", goal: { scorer: "R. Rakell", team: "PIT", effect: "ties it",
  when: "1:06 left in the 3rd", before: 0.0706, after: 0.5473 } };
const UPSET = { available: true, story: "upset-2026020197", link: "https://puckpulse.io/g/2026020197",
  image: "https://api.test/og/game/2026020197.png", x_text: "VAN won 6-5 in OT at Anaheim with a 34% pregame chance.",
  reddit_title: "VAN steals one in Anaheim, 6-5 in OT", model: "Google Gemini" };

function serve(byPath) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const key = Object.keys(byPath).find((k) => url.includes(k));
    return { ok: true, json: async () => byPath[key] };
  });
}

const renderKit = () => render(
  <MemoryRouter initialEntries={["/post-kit?date=2026-10-24"]}><Routes><Route path="/post-kit" element={<PostKitPage />} /></Routes></MemoryRouter>,
);

describe("PostKitPage", () => {
  beforeEach(() => clearResponseCache());
  afterEach(() => vi.restoreAllMocks());

  it("without a draft, lays out Swing of the Night: card, text to tweak, and Post on X", async () => {
    serve({ "/post-kit/": { available: false }, "/swing-of-the-night": SWING });
    renderKit();
    const text = await screen.findByLabelText(/Post text/);
    expect(text).toHaveValue("Swing of the Night (Oct 24): R. Rakell ties it with 1:06 left in the 3rd. PIT went from 7% to 55% to win.");
    expect(screen.getByRole("img").getAttribute("src")).toMatch(/\/og\/swing\/2026-10-24\.png$/);
    const x = screen.getByRole("link", { name: "Post on X" }).getAttribute("href");
    expect(x).toContain("url=https%3A%2F%2Fpuckpulse.io%2Fs%2F2026-10-24");
    expect(x).toContain(encodeURIComponent("R. Rakell ties it"));
    expect(screen.queryByText("Reddit title")).not.toBeInTheDocument();
  });

  it("shows the agent's draft: its story's card and link, and a Reddit title", async () => {
    serve({ "/post-kit/": UPSET });
    renderKit();
    expect(await screen.findByLabelText(/Post text/)).toHaveValue(UPSET.x_text);
    expect(screen.getByRole("img").getAttribute("src")).toBe(UPSET.image);
    expect(screen.getByRole("link", { name: "Post on X" }).getAttribute("href")).toContain(encodeURIComponent(UPSET.link));
    expect(screen.getByText(UPSET.reddit_title)).toBeInTheDocument();
    const reddit = screen.getByRole("link", { name: "Post on Reddit" }).getAttribute("href");
    expect(reddit).toContain(`url=${encodeURIComponent(UPSET.link)}`);
    expect(reddit).toContain(`title=${encodeURIComponent(UPSET.reddit_title)}`);
    expect(screen.getByText(/Drafted by PuckPulse AI \(Google Gemini\)/)).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalledWith(expect.stringContaining("/swing-of-the-night"));
  });

  it("on the owner's device, records what was posted, as edited", async () => {
    localStorage.setItem("pp-creator-key", "abcdefghijklmnop1234");
    serve({ "/post-kit/": UPSET });
    renderKit();
    fireEvent.change(await screen.findByLabelText(/Post text/), { target: { value: "VAN steals it, 6-5 in OT." } });
    fireEvent.click(screen.getByRole("link", { name: "Post on X" }));
    const [url, init] = fetch.mock.calls.find(([u]) => u.includes("/actions"));
    expect(url).toMatch(/\/post-kit\/2026-10-24\/actions$/);
    expect(JSON.parse(init.body)).toEqual({ action: "posted_x", text: "VAN steals it, 6-5 in OT.", creator_key: "abcdefghijklmnop1234" });
    expect(screen.queryByText(/isn.t remembered/)).not.toBeInTheDocument();
    localStorage.clear();
  });

  it("on anyone else's device, records nothing and says so", async () => {
    serve({ "/post-kit/": UPSET });
    renderKit();
    fireEvent.click(await screen.findByRole("link", { name: "Post on X" }));
    expect(fetch.mock.calls.some(([u]) => u.includes("/actions"))).toBe(false);
    expect(screen.getByText(/isn.t remembered for future drafts/)).toBeInTheDocument();
  });

  it("a story without a card has no image or Save image", async () => {
    serve({ "/post-kit/": { ...UPSET, story: "odds-FLA", link: "https://puckpulse.io/t/FLA", image: null } });
    renderKit();
    await screen.findByLabelText(/Post text/);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save image" })).not.toBeInTheDocument();
  });
});
