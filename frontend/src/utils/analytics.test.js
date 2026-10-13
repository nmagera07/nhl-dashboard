import { track } from "./analytics.js";

describe("track", () => {
  afterEach(() => delete globalThis.umami);

  it("sends a named event when the tracker is loaded", () => {
    globalThis.umami = { track: vi.fn() };
    track("follow-team", { team: "PIT" });
    expect(globalThis.umami.track).toHaveBeenCalledWith("follow-team", { team: "PIT" });
  });

  it("is a no-op without the tracker, and never throws", () => {
    expect(() => track("ai-question")).not.toThrow();
    globalThis.umami = { track: () => { throw new Error("blocked"); } };
    expect(() => track("ai-question")).not.toThrow();
  });
});
