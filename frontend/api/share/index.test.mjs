import { afterEach, describe, expect, it, vi } from "vitest";
import { createRequire } from "node:module";

const share = createRequire(import.meta.url)("./index.js");

async function run(originalUrl, apiBody) {
  const fetch = vi.fn(async () => ({ ok: Boolean(apiBody), json: async () => apiBody }));
  vi.stubGlobal("fetch", fetch);
  const context = { log: { warn: vi.fn() }, res: null };
  await share(context, { headers: { "x-ms-original-url": `https://puckpulse.io${originalUrl}` }, params: {}, query: {} });
  return { html: context.res.body, fetch };
}

afterEach(() => vi.unstubAllGlobals());

describe("share function", () => {
  it("serves a team card for /t/BUF and sends people to the team page", async () => {
    const { html, fetch } = await run("/t/buf", { title: "Buffalo Sabres: 17.7% to make the playoffs", description: "3-3-0, 6 pts.", url: "https://puckpulse.io/teams/BUF" });
    expect(fetch.mock.calls[0][0]).toMatch(/\/teams\/BUF\/share$/);
    expect(html).toContain('property="og:title" content="Buffalo Sabres: 17.7% to make the playoffs"');
    expect(html).toContain('content="0; url=https://puckpulse.io/teams/BUF"');
    expect(html).toContain('property="og:image" content="https://puckpulse.io/og-card.png"');
  });

  it("never lets the API's response change where the link goes", async () => {
    const { html } = await run("/g/2026020152", { title: "PHI @ BUF", description: "x", url: "https://evil.example/phish",
                                                   image: "https://evil.example/x.png" });
    expect(html).toContain('content="0; url=https://puckpulse.io/games/2026020152"');
    expect(html).not.toContain("evil.example");
    expect(html).toContain('property="og:title" content="PHI @ BUF"');
  });

  it("escapes text from the API", async () => {
    const { html } = await run("/g/2026020152", { title: '"><script>alert(1)</script>', description: "a & b" });
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&quot;&gt;&lt;script&gt;");
  });

  it("falls back to the generic card for an unknown team, without calling the API", async () => {
    const { html, fetch } = await run("/t/XYZ");
    expect(fetch).not.toHaveBeenCalled();
    expect(html).toContain("PuckPulse: NHL scores, playoff odds, and an AI hockey analyst");
    expect(html).toContain('url=https://puckpulse.io"');
    expect(html).not.toMatch(/bet|fair odds/i);
  });

  it("still serves game cards for /g/{id}", async () => {
    const { html, fetch } = await run("/g/2026020150", { title: "PIT @ COL", description: "x", url: "https://puckpulse.io/games/2026020150" });
    expect(fetch.mock.calls[0][0]).toMatch(/\/games\/2026020150\/share$/);
    expect(html).toContain("url=https://puckpulse.io/games/2026020150");
  });

  it("serves Swing of the Night for /s/{date} and sends people to that game", async () => {
    const { html, fetch } = await run("/s/2026-10-20", {
      title: "Swing of the Night, Oct 20: A. DeBrincat ties it with 0:17 left in the 3rd", description: "DET @ SEA",
      game_id: 2026020149, image: "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io/og/swing/2026-10-20.png" });
    expect(fetch.mock.calls[0][0]).toMatch(/\/swing\/2026-10-20\/share$/);
    expect(html).toContain("ties it with 0:17 left");
    expect(html).toContain('content="0; url=https://puckpulse.io/games/2026020149"');
    expect(html).toContain("/og/swing/2026-10-20.png");
  });

  it("only sends a swing link to one of our own game pages", async () => {
    const { html } = await run("/s/2026-10-20", { title: "x", description: "y", game_id: "../evil" });
    expect(html).toContain('url=https://puckpulse.io"');
    const bad = await run("/s/not-a-date");
    expect(bad.fetch).not.toHaveBeenCalled();
  });

  it("serves a comparison card for /c/{a}-{b} and opens the compare page", async () => {
    const { html, fetch } = await run("/c/8478402-8447400", { title: "McDavid vs Gretzky: who's better?", description: "x",
      url: "https://evil.example", image: "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io/og/compare/8478402-8447400.png" });
    expect(fetch.mock.calls[0][0]).toMatch(/\/compare\/8478402\/8447400\/share$/);
    expect(html).toContain("McDavid vs Gretzky: who&#39;s better?");
    expect(html).toContain('content="0; url=https://puckpulse.io/compare?a=8478402&amp;b=8447400"');
    expect(html).not.toContain("evil.example");
  });
});
