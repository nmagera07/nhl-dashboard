import { startChatTimer } from "./chatTiming.js";

describe("startChatTimer", () => {
  it("records time to first status, first text, and the whole answer", () => {
    let t = 1000;
    const report = vi.fn();
    const timer = startChatTimer({ now: () => t, report });

    t = 1800; timer.status();
    t = 2500; timer.status();
    t = 4100; timer.text();
    t = 4200; timer.text();
    t = 4300;
    const timing = timer.finish();

    expect(timing).toEqual({
      "chat.first_status_ms": 800, "chat.first_text_ms": 3100, "chat.total_ms": 3300,
      "chat.tool_calls": 2, "chat.error": false,
    });
    expect(report).toHaveBeenCalledWith(timing, 1000);
  });

  it("reports errors and answers with no tools", () => {
    let t = 0;
    const timer = startChatTimer({ now: () => t, report: () => {} });
    t = 900;
    expect(timer.finish({ error: true })).toMatchObject({ "chat.first_status_ms": null, "chat.total_ms": 900, "chat.error": true });
  });

  it("is safe without Sentry configured", () => {
    expect(() => startChatTimer().finish()).not.toThrow();
  });
});
