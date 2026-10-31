import { Box3, Matrix4, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { aircraftGeometry } from "./aircraft-model";
import { scenarioSlots } from "./fleet";
import { concourses, parkedAircraft } from "./scenery-layout";
import { datasetLayout, demoLayout, stormLayout } from "./layout";
import type { Point } from "./layout";

// Include the rounded end caps and roof overhang, using the same transforms
// as the rendered concourses. Check the whole aircraft, including its wings.
const buildings = concourses.map(({ position, length, rotation = 0 }) =>
  new Box3(
    new Vector3(-length / 2 - 8.75, 0, -8.75),
    new Vector3(length / 2 + 8.75, 10.05, 8.75),
  ).applyMatrix4(
    new Matrix4()
      .makeTranslation(...position)
      .multiply(new Matrix4().makeRotationY(rotation)),
  ),
);
const model = new Box3();
for (const geometry of Object.values(aircraftGeometry)) {
  geometry.computeBoundingBox();
  model.union(geometry.boundingBox!);
}
function overlapsTerminal(position: Point, rotation = 0) {
  const bounds = model
    .clone()
    .applyMatrix4(
      new Matrix4()
        .makeTranslation(...position)
        .multiply(new Matrix4().makeRotationY(rotation)),
    );
  return buildings.some((building) => bounds.intersectsBox(building));
}

describe("aircraft clearance from the illustrative terminal", () => {
  it("detects the reported north-stand collision", () => {
    expect(overlapsTerminal([-80, 0, -38], Math.PI)).toBe(true);
  });
  it("keeps every decorative parked aircraft outside the terminal", () => {
    for (const { position, rotation } of [...parkedAircraft, ...scenarioSlots])
      expect(overlapsTerminal(position, rotation), `Stand ${position}`).toBe(
        false,
      );
  });
  it("keeps mapped proposal placements and the idle flight outside buildings", () => {
    expect(overlapsTerminal([13, 0, 52])).toBe(false);
    for (const layout of [demoLayout, stormLayout, datasetLayout])
      for (const [x, , z] of Object.values(layout.gates))
        expect(overlapsTerminal([x, 0, z + 16])).toBe(false);
  });
});
