import { expect, it } from "vitest";
import {
  BoxGeometry,
  Group,
  InstancedMesh,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
} from "three";
import { bakeStaticMeshes } from "./static-batch";

it("batches repeated static parts without losing their world placements", () => {
  const root = new Group();
  root.position.x = 100;
  const geometry = new BoxGeometry(2, 2, 2),
    material = new MeshStandardMaterial();
  const a = new Mesh(geometry, material);
  a.position.x = 5;
  root.add(a);
  const nested = new Group();
  nested.position.x = 10;
  root.add(nested);
  const instances = new InstancedMesh(geometry, material, 2);
  instances.setMatrixAt(0, new Matrix4().makeTranslation(5, 0, 0));
  instances.setMatrixAt(1, new Matrix4().makeTranslation(10, 0, 0));
  nested.add(instances);
  const baked = bakeStaticMeshes(root);
  expect(baked.children.length).toBe(1);
  const mesh = baked.children[0] as Mesh;
  mesh.geometry.computeBoundingBox();
  expect(mesh.geometry.boundingBox!.min.x).toBe(4);
  expect(mesh.geometry.boundingBox!.max.x).toBe(21);
  expect(mesh.geometry.getAttribute("position").count).toBe(108);
  mesh.geometry.dispose();
  geometry.dispose();
  material.dispose();
});
