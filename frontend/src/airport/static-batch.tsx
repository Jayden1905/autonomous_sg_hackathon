import { useLayoutEffect, useRef } from "react";
import type { ReactNode } from "react";
import { useThree } from "@react-three/fiber";
import { Group, InstancedMesh, Matrix4, Mesh } from "three";
import type { BufferGeometry, Material } from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

/** Bake fixed meshes/instances by material and shadow flags. Never use for moving objects or Lines. */
export function bakeStaticMeshes(source: Group) {
  source.updateWorldMatrix(true, true);
  const inverse = source.matrixWorld.clone().invert();
  const buckets = new Map<
    string,
    {
      material: Material;
      cast: boolean;
      receive: boolean;
      parts: BufferGeometry[];
    }
  >();
  const local = new Matrix4(),
    matrix = new Matrix4();
  source.traverse((object) => {
    if (!(object instanceof Mesh) || Array.isArray(object.material)) return;
    const key = `${object.material.uuid}:${object.castShadow}:${object.receiveShadow}`;
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = {
        material: object.material,
        cast: object.castShadow,
        receive: object.receiveShadow,
        parts: [],
      };
      buckets.set(key, bucket);
    }
    const instances = object instanceof InstancedMesh ? object.count : 1;
    for (let i = 0; i < instances; i++) {
      matrix.multiplyMatrices(inverse, object.matrixWorld);
      if (object instanceof InstancedMesh) {
        object.getMatrixAt(i, local);
        matrix.multiply(local);
      }
      const geometry = object.geometry.index
        ? object.geometry.toNonIndexed()
        : object.geometry.clone();
      geometry.applyMatrix4(matrix);
      bucket.parts.push(geometry);
    }
  });
  const baked = new Group();
  for (const bucket of buckets.values()) {
    const geometry = mergeGeometries(bucket.parts);
    bucket.parts.forEach((part) => part.dispose());
    if (!geometry)
      throw new Error("Static airport geometry could not be batched.");
    geometry.computeBoundingSphere();
    const mesh = new Mesh(geometry, bucket.material);
    mesh.castShadow = bucket.cast;
    mesh.receiveShadow = bucket.receive;
    mesh.matrixAutoUpdate = false;
    baked.add(mesh);
  }
  return baked;
}

export function StaticBatch({ children }: { children: ReactNode }) {
  const source = useRef<Group>(null);
  const root = useRef<Group>(null);
  const { gl, invalidate } = useThree();
  useLayoutEffect(() => {
    if (!source.current || !root.current) return;
    const original = source.current,
      parent = root.current;
    const baked = bakeStaticMeshes(original);
    original.visible = false;
    parent.add(baked);
    gl.shadowMap.needsUpdate = true;
    invalidate();
    return () => {
      parent.remove(baked);
      original.visible = true;
      baked.traverse((object) => {
        if (object instanceof Mesh) object.geometry.dispose();
      });
    };
  }, [gl, invalidate]);
  return (
    <group ref={root}>
      <group ref={source}>{children}</group>
    </group>
  );
}
