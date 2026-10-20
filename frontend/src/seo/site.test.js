import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { PAGES, SITEMAP_PATHS, TEAMS, sitemapXml, titleFor } from "./site.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

describe("sitemap", () => {
  it("public/sitemap.xml matches the route list (regenerate with sitemapXml() if this fails)", () => {
    expect(read("../../public/sitemap.xml")).toBe(sitemapXml());
  });

  it("lists every top-level page App.jsx routes and all 32 teams", () => {
    const app = read("../App.jsx");
    for (const { path } of PAGES) expect(app).toContain(`path="${path}"`);
    expect(Object.keys(TEAMS)).toHaveLength(32);
    expect(SITEMAP_PATHS).toContain("/teams/BUF");
    expect(SITEMAP_PATHS).not.toContain("/bets");
  });

  it("robots.txt allows all and points to the sitemap", () => {
    const robots = read("../../public/robots.txt");
    expect(robots).toMatch(/User-agent: \*\nAllow: \//);
    expect(robots).toContain("Sitemap: https://puckpulse.io/sitemap.xml");
  });

  it("the static site serves robots/sitemap as files and /t/* via the share function", () => {
    const config = JSON.parse(read("../../public/staticwebapp.config.json"));
    expect(config.navigationFallback.exclude.join(" ")).toMatch(/xml/);
    expect(config.routes).toContainEqual({ route: "/t/*", rewrite: "/api/share" });
  });

  it("the share function knows the same 32 teams", async () => {
    const { TEAMS: shareTeams } = await import("../../api/share/index.js");
    expect([...shareTeams].sort()).toEqual(Object.keys(TEAMS).sort());
  });
});

describe("titleFor", () => {
  it("names pages and teams", () => {
    expect(titleFor("/standings")).toBe("NHL Standings | PuckPulse");
    expect(titleFor("/teams/buf")).toBe("Buffalo Sabres playoff odds & stats | PuckPulse");
    expect(titleFor("/teams/XYZ")).toBe("PuckPulse: NHL scores, playoff odds, and an AI hockey analyst");
    expect(titleFor("/")).toBe("PuckPulse: NHL scores, playoff odds, and an AI hockey analyst");
    expect(titleFor("/games/2026020150")).toBe("Game | PuckPulse");
  });
});

describe("site-wide preview", () => {
  it("has no betting wording", () => {
    const html = read("../../index.html");
    const meta = html.match(/<meta[^>]+>/g).filter((t) => /description|og:|twitter:/.test(t)).join("\n");
    expect(meta).toContain("AI hockey analyst");
    expect(meta).not.toMatch(/bet|lines|fair odds|gambl/i);
  });
});
