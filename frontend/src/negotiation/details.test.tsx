// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CitedText, safeSourceUrl } from "./details";

afterEach(cleanup);
it("keeps identical citation numbers scoped to their own reply", () => {
  render(
    <>
      <CitedText
        text="ATC claim [1]"
        evidence={[
          {
            id: 1,
            claim: "ATC source",
            source: "scenario:runways",
            grounded: true,
            trust: "high",
          },
        ]}
      />
      <CitedText
        text="Pilot claim [1]"
        evidence={[
          {
            id: 1,
            claim: "Pilot source",
            source: "scenario:fuel",
            grounded: false,
            trust: "low",
          },
        ]}
      />
    </>,
  );
  fireEvent.click(
    screen.getAllByRole("button", { name: "Show evidence 1" })[1],
  );
  expect(document.activeElement?.textContent).toContain("Pilot source");
  expect(document.activeElement?.textContent).toContain("Unverified source");
  expect(screen.getByText("ATC source").closest("details")?.open).toBe(false);
});
it("only exposes http and https source links", () => {
  expect(safeSourceUrl("javascript:alert(1)")).toBeUndefined();
  expect(safeSourceUrl("data:text/html,test")).toBeUndefined();
  expect(safeSourceUrl("https://example.org/rule")).toBe(
    "https://example.org/rule",
  );
});
