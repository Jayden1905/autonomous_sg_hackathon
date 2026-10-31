import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const output = join(tmpdir(), "nushack-interactions");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({
  viewport: { width: 1600, height: 1000 },
  reducedMotion: "reduce",
});
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
const inspector = page.getByRole("complementary", { name: "Flight inspector" });
const scene = page.getByRole("region", { name: "Illustrative 3D airport" });
// Controlled UI fixture: verifies transitions without making an operational claim.
const before = {
  arrival_min: 52,
  runway: "27L",
  gate: "B6",
  rationale: "Initial test proposal",
};
const after = {
  arrival_min: 60,
  runway: "27R",
  gate: "C9",
  rationale: "Revised test proposal",
};
const evaluation = (proposal, feasible) => ({
  proposal,
  feasible,
  cost: 0,
  results: [],
});
let outcome = "consensus";
try {
  await page.goto(process.env.E2E_URL || "http://127.0.0.1:5173");
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .waitFor();
  // Test the geometry itself, not just the HTML labels. Fiber's dev root gives
  // the projected coordinate of the real hit mesh; no test hook in app code.
  await page
    .getByRole("button", { name: "Top-down view", exact: true })
    .click();
  // Allow CameraControls and the demand-rendered canvas to finish changing view
  // before projecting hit surfaces (software WebGL can take several frames).
  await page.waitForTimeout(1000);
  const clickSurface = async (name) => {
    const point = await page.evaluate(async (name) => {
      const { _roots } =
        await import("/node_modules/.vite/deps/@react-three_fiber.js");
      const canvas = document.querySelector("canvas");
      const state = _roots.get(canvas).store.getState();
      const object = state.scene.getObjectByName(name);
      const vector = object.position.clone();
      state.camera.updateMatrixWorld();
      // Avoid the aircraft and HTML badge over the middle of a stand.
      if (name.includes("gate")) {
        vector.x -= 12;
        vector.z += 18;
      } else vector.x -= 170;
      vector.project(state.camera);
      const rect = canvas.getBoundingClientRect();
      return {
        x: rect.x + ((vector.x + 1) * rect.width) / 2,
        y: rect.y + ((1 - vector.y) * rect.height) / 2,
      };
    }, name);
    await page.mouse.move(point.x, point.y);
    await page.mouse.click(point.x, point.y);
  };
  await clickSurface("resource-gate-B6");
  await inspector
    .getByRole("heading", { name: "Gate B6", exact: true })
    .waitFor();
  await inspector.getByText("Free until", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Select gate B6", exact: true })
      .getAttribute("aria-pressed"),
    "true",
  );
  await clickSurface("resource-runway-27L");
  await inspector
    .getByRole("heading", { name: "Runway 27L", exact: true })
    .waitFor();
  await inspector.locator("dd").getByText("Closed", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "3D airport view", exact: true })
    .click();
  await page.screenshot({ path: join(output, "runway-details.png") });
  // Same action is reachable without canvas or pointer input.
  await page
    .getByRole("button", { name: "Select gate C9", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await inspector
    .getByRole("heading", { name: "Gate C9", exact: true })
    .waitFor();
  await page.screenshot({ path: join(output, "gate-details.png") });
  await inspector
    .getByRole("button", { name: "Back to flight", exact: true })
    .click();
  await page.route("**/api/negotiate/stream", (route) => {
    assert.equal(route.request().postDataJSON().mock, true);
    const trace = {
      scenario_id: "demo-storm-ORD-UA599",
      model: "UI test fixture",
      started_at: "2026-10-31T00:00:00Z",
      duration_s: 1,
      outcome,
      final: after,
      final_evaluation: evaluation(after, outcome === "consensus"),
      turns: [before, after].map((proposal, i) => ({
        turn: i + 1,
        proposer: "atc",
        proposal,
        evaluation: evaluation(proposal, i === 1),
        responses: {},
        counter_evaluations: {},
      })),
    };
    return route.fulfill({
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify(trace)}\n\n`,
    });
  });
  await page
    .getByRole("button", { name: "Run negotiation", exact: true })
    .click();
  await inspector
    .getByText("Compared with turn 1 · 3 changes", { exact: true })
    .waitFor();
  await inspector.getByText("8 min later", { exact: true }).waitFor();
  await page.screenshot({ path: join(output, "plan-changes.png") });
  await inspector
    .getByRole("button", { name: "Inspect previous gate B6", exact: true })
    .click();
  await inspector
    .getByRole("heading", { name: "Gate B6", exact: true })
    .waitFor();
  await inspector.getByText(/Replaced by C9/).waitFor();
  await inspector
    .getByRole("button", { name: "Inspect gate C9", exact: true })
    .click();
  await inspector
    .getByRole("heading", { name: "Gate C9", exact: true })
    .waitFor();
  outcome = "no_legal_option";
  await page.getByRole("button", { name: "Run again", exact: true }).click();
  await inspector
    .getByText("Last attempt · not a recommendation", { exact: true })
    .waitFor();
  assert.equal(
    await scene.locator("button small").count(),
    0,
    "No plan/previous emphasis for no legal option",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .click();
  await inspector
    .getByRole("heading", { name: "Gate B6", exact: true })
    .waitFor();
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.screenshot({ path: join(output, "mobile-gate.png") });
  assert.deepEqual(errors, []);
  console.log(
    `Verified surface clicks, keyboard labels, resource details, recorded plan changes, no-option emphasis and mobile. Screenshots: ${output}`,
  );
} catch (error) {
  await page.screenshot({ path: join(output, "failure.png") });
  console.error("Inspector at failure:", await inspector.innerText());
  console.error("Browser errors:", errors);
  throw error;
} finally {
  await browser.close();
}
