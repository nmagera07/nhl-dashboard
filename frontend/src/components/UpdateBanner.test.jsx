import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UpdateBanner from "./UpdateBanner.jsx";
import { pwaState } from "../test/pwaRegisterStub.js";

describe("UpdateBanner", () => {
  afterEach(() => {
    pwaState.needRefresh = false;
    pwaState.updateServiceWorker = () => Promise.resolve();
  });

  it("stays hidden when there's no new version", () => {
    const { container } = render(<UpdateBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("offers the new version and installs it on Refresh", async () => {
    pwaState.needRefresh = true;
    const update = vi.fn(() => Promise.resolve());
    pwaState.updateServiceWorker = update;
    render(<UpdateBanner />);

    expect(screen.getByRole("status")).toHaveTextContent("A new version of NHL Dash is ready.");
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(update).toHaveBeenCalledWith(true);
  });

  it("can be dismissed", async () => {
    pwaState.needRefresh = true;
    render(<UpdateBanner />);

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
