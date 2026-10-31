import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const output = process.env.E2E_OUTPUT_DIR || join(tmpdir(), "nushack-motion");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (
    message.type() === "error" &&
    /shader|webgl|invalid/i.test(message.text())
  )
    errors.push(message.text());
});
await page.addInitScript(() => {
  window.__draws = 0;
  for (const name of [
    "drawArrays",
    "drawElements",
    "drawArraysInstanced",
    "drawElementsInstanced",
  ]) {
    const original = WebGL2RenderingContext.prototype[name];
    WebGL2RenderingContext.prototype[name] = function (...args) {
      window.__draws++;
      return original.apply(this, args);
    };
  }
});
const scene = page.getByRole("region", { name: "Illustrative 3D airport" });
const canvas = page.locator("canvas");
const options = scene
  .locator("details")
  .filter({
    has: page.getByRole("combobox", {
      name: "Scene weather",
      includeHidden: true,
    }),
  });
const wait = (ms) => page.waitForTimeout(ms);
try {
  await page.goto(process.env.E2E_URL || "http://127.0.0.1:5173");
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .waitFor();
  await page.waitForFunction(
    () => Number(document.querySelector("canvas")?.dataset.sceneTime) > 19,
  );
  assert.equal(await scene.getAttribute("data-weather"), "storm");
  assert.equal(await scene.getAttribute("data-motion"), "playing");
  await options.locator("summary").click();
  await page
    .getByRole("combobox", { name: "Scene quality" })
    .selectOption("high");
  await options.locator("summary").press("Escape");
  await wait(1500);
  const time = Number(await canvas.getAttribute("data-scene-time"));
  await page.screenshot({ path: join(output, "storm.png") });
  await wait(1600);
  assert.ok(Number(await canvas.getAttribute("data-scene-time")) > time);
  console.log(
    "Desktop storm renderer:",
    await canvas.evaluate((c) => ({ ...c.dataset })),
  );

  await options.locator("summary").click();
  await page
    .getByRole("combobox", { name: "Scene weather" })
    .selectOption("clear");
  await page
    .getByRole("button", { name: "Pause scene motion", exact: true })
    .click();
  assert.equal(await scene.getAttribute("data-motion"), "paused");
  await options.locator("summary").press("Escape");
  await wait(900);
  const pausedDraws = await page.evaluate(() => window.__draws);
  await wait(1200);
  assert.equal(
    await page.evaluate(() => window.__draws),
    pausedDraws,
    "Paused idle scene should issue no draws",
  );
  await page.screenshot({ path: join(output, "clear-paused.png") });

  await options.locator("summary").click();
  await page
    .getByRole("combobox", { name: "Scene weather" })
    .selectOption("rain");
  await page
    .getByRole("combobox", { name: "Scene quality" })
    .selectOption("eco");
  await page
    .getByRole("button", { name: "Resume scene motion", exact: true })
    .click();
  await options.locator("summary").press("Escape");
  assert.equal(await scene.getAttribute("data-quality"), "eco");
  await wait(1500);
  console.log(
    "Eco rain renderer:",
    await canvas.evaluate((c) => ({ ...c.dataset })),
  );

  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForFunction(
    () =>
      document.querySelector("[data-motion]")?.getAttribute("data-motion") ===
      "paused",
  );
  await wait(500);
  const hiddenDraws = await page.evaluate(() => window.__draws);
  await wait(1100);
  assert.equal(
    await page.evaluate(() => window.__draws),
    hiddenDraws,
    "Hidden idle scene should issue no draws",
  );
  await page.evaluate(() => {
    delete document.hidden;
    document.dispatchEvent(new Event("visibilitychange"));
  });

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForFunction(
    () =>
      document.querySelector("[data-motion]")?.getAttribute("data-motion") ===
      "paused",
  );
  await options.locator("summary").click();
  assert.equal(
    await page
      .getByRole("button", { name: "Pause scene motion", exact: true })
      .isDisabled(),
    true,
  );
  await page
    .getByText("Motion is off to respect your reduced-motion preference.")
    .waitFor();
  await options.locator("summary").press("Escape");
  await page
    .getByRole("button", { name: "Run negotiation", exact: true })
    .click();
  await page
    .locator(".outcome")
    .filter({ hasText: "Consensus reached" })
    .waitFor();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .waitFor();
  assert.equal(await scene.getAttribute("data-quality"), "eco");
  await options.locator("summary").click();
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.screenshot({ path: join(output, "mobile-controls.png") });
  assert.deepEqual(errors, []);
  console.log(
    `Motion, weather, quality, idle draw suppression, hidden-tab pause, reduced motion and mobile verified. Images: ${output}`,
  );
} finally {
  await browser.close();
}
