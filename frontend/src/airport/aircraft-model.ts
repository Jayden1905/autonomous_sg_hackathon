import {
  BoxGeometry,
  CircleGeometry,
  CylinderGeometry,
  ExtrudeGeometry,
  LatheGeometry,
  Matrix4,
  Shape,
  Vector2,
} from "three";
import type { BufferGeometry } from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

// One shared geometry per material, preserving Daniel's original aircraft shapes.
function placed(geometry: BufferGeometry, matrix: Matrix4) {
  const nonIndexed = geometry.index ? geometry.toNonIndexed() : geometry;
  if (nonIndexed !== geometry) geometry.dispose();
  nonIndexed.applyMatrix4(matrix);
  if (matrix.determinant() < 0) {
    for (const attribute of Object.values(nonIndexed.attributes)) {
      const array = attribute.array;
      for (let i = 0; i < attribute.count; i += 3) {
        for (let k = 0; k < attribute.itemSize; k++) {
          const a = (i + 1) * attribute.itemSize + k,
            b = (i + 2) * attribute.itemSize + k;
          [array[a], array[b]] = [array[b], array[a]];
        }
      }
    }
  }
  return nonIndexed;
}
function transform(
  x: number,
  y: number,
  z: number,
  rx = 0,
  ry = 0,
  rz = 0,
  sx = 1,
) {
  return new Matrix4()
    .makeTranslation(x, y, z)
    .multiply(new Matrix4().makeRotationX(rx))
    .multiply(new Matrix4().makeRotationY(ry))
    .multiply(new Matrix4().makeRotationZ(rz))
    .multiply(new Matrix4().makeScale(sx, 1, 1));
}
const white: BufferGeometry[] = [],
  dark: BufferGeometry[] = [],
  gear: BufferGeometry[] = [];
const box = (
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
) => placed(new BoxGeometry(w, h, d), transform(x, y, z));
const wing = (points: number[][], matrix: Matrix4, depth = 0.18) =>
  placed(
    new ExtrudeGeometry(new Shape(points.map((p) => new Vector2(p[0], p[1]))), {
      depth,
      bevelEnabled: false,
    }),
    matrix,
  );
const profile = [
  [0, -17],
  [0.6, -16.4],
  [1.4, -14.8],
  [1.8, -12],
  [1.85, -8],
  [1.85, 7],
  [1.6, 11],
  [1.1, 14],
  [0.4, 16.5],
  [0, 17],
].map((p) => new Vector2(p[0], p[1]));
const fuselage = placed(
  new LatheGeometry(profile, 28),
  transform(0, 3, 0, Math.PI / 2),
);
white.push(fuselage.clone());
for (const side of [-1, 1]) {
  for (let z = -10; z < 10; z += 1.1)
    dark.push(box(side * 1.82, 3.5, z, 0.05, 0.32, 0.46));
  white.push(
    wing(
      [
        [1, -5],
        [14, -0.1],
        [16, 3],
        [5, 3],
        [1, 5],
      ],
      transform(0, 2.8, 0, -Math.PI / 2, 0, 0, side),
    ),
  );
  white.push(
    wing(
      [
        [0.7, -2],
        [6, 1],
        [6.5, 3],
        [1, 2],
      ],
      transform(0, 3, 11, -Math.PI / 2, 0, 0, side),
    ),
  );
  white.push(
    placed(
      new CylinderGeometry(1.15, 0.9, 3.8, 20),
      transform(side * 7, 2.1, -1.5, Math.PI / 2),
    ),
  );
  dark.push(
    placed(
      new CircleGeometry(0.9, 20),
      transform(side * 7, 2.1, -3.42, 0, Math.PI),
    ),
  );
  gear.push(box(side * 2, 1.1, 3, 0.22, 2, 0.22));
  for (const z of [2.6, 3.5])
    gear.push(
      placed(
        new CylinderGeometry(0.55, 0.55, 0.7, 10),
        transform(side * 2, 0.55, z, 0, 0, Math.PI / 2),
      ),
    );
  white.push(box(side * 15.2, 3.5, 1.4, 0.22, 2, 1.5));
}
white.push(
  wing(
    [
      [-3, 0],
      [2, 0],
      [2, 6],
      [0.5, 6],
    ],
    transform(0, 5.5, 12.5, 0, Math.PI / 2),
    0.25,
  ),
);
gear.push(box(0, 1.1, -11, 0.22, 2, 0.22));
gear.push(
  placed(
    new CylinderGeometry(0.45, 0.45, 0.8, 10),
    transform(0, 0.5, -11, 0, 0, Math.PI / 2),
  ),
);
function merged(parts: BufferGeometry[]) {
  const geometry = mergeGeometries(parts)!;
  parts.forEach((part) => part.dispose());
  geometry.computeBoundingSphere();
  return geometry;
}
export const aircraftGeometry = {
  white: merged(white),
  dark: merged(dark),
  gear: merged(gear),
  cockpit: box(0, 3.75, -14.2, 2.1, 0.52, 1.3),
  fuselage,
};
