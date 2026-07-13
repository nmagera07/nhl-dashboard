import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DivisionTabs from "./DivisionTabs.jsx";

describe("DivisionTabs", () => {
  const divisions = ["Atlantic", "Metropolitan"];

  it("renders one uppercased button per division", () => {
    render(<DivisionTabs divisions={divisions} active="Atlantic" onSelect={vi.fn()} disabled={false} />);

    expect(screen.getByRole("button", { name: "ATLANTIC" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "METROPOLITAN" })).toBeInTheDocument();
  });

  it("marks only the active division's tab as active", () => {
    render(<DivisionTabs divisions={divisions} active="Metropolitan" onSelect={vi.fn()} disabled={false} />);

    expect(screen.getByRole("button", { name: "ATLANTIC" })).not.toHaveClass("division-tab-active");
    expect(screen.getByRole("button", { name: "METROPOLITAN" })).toHaveClass("division-tab-active");
  });

  it("calls onSelect with the clicked division", async () => {
    const onSelect = vi.fn();
    render(<DivisionTabs divisions={divisions} active="Atlantic" onSelect={onSelect} disabled={false} />);

    await userEvent.click(screen.getByRole("button", { name: "METROPOLITAN" }));

    expect(onSelect).toHaveBeenCalledWith("Metropolitan");
  });

  it("disables every tab and cannot be clicked while searching", async () => {
    const onSelect = vi.fn();
    render(<DivisionTabs divisions={divisions} active="Atlantic" onSelect={onSelect} disabled={true} />);

    const button = screen.getByRole("button", { name: "ATLANTIC" });
    expect(button).toBeDisabled();

    await userEvent.click(button);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
