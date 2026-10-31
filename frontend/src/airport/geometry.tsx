import { useLayoutEffect, useRef } from "react";
import type { InstancedMesh } from "three";
import { BoxGeometry, MeshStandardMaterial, Object3D, DoubleSide } from "three";
import type { Point } from "./layout";

import { roofMaterial, asphaltMaterial, vergeMaterial } from "./surface-nodes";

export const materials = {
  concrete: new MeshStandardMaterial({ color: "#727a7b", roughness: 0.96 }),
  roof: roofMaterial(),
  edge: new MeshStandardMaterial({
    color: "#a7b0b3",
    roughness: 0.65,
    metalness: 0.3,
  }),
  wall: new MeshStandardMaterial({ color: "#adb2ae", roughness: 0.85 }),
  glass: new MeshStandardMaterial({
    color: "#526773",
    roughness: 0.16,
    metalness: 0.35,
    envMapIntensity: 1.3,
  }),
  window: new MeshStandardMaterial({
    color: "#c7c7a9",
    emissive: "#b3a371",
    emissiveIntensity: 0.35,
    roughness: 0.4,
    metalness: 0.15,
  }),
  white: new MeshStandardMaterial({
    color: "#f1f1ec",
    roughness: 0.3,
    metalness: 0.05,
    side: DoubleSide,
  }),
  dark: new MeshStandardMaterial({ color: "#26323b", roughness: 0.65 }),
  rubber: new MeshStandardMaterial({ color: "#23262a", roughness: 0.9 }),
  asphalt: asphaltMaterial(),
  grass: vergeMaterial(),
  marking: new MeshStandardMaterial({ color: "#c4ad65", roughness: 0.9 }),
};
export type MaterialName = keyof typeof materials;
const box = new BoxGeometry(1, 1, 1);
export interface Block {
  position: Point;
  scale: Point;
  rotation?: number;
}

export function Box({
  position = [0, 0, 0],
  scale,
  material = "roof",
  rotation = 0,
  castShadow = true,
}: Block & { material?: MaterialName; castShadow?: boolean }) {
  return (
    <mesh
      geometry={box}
      material={materials[material]}
      position={position}
      scale={scale}
      rotation-y={rotation}
      castShadow={castShadow}
      receiveShadow
      dispose={null}
    />
  );
}

/** Repeat architecture with one draw call per material. */
export function Blocks({
  blocks,
  material = "roof",
  shadows = true,
}: {
  blocks: Block[];
  material?: MaterialName;
  shadows?: boolean;
}) {
  const ref = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    const object = new Object3D();
    blocks.forEach((block, i) => {
      object.position.set(...block.position);
      object.scale.set(...block.scale);
      object.rotation.set(0, block.rotation ?? 0, 0);
      object.updateMatrix();
      ref.current?.setMatrixAt(i, object.matrix);
    });
    if (ref.current) {
      ref.current.instanceMatrix.needsUpdate = true;
      ref.current.computeBoundingSphere();
    }
  }, [blocks]);
  return (
    <instancedMesh
      ref={ref}
      args={[box, materials[material], blocks.length]}
      castShadow={shadows}
      receiveShadow
      dispose={null}
    />
  );
}
