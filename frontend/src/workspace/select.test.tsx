// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { Select } from "./select";

afterEach(cleanup);
const options = [
  { value: "auto", label: "Auto", description: "Adjust to this device" },
  { value: "blocked", label: "Unavailable", disabled: true },
  { value: "eco", label: "Eco" },
  { value: "high", label: "High" },
];
function Example() {
  const [value, setValue] = useState("auto");
  return (
    <Select
      label="Quality"
      value={value}
      onChange={setValue}
      options={options}
    />
  );
}
it("uses a labelled list with a selected check and keeps focus on the trigger", () => {
  render(<Example />);
  const trigger = screen.getByRole("combobox", { name: "Quality" });
  trigger.focus();
  fireEvent.click(trigger);
  expect(screen.getByRole("option", { name: "Auto" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  expect(trigger).toHaveAttribute(
    "aria-activedescendant",
    screen.getByRole("option", { name: "Eco" }).id,
  );
  fireEvent.keyDown(trigger, { key: "Enter" });
  expect(trigger).toHaveTextContent("Eco");
  expect(trigger).toHaveFocus();
  expect(screen.queryByRole("listbox")).toBeNull();
});
it("supports type-ahead and cancels without committing on Escape", () => {
  render(<Example />);
  const trigger = screen.getByRole("combobox");
  fireEvent.keyDown(trigger, { key: "h" });
  expect(trigger).toHaveAttribute(
    "aria-activedescendant",
    screen.getByRole("option", { name: "High" }).id,
  );
  fireEvent.keyDown(trigger, { key: "Escape" });
  expect(trigger).toHaveTextContent("Auto");
  expect(screen.queryByRole("listbox")).toBeNull();
});
it("dismisses on outside interaction and leaves disabled controls inert", () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <Select
      label="Quality"
      value="auto"
      onChange={onChange}
      options={options}
    />,
  );
  fireEvent.click(screen.getByRole("combobox"));
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("listbox")).toBeNull();
  rerender(
    <Select
      label="Quality"
      value="auto"
      onChange={onChange}
      options={options}
      disabled
    />,
  );
  fireEvent.click(screen.getByRole("combobox"));
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(onChange).not.toHaveBeenCalled();
});
it("lets users inspect closed resources without treating them as disabled", () => {
  const onChange = vi.fn();
  render(
    <Select
      label="Resource"
      value="gate"
      onChange={onChange}
      options={[
        {
          value: "runway",
          label: "Runway 27L",
          group: "Runways",
          meta: "Closed",
        },
        { value: "gate", label: "Gate B6", group: "Gates" },
      ]}
    />,
  );
  fireEvent.click(screen.getByRole("combobox"));
  fireEvent.click(screen.getByRole("option", { name: "Runway 27L" }));
  expect(onChange).toHaveBeenCalledWith("runway");
});
