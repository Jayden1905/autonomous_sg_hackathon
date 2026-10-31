import assert from "node:assert/strict";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

// Start make serve and npm run dev first. All real API requests use mock agents.
const output = process.env.E2E_OUTPUT_DIR || join(tmpdir(), "nushack-e2e");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = [];
let phase = "initial load";
page.on("pageerror", (error) => {
  errors.push(error.message);
  console.error(phase, error.stack);
});
page.on("request", (request) => {
  if (request.url().endsWith("/negotiate/stream"))
    assert.equal(
      request.postDataJSON().mock,
      true,
      "Browser tests must never spend model credits",
    );
});
const app = process.env.E2E_URL || "http://127.0.0.1:5173";
const inspector = page.getByRole("complementary", { name: "Flight inspector" });
const run = async (outcome) => {
  phase = `run: ${outcome}`;
  await page
    .getByRole("button", {
      name: /^(Run negotiation|Run again|Retry negotiation)$/,
    })
    .click();
  await inspector.locator(".outcome").filter({ hasText: outcome }).waitFor();
};
const choose = async (query) => {
  phase = `scenario: ${query}`;
  await page.getByRole("button", { name: "Find a flight or scenario" }).click();
  await page
    .getByRole("textbox", { name: "Search loaded scenarios" })
    .fill(query);
  await page
    .getByRole("dialog")
    .locator("button")
    .filter({ hasText: query })
    .last()
    .click();
};
try {
  await page.goto(app);
  await inspector
    .getByRole("heading", { name: "UA599", exact: true })
    .waitFor();
  await page.locator("canvas").waitFor();
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .click();
  assert.equal(
    await inspector
      .getByRole("button", { name: /^Gate B6/ })
      .getAttribute("aria-pressed"),
    "true",
  );
  await inspector
    .getByRole("button", { name: "UA599 Flight", exact: true })
    .click();
  await run("Consensus reached");
  assert.match(await inspector.textContent(), /B6/);
  await page.screenshot({ path: join(output, "consensus.png") });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export negotiation trace" }).click();
  const download = await downloadPromise;
  const trace = JSON.parse(await readFile(await download.path(), "utf8"));
  assert.equal(trace.outcome, "consensus");
  assert.equal(trace.final.gate, "B6");

  await page.getByRole("tab", { name: "History", exact: true }).click();
  await page
    .getByRole("button", { name: "Inspect T1 · ATC", exact: true })
    .click();
  await inspector.getByText("Historical proposal", { exact: true }).waitFor();
  await inspector
    .getByRole("button", { name: "Back to latest", exact: true })
    .click();
  await inspector
    .locator(".outcome")
    .filter({ hasText: "Consensus reached" })
    .waitFor();

  await choose("UA1234");
  await inspector.locator(".run-settings > summary").click();
  await page.getByRole("combobox", { name: "Maximum turns" }).selectOption("1");
  await inspector.locator(".run-settings > summary").click();
  await run("Fallback plan");
  await inspector.getByText("Solver recommendation", { exact: true }).waitFor();

  await choose("VX204");
  await run("No legal option");
  await inspector
    .getByText("Last attempt · not a recommendation", { exact: true })
    .waitFor();
  assert.equal(
    await inspector.getByText("Agreed recommendation", { exact: true }).count(),
    0,
  );
  await page.screenshot({ path: join(output, "no-legal-option.png") });

  await page.getByRole("button", { name: /Decision history/ }).click();
  await page
    .getByRole("region", { name: "Decision history" })
    .getByRole("button")
    .filter({ hasText: "UA599" })
    .click();
  await inspector
    .getByRole("heading", { name: "UA599", exact: true })
    .waitFor();
  await inspector
    .locator(".outcome")
    .filter({ hasText: "Consensus reached" })
    .waitFor();

  // A truncated stream must never promote a partial plan to a final result.
  await page.route("**/api/negotiate/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: 'event: thinking\ndata: {"turn":1,"agent":"atc","action":"propose"}\n\n',
    }),
  );
  await page.getByRole("button", { name: "Run again", exact: true }).click();
  await inspector.getByText("Run incomplete", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Export negotiation trace" })
      .isDisabled(),
    true,
  );
  await page.unroute("**/api/negotiate/stream");

  // Delayed previous-run results must not replace a new scenario.
  let release;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  let started;
  const requested = new Promise((resolve) => {
    started = resolve;
  });
  await page.route("**/api/negotiate/stream", async (route) => {
    started();
    await waiting;
    await route
      .fulfill({
        contentType: "text/event-stream",
        body: `event: done\ndata: ${JSON.stringify(trace)}\n\n`,
      })
      .catch(() => {});
  });
  await page.getByRole("button", { name: "Retry negotiation" }).click();
  await requested;
  await choose("VX204");
  release();
  await inspector
    .getByRole("heading", { name: "VX204", exact: true })
    .waitFor();
  assert.equal(await inspector.locator(".outcome").count(), 0);
  await page.unrouteAll({ behavior: "wait" });

  // Narrow screen starts with the scene visible, and uses an explicit details sheet.
  phase = "mobile reload";
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .getByRole("button", { name: "Find a flight or scenario" })
    .waitFor();
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .waitFor();
  assert.equal(await inspector.count(), 0);
  await page.getByRole("button", { name: "Open flight inspector" }).click();
  await run("Consensus reached");
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    true,
  );
  await page.screenshot({ path: join(output, "mobile.png") });
  await page.getByRole("tab", { name: "Negotiation", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(
    await page
      .getByRole("tab", { name: "History", exact: true })
      .getAttribute("aria-selected"),
    "true",
  );
  assert.deepEqual(errors, []);
  // Losing the renderer must leave the flight list and negotiation workflow usable.
  phase = "renderer unavailable";
  await page.locator("canvas").evaluate((canvas) => {
    const context = canvas.getContext("webgl2");
    const extension = context?.getExtension("WEBGL_lose_context");
    if (!extension) throw new Error("WebGL context-loss test unavailable");
    extension.loseContext();
  });
  await page.getByText("3D view unavailable", { exact: true }).waitFor();
  await page.getByRole("tab", { name: "Flight", exact: true }).click();
  await inspector.getByRole("button", { name: /^Gate B6/ }).click();
  await run("Consensus reached");

  phase = "backend unavailable";
  await page.route("**/api/health", (route) =>
    route.fulfill({ status: 503, body: "Backend temporarily unavailable" }),
  );
  await page.reload();
  await page.getByRole("heading", { name: "Connect the backend" }).waitFor();
  await page.unroute("**/api/health");
  await page.getByRole("button", { name: "Reconnect", exact: true }).click();
  await page
    .getByRole("button", { name: "Find a flight or scenario" })
    .waitFor();
  assert.deepEqual(errors, []);
  console.log(
    `Verified consensus, fallback, no legal option, scene selection, export, history, interrupted stream, scenario-switch isolation, mobile, renderer loss and API reconnection. Screenshots: ${output}`,
  );
} finally {
  await browser.close();
}
