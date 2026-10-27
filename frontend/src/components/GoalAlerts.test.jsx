import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GoalAlerts from "./GoalAlerts.jsx";
import * as push from "../utils/push.js";

vi.mock("../utils/push.js", () => ({
  pushSupport: vi.fn(() => "ready"),
  currentSubscription: vi.fn(async () => null),
  enableAlerts: vi.fn(async () => "granted"),
  disableAlerts: vi.fn(async () => {}),
  updateAlertTeams: vi.fn(async () => {}),
  alertPrefs: vi.fn(() => ({ starts: true, goals: true, goals_against: true, finals: true, muted: [] })),
  setAlertPrefs: vi.fn(),
}));

describe("GoalAlerts", () => {
  beforeEach(() => vi.clearAllMocks());

  it("turns alerts on for the team, then off", async () => {
    render(<GoalAlerts teams={["PIT"]} />);

    await userEvent.click(screen.getByRole("button", { name: /goal alerts/i }));
    expect(push.enableAlerts).toHaveBeenCalledWith(["PIT"]);
    expect(await screen.findByRole("button", { name: /alerts on/i })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: /alerts on/i }));
    expect(push.disableAlerts).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /goal alerts/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("alert settings: switch off a kind of alert or a team, and each change is saved", async () => {
    push.currentSubscription.mockResolvedValueOnce({ endpoint: "https://fcm.googleapis.com/x" });
    render(<GoalAlerts teams={["PIT", "VGK"]} />);
    await userEvent.click(await screen.findByRole("button", { name: "Alert settings" }));

    await userEvent.click(screen.getByRole("checkbox", { name: "Goals against" }));
    expect(push.setAlertPrefs).toHaveBeenLastCalledWith(expect.objectContaining({ goals_against: false, starts: true }));
    expect(push.updateAlertTeams).toHaveBeenLastCalledWith(["PIT", "VGK"]);

    await userEvent.click(screen.getByRole("checkbox", { name: "VGK" }));
    expect(push.setAlertPrefs).toHaveBeenLastCalledWith(expect.objectContaining({ muted: ["VGK"] }));
    expect(screen.getByRole("checkbox", { name: "PIT" })).toBeDisabled(); // the last team can't be switched off

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("group", { name: "Alert me about" })).not.toBeInTheDocument();
  });

  it("shows alerts on for a subscribed device and keeps its team current", async () => {
    push.currentSubscription.mockResolvedValueOnce({ endpoint: "https://fcm.googleapis.com/x" });
    render(<GoalAlerts teams={["BOS"]} />);

    expect(await screen.findByRole("button", { name: /alerts on/i })).toBeInTheDocument();
    expect(push.updateAlertTeams).toHaveBeenCalledWith(["BOS"]);
  });

  it("explains the iPhone home-screen requirement", () => {
    push.pushSupport.mockReturnValue("ios-install");
    render(<GoalAlerts teams={["PIT"]} />);
    expect(screen.getByText(/add to home screen for goal alerts/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says when notifications are blocked, and hides itself where push can't work", () => {
    push.pushSupport.mockReturnValue("denied");
    const { unmount } = render(<GoalAlerts teams={["PIT"]} />);
    expect(screen.getByText(/blocked in settings/i)).toBeInTheDocument();
    unmount();

    push.pushSupport.mockReturnValue("unsupported");
    const { container } = render(<GoalAlerts teams={["PIT"]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the error if subscribing fails", async () => {
    push.pushSupport.mockReturnValue("ready");
    push.enableAlerts.mockRejectedValueOnce(new Error("Notifications aren't set up on the server yet."));
    render(<GoalAlerts teams={["PIT"]} />);

    await userEvent.click(screen.getByRole("button", { name: /goal alerts/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("aren't set up");
  });
});
