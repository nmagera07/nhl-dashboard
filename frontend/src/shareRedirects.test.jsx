import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { CompareShareRedirect, SwingShareRedirect, TimeMachineShareRedirect } from "./App.jsx";
import { clearResponseCache } from "./utils/responseCache.js";

function Where() {
  const { pathname, search } = useLocation();
  return <p>at {pathname}{search}</p>;
}

const renderAt = (path) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/s/:day" element={<SwingShareRedirect />} />
      <Route path="/c/:pair" element={<CompareShareRedirect />} />
      <Route path="/tm/:spec" element={<TimeMachineShareRedirect />} />
      <Route path="*" element={<Where />} />
    </Routes>
  </MemoryRouter>,
);

// An installed app's service worker answers share links with the app shell, so the app forwards them itself.
describe("share links inside the installed app", () => {
  beforeEach(() => clearResponseCache());
  afterEach(() => vi.restoreAllMocks());

  it("a Swing of the Night link opens that night's game, with the moment", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ available: true, game: { id: 2026020172 } }) });
    renderAt("/s/2026-10-24");
    expect(await screen.findByText("at /games/2026020172?swing=2026-10-24")).toBeInTheDocument();
    expect(globalThis.fetch.mock.calls[0][0]).toMatch(/\/swing-of-the-night\?date=2026-10-24$/);
  });

  it("a night without a swing goes to Scores", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ available: false }) });
    renderAt("/s/2026-07-01");
    expect(await screen.findByText("at /")).toBeInTheDocument();
  });

  it("a comparison link opens the compare page", () => {
    renderAt("/c/8478402-8447400");
    expect(screen.getByText("at /compare?a=8478402&b=8447400")).toBeInTheDocument();
  });

  it("a time machine link opens that result", () => {
    renderAt("/tm/8447400-19851986-20252026");
    expect(screen.getByText("at /time-machine?player=8447400&season=19851986&target=20252026")).toBeInTheDocument();
  });

  it("a mangled time machine link opens the empty time machine", () => {
    renderAt("/tm/gretzky");
    expect(screen.getByText("at /time-machine")).toBeInTheDocument();
  });
});
