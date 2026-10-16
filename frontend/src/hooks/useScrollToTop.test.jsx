import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useScrollToTop } from "./useScrollToTop.js";

function Harness() {
  useScrollToTop();
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate("/")}>Scores</button>
      <button onClick={() => navigate(-1)}>Back</button>
    </>
  );
}

describe("useScrollToTop", () => {
  beforeEach(() => {
    window.scrollTo = vi.fn();
  });

  it("scrolls to the top when a link opens a new page", () => {
    render(<MemoryRouter initialEntries={["/games/1"]}><Harness /></MemoryRouter>);
    window.scrollTo.mockClear();
    fireEvent.click(screen.getByText("Scores"));
    expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
  });

  it("leaves Back to the browser", () => {
    render(<MemoryRouter initialEntries={["/", "/games/1"]} initialIndex={1}><Harness /></MemoryRouter>);
    window.scrollTo.mockClear();
    fireEvent.click(screen.getByText("Back"));
    expect(window.scrollTo).not.toHaveBeenCalled();
  });
});
