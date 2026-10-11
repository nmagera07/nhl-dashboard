import { resetWarmUp, warmUpChat } from "./warmUp.js";

describe("warmUpChat", () => {
  beforeEach(() => resetWarmUp());

  it("pings both backends, at most once every few minutes", () => {
    const fetchImpl = vi.fn(() => Promise.resolve({}));

    expect(warmUpChat(0, fetchImpl)).toBe(true);
    expect(fetchImpl.mock.calls.map(([url]) => url)).toEqual([
      expect.stringMatching(/nhl-intelligence.*\/health$/),
      expect.stringMatching(/\/health$/),
    ]);
    expect(warmUpChat(60_000, fetchImpl)).toBe(false);
    expect(warmUpChat(5 * 60_000, fetchImpl)).toBe(true);
    expect(fetchImpl).toHaveBeenCalledTimes(4);
  });

  it("never throws when a ping fails", async () => {
    const fetchImpl = vi.fn(() => Promise.reject(new Error("offline")));
    expect(() => warmUpChat(0, fetchImpl)).not.toThrow();
    await Promise.resolve();
  });
});
