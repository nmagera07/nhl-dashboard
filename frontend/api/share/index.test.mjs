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
});
