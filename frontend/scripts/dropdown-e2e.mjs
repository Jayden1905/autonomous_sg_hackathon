import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const output = join(tmpdir(), "nushack-dropdowns");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const errors = [];
const app = process.env.E2E_URL || "http://127.0.0.1:5173";
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  reducedMotion: "reduce",
});
page.on("pageerror", (error) => errors.push(error.message));
const containedMenu = async (page) => {
  const box = await page.getByRole("listbox").boundingBox();
  const viewport = page.viewportSize();
  assert.ok(
    box &&
      box.x >= 0 &&
      box.y >= 0 &&
      box.x + box.width <= viewport.width + 1 &&
      box.y + box.height <= viewport.height + 1,
    "Menu stays in the viewport",
  );
};
try {
  await page.goto(app);
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .waitFor();
  const atmosphere = page
    .getByRole("region", { name: "Illustrative 3D airport" })
    .locator("details");
  await atmosphere.locator("summary").click();
  const weather = page.getByRole("combobox", { name: "Scene weather" });
  await weather.click();
  await containedMenu(page);
  await page.screenshot({ path: join(output, "weather.png") });
  await weather.press("Escape");
  assert.equal(await atmosphere.getAttribute("open"), "");
  assert.equal(await page.getByRole("listbox").count(), 0);
  await weather.press("r");
  await weather.press("Enter");
  assert.match(await weather.textContent(), /Rain/);
  assert.equal(
    await page
      .getByRole("region", { name: "Illustrative 3D airport" })
      .getAttribute("data-weather"),
    "rain",
  );
  await weather.click();
  await page.mouse.click(800, 100);
  assert.equal(await page.getByRole("listbox").count(), 0);
  await page.getByRole("combobox", { name: "Scene quality" }).click();
  await page.getByRole("option", { name: "High", exact: true }).click();
  await atmosphere.locator("summary").press("Escape");
  await page.locator(".run-settings summary").click();
  const mode = page.getByRole("combobox", { name: "Agent mode" });
  await mode.click();
  await page.getByRole("option", { name: "Live AI", exact: true }).click();
  const effort = page.getByRole("combobox", { name: "Reasoning effort" });
  await effort.click();
  await containedMenu(page);
  await effort.press("End");
  await effort.press("Enter");
  assert.match(await effort.textContent(), /Maximum/);
  await mode.click();
  await page.getByRole("option", { name: "Mock agents", exact: true }).click();
  const turns = page.getByRole("combobox", { name: "Maximum turns" });
  await turns.click();
  await turns.press("Home");
  await turns.press("Enter");
  assert.match(await turns.textContent(), /1 turn/);
  await turns.click();
  await turns.press("Tab");
  assert.equal(await page.getByRole("listbox").count(), 0);
  await page.locator(".run-settings summary").click();
  await page
    .getByRole("button", { name: "Select gate B6", exact: true })
    .click();
  const resource = page.getByRole("combobox", {
    name: "Inspect another resource",
  });
  await resource.click();
  await containedMenu(page);
  await page.screenshot({ path: join(output, "resources.png") });
  await page.getByRole("option", { name: "Runway 27L", exact: true }).click();
  await page
    .getByRole("heading", { name: "Runway 27L", exact: true })
    .waitFor();
  assert.equal(
    await resource.evaluate((element) => element === document.activeElement),
    true,
  );

  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    reducedMotion: "reduce",
  });
  mobile.on("pageerror", (error) => errors.push(error.message));
  await mobile.goto(app);
  await mobile
    .getByRole("button", { name: "Select gate B6", exact: true })
    .tap();
  const mobileResource = mobile.getByRole("combobox", {
    name: "Inspect another resource",
  });
  await mobileResource.tap();
  await containedMenu(mobile);
  await mobile.screenshot({ path: join(output, "mobile-resources.png") });
  await mobile.getByRole("option", { name: "Gate C9", exact: true }).tap();
  await mobile.getByRole("heading", { name: "Gate C9", exact: true }).waitFor();
  assert.equal(
    await mobile.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await mobile.close();
  assert.deepEqual(errors, []);
  console.log(
    `Verified all dropdown fields, keyboard/type-ahead, Escape, outside click, retained resource focus, touch selection and viewport positioning. Screenshots: ${output}`,
  );
} finally {
  await browser.close();
}
