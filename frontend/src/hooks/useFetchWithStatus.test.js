import { renderHook, waitFor } from "@testing-library/react";
import { useFetchWithStatus } from "./useFetchWithStatus.js";

function mockFetchOnce(body) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    json: () => Promise.resolve(body),
  });
}

function mockFetchRejecting() {
  globalThis.fetch = vi.fn().mockRejectedValue(new Error("network down"));
}

describe("useFetchWithStatus", () => {
  it("starts idle when no url is given, and never calls fetch", () => {
    globalThis.fetch = vi.fn();

    const { result } = renderHook(() => useFetchWithStatus(null, { initialData: [] }));

    expect(result.current.status).toBe("idle");
    expect(result.current.data).toEqual([]);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("goes loading -> ready and stores the parsed response", async () => {
    mockFetchOnce([{ id: 1 }]);

    const { result } = renderHook(() => useFetchWithStatus("http://api.test/things"));

    expect(result.current.status).toBe("loading");

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toEqual([{ id: 1 }]);
  });

  it("goes loading -> error when fetch rejects, and leaves data untouched", async () => {
    mockFetchRejecting();

    const { result } = renderHook(() => useFetchWithStatus("http://api.test/things", { initialData: [] }));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.data).toEqual([]);
  });

  it("runs transform on the raw response before storing it", async () => {
    // Mirrors real usage: several pages default a non-array API response to [].
    mockFetchOnce(null);

    const { result } = renderHook(() =>
      useFetchWithStatus("http://api.test/things", {
        initialData: [],
        transform: (raw) => (Array.isArray(raw) ? raw : []),
      })
    );

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toEqual([]);
  });

  it("calls onSuccess with the (already-transformed) value once data arrives", async () => {
    mockFetchOnce([{ division: "Atlantic" }, { division: "Metropolitan" }]);
    const onSuccess = vi.fn();

    const { result } = renderHook(() =>
      useFetchWithStatus("http://api.test/standings", { initialData: [], onSuccess })
    );

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledWith([{ division: "Atlantic" }, { division: "Metropolitan" }]);
  });

  it("re-fetches when the url changes", async () => {
    mockFetchOnce({ team: "PIT" });
    const { result, rerender } = renderHook(({ url }) => useFetchWithStatus(url), {
      initialProps: { url: "http://api.test/standings/PIT" },
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    mockFetchOnce({ team: "BOS" });
    rerender({ url: "http://api.test/standings/BOS" });

    expect(globalThis.fetch).toHaveBeenCalledWith("http://api.test/standings/BOS");
    await waitFor(() => expect(result.current.data).toEqual({ team: "BOS" }));
  });
});
