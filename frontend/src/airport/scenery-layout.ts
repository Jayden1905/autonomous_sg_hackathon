import type { Point } from "./layout";

/** Illustrative scenery only; these are not operational airport coordinates. */
export const concourses: {
  position: Point;
  length: number;
  rotation?: number;
}[] = [
  { position: [0, 0, 0], length: 206 },
  { position: [-71, 0, -43], length: 86, rotation: Math.PI / 2 },
  { position: [-25, 0, -83], length: 210 },
  { position: [-108, 0, 47], length: 94, rotation: Math.PI / 2 },
];

// The western north stands are occupied by the connecting concourse.
// Share the usable stand list with jet bridges so no bridge points into it.
export const northStandXs = [-18, 13, 44, 75];
export const parkedAircraft: { position: Point; rotation?: number }[] = [
  ...[-80, -49, -18, 44, 75].map((x) => ({
    position: [x, 0, 39] as Point,
  })),
  ...northStandXs
    .filter((x) => x !== 13)
    .map((x) => ({
      position: [x, 0, -38] as Point,
      rotation: Math.PI,
    })),
];
