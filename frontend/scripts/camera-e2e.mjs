import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const output = join(tmpdir(), "nushack-camera");
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
// A paced UI fixture lets us inspect each streamed state without calling an LLM.
await page.addInitScript(() => {
  const original = window.fetch;
  window.fetch = async (input, init) => {
    if (!String(input).endsWith("/negotiate/stream"))
      return original(input, init);
    const request = JSON.parse(init.body);
    if (!request.mock) throw new Error("Camera fixture must use mock agents");
    return new Response(
      new ReadableStream({
        start(controller) {
          const encoder = new TextEncoder();
          window.__cameraEmit = (type, data) =>
            controller.enqueue(
              encoder.encode(
                `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`,
              ),
            );
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  };
});
const scene = page.getByRole("region", { name: "Illustrative 3D airport" });
const inspect = () =>
  page.evaluate(async () => {
    const { _roots } =
      await import("/node_modules/.vite/deps/@react-three_fiber.js");
    const state = _roots
      .get(document.querySelector("canvas"))
      ?.store.getState();
    if (!state?.controls) return null;
    const aircraft = [];
    state.scene.traverse((object) => {
      if (object.name === "parked-aircraft" && object.userData.scenarioId)
        aircraft.push({
          id: object.userData.scenarioId,
          position: object.position.toArray(),
        });
    });
    return {
      target: state.controls.getTarget(state.camera.position.clone()).toArray(),
      camera: state.camera.position.toArray(),
      aircraft,
    };
  });
const near = (a, b) => a.every((value, i) => Math.abs(value - b[i]) < 0.5);
async function target(expected) {
  const end = Date.now() + 15000;
  let state;
  do {
    state = await inspect();
    if (state && near(state.target, expected)) return state;
    await page.waitForTimeout(100);
  } while (Date.now() < end);
  assert.fail(`Expected camera target ${expected}; got ${state?.target}`);
}
const emit = async (type, data) => {
  await page.waitForFunction(() => typeof window.__cameraEmit === "function");
  await page.evaluate(({ type, data }) => window.__cameraEmit(type, data), {
    type,
    data,
  });
};
const evaluation = (proposal, feasible = true) => ({
  proposal,
  feasible,
  cost: 0,
  results: [],
});
const turn = (proposal, index) => ({
  turn: index,
  proposer: "atc",
  proposal,
  evaluation: evaluation(proposal),
  responses: {},
  counter_evaluations: {},
});
const scenarioId = "demo-storm-ORD-UA599";
try {
  await page.goto(process.env.E2E_URL || "http://127.0.0.1:5173");
  await page
    .locator('[data-scenario-id="demo-storm-ORD-AA1453-moves"]')
    .waitFor();
  const initial = await inspect();
  assert.equal(
    new Set(initial.aircraft.map((a) => a.position.join(","))).size,
    initial.aircraft.length,
  );
  const aa = initial.aircraft.find(
    (a) => a.id === "demo-storm-ORD-AA1453-moves",
  );
  const ua = initial.aircraft.find((a) => a.id === scenarioId);
  await page
    .getByRole("button", { name: "Find a flight or scenario", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button")
    .filter({ hasText: "AA1453" })
    .click();
  await target(aa.position);
  assert.match(await scene.getAttribute("data-plan-focus"), /^AA1453/);
  await page.screenshot({ path: join(output, "scenario-focus.png") });

  // Click the actual UA599 airframe, not just its label.
  const point = await page.evaluate(async (id) => {
    const { _roots } =
      await import("/node_modules/.vite/deps/@react-three_fiber.js");
    const canvas = document.querySelector("canvas"),
      state = _roots.get(canvas).store.getState();
    let plane;
    state.scene.traverse((o) => {
      if (o.userData.scenarioId === id) plane = o;
    });
    const vector = plane.position.clone();
    vector.y += 2.8;
    vector.project(state.camera);
    const r = canvas.getBoundingClientRect();
    return {
      x: r.x + ((vector.x + 1) * r.width) / 2,
      y: r.y + ((1 - vector.y) * r.height) / 2,
    };
  }, scenarioId);
  await page.mouse.click(point.x, point.y);
  await target(ua.position);
  assert.match(await scene.getAttribute("data-plan-focus"), /^UA599/);

  await page
    .getByRole("button", { name: "Run negotiation", exact: true })
    .click();
  const p1 = {
    arrival_min: 60,
    runway: "27L",
    gate: "B6",
    rationale: "Initial preview",
  };
  const p2 = { ...p1, gate: "C9", rationale: "Different gate" };
  const p3 = { ...p2, runway: "27R", rationale: "Different runway" };
  const p4 = { ...p3, gate: "B6", rationale: "Final gate" };
  await emit("proposal", { turn: 1, proposer: "atc", proposal: p1 });
  await emit("turn_complete", turn(p1, 1));
  await target([-21, 0, -59.5]);
  const beforeThinking = await inspect();
  await emit("thinking", { turn: 2, agent: "ground", action: "propose" });
  await page.waitForTimeout(600);
  const duringThinking = await inspect();
  assert.ok(
    near(beforeThinking.target, duringThinking.target),
    "Thinking must not pan",
  );
  assert.deepEqual(
    beforeThinking.aircraft,
    duringThinking.aircraft,
    "Thinking must not relocate the preview aircraft",
  );
  await emit("proposal", { turn: 2, proposer: "ground", proposal: p2 });
  await emit("turn_complete", turn(p2, 2));
  await target([75, 0, 39]);
  await emit("proposal", { turn: 3, proposer: "atc", proposal: p3 });
  await emit("turn_complete", turn(p3, 3));
  await target([-55, 0, -218]);
  await page.screenshot({ path: join(output, "runway-change.png") });

  await page.mouse.move(280, 420);
  await page.mouse.down();
  await page.mouse.move(360, 450, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  assert.equal(await scene.getAttribute("data-camera-follow"), "free");
  const free = await inspect();
  await emit("proposal", { turn: 4, proposer: "ground", proposal: p4 });
  await emit("turn_complete", turn(p4, 4));
  await page.waitForTimeout(600);
  assert.ok(
    near(free.camera, (await inspect()).camera),
    "Plan updates must not override free exploration",
  );
  await page
    .getByRole("button", { name: "Resume plan following", exact: true })
    .click();
  await target([13, 0, 39]);
  const trace = {
    scenario_id: scenarioId,
    model: "UI camera fixture",
    started_at: "2026-10-31T00:00:00Z",
    duration_s: 1,
    outcome: "consensus",
    final: p4,
    final_evaluation: evaluation(p4),
    turns: [p1, p2, p3, p4].map((p, i) => turn(p, i + 1)),
  };
  await emit("done", trace);
  await target([-21, 0, -89.5]);
  await page.screenshot({ path: join(output, "final-plan.png") });
  await page.getByRole("tab", { name: "History", exact: true }).click();
  await page
    .getByRole("button", { name: "Inspect T1 · ATC", exact: true })
    .click();
  await target([-21, 0, -59.5]);
  await page
    .getByRole("button", { name: "Back to latest", exact: true })
    .click();
  await target([-21, 0, -89.5]);

  await page.getByRole("button", { name: "Run again", exact: true }).click();
  await emit("done", {
    ...trace,
    outcome: "no_legal_option",
    final_evaluation: evaluation(p4, false),
  });
  await target(ua.position);
  assert.match(await scene.getAttribute("data-plan-focus"), /No legal option/);
  assert.equal(await scene.locator("button small").count(), 0);

  // Normal-motion transition and a narrow-screen selection.
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page
    .locator('[data-scenario-id="demo-storm-ORD-AA1453-moves"]')
    .click();
  await target(aa.position);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .getByRole("button", { name: "Find a flight or scenario", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button")
    .filter({ hasText: "AA1453" })
    .click();
  await target(aa.position);
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.screenshot({ path: join(output, "mobile-focus.png") });
  assert.deepEqual(errors, []);
  console.log(
    `Verified distinct aircraft, picker and mesh selection, streamed gate/runway changes, thinking stability, free camera, resume, final/history/no-option focus and mobile. Images: ${output}`,
  );
} catch (error) {
  await page.screenshot({ path: join(output, "failure.png") });
  console.error("Scene:", await inspect().catch(() => null), errors);
  throw error;
} finally {
  await browser.close();
}
