import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Sentry from "@sentry/react";
import ErrorFallback from "./ErrorFallback.jsx";

function Bomb() {
  throw new Error("boom");
}

describe("ErrorFallback / Sentry.ErrorBoundary wiring", () => {
  // React logs the caught error to the console by design; keep test
  // output clean without hiding a real assertion failure.
  let consoleError;
  beforeEach(() => {
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    consoleError.mockRestore();
  });

  it("renders children normally when nothing throws", () => {
    render(
      <Sentry.ErrorBoundary fallback={ErrorFallback}>
        <div>All good</div>
      </Sentry.ErrorBoundary>
    );

    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("catches a render error and shows the fallback instead of crashing", () => {
    render(
      <Sentry.ErrorBoundary fallback={ErrorFallback}>
        <Bomb />
      </Sentry.ErrorBoundary>
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.queryByText("All good")).not.toBeInTheDocument();
  });

  it("the fallback's reload button calls window.location.reload", async () => {
    // jsdom's window.location.reload isn't directly spy-able (it throws
    // "Cannot redefine property"); replace the whole location object
    // instead, matching Vitest's documented workaround.
    const reload = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, reload },
    });

    render(
      <Sentry.ErrorBoundary fallback={ErrorFallback}>
        <Bomb />
      </Sentry.ErrorBoundary>
    );
    await userEvent.click(screen.getByRole("button", { name: /reload the page/i }));

    expect(reload).toHaveBeenCalled();

    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });
});
