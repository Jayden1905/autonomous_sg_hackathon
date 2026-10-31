// @vitest-environment jsdom
import { afterEach, beforeAll, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { Scenario } from "@/workspace";
import storm from "../../../scenarios/demo_storm_ua599.json";
import weather from "../../../scenarios/sample_weather.json";
import { ScenarioPicker } from "./picker";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(cleanup);
describe("scenario picker", () => {
  it("searches only supplied scenarios and emits the selected scenario", () => {
    const onSelect = vi.fn();
    render(
      <ScenarioPicker
        scenarios={[weather as Scenario]}
        selectedId=""
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Find a flight/ }));
    expect(screen.getByRole("textbox")).toHaveFocus();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "not-an-airport" },
    });
    expect(screen.getByText(/No loaded scenarios match/)).toBeVisible();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "den" } });
    fireEvent.click(screen.getByRole("button", { name: /UA1234/ }));
    expect(onSelect).toHaveBeenCalledWith(weather);
    expect(screen.getByRole("button", { name: /Find a flight/ })).toHaveFocus();
  });
  it("labels each result's provenance and reports where scenarios came from", () => {
    render(
      <ScenarioPicker
        scenarios={[weather as Scenario, storm as Scenario]}
        selectedId=""
        onSelect={() => {}}
        status="Backend not reachable"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Find a flight/ }));
    expect(
      screen.getByText(
        "Hand-written sample · not from the dataset · Weather disruption",
      ),
    ).toBeVisible();
    expect(
      screen.getByText("US DOT flight · 8 May 2015 · Weather disruption"),
    ).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Backend not reachable",
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "boston" },
    });
    expect(screen.getByRole("button", { name: /UA599/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /UA1234/ })).toBeNull();
  });
  it("closes with Escape and returns focus to its trigger", () => {
    render(<ScenarioPicker scenarios={[]} selectedId="" onSelect={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /Find a flight/ }));
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { bubbles: true, cancelable: true }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Find a flight/ })).toHaveFocus();
  });
});
