import { Box, Blocks, materials } from "./geometry";
import type { Block } from "./geometry";
import type { Point } from "./layout";
import { concourses, northStandXs } from "./scenery-layout";

function Concourse({
  position,
  length,
  rotation = 0,
}: {
  position: Point;
  length: number;
  rotation?: number;
}) {
  const frames: Block[] = [],
    lights: Block[] = [],
    vents: Block[] = [],
    seams: Block[] = [],
    grilles: Block[] = [],
    ducts: Block[] = [];
  for (let x = -length / 2 + 2; x < length / 2; x += 3)
    for (const side of [-1, 1]) {
      frames.push({ position: [x, 5.8, side * 8.12], scale: [0.16, 6, 0.16] });
      if (Math.round(x) % 3 !== 0)
        lights.push({
          position: [x + 1.4, 4.5, side * 8.05],
          scale: [2.5, 1.5, 0.07],
        });
    }
  for (let x = -length / 2 + 6; x < length / 2; x += 12) {
    vents.push({ position: [x, 9.6, 1], scale: [3.2, 0.9, 2.5] });
    // Small louvres and duct runs give equipment depth; StaticBatch merges them.
    for (let fin = -3; fin <= 3; fin++)
      grilles.push({
        position: [x + fin * 0.36, 10.07, 1],
        scale: [0.13, 0.06, 1.95],
      });
    ducts.push({ position: [x + 2.5, 9.42, 1], scale: [2, 0.45, 0.75] });
    seams.push({ position: [x, 9.16, 0], scale: [0.09, 0.06, 17] });
  }
  return (
    <group position={position} rotation-y={rotation}>
      <Box position={[0, 1.5, 0]} scale={[length, 3, 16]} material="wall" />
      <Box position={[0, 5.8, 0]} scale={[length, 5.8, 16]} material="glass" />
      <Blocks blocks={lights} material="window" />
      <Blocks blocks={frames} material="edge" />
      <Box position={[0, 8.9, 0]} scale={[length + 1.4, 0.5, 17.5]} />
      <Box
        position={[0, 3, 0]}
        scale={[length + 0.4, 0.35, 16.5]}
        material="edge"
      />
      <Blocks blocks={vents} material="concrete" />
      <Blocks blocks={grilles} material="dark" />
      <Blocks blocks={ducts} material="edge" />
      <Blocks blocks={seams} material="edge" />
      {[-1, 1].map((side) => (
        <group key={`end-${side}`} position={[(side * length) / 2, 0, 0]}>
          <mesh
            position={[0, 1.5, 0]}
            material={materials.wall}
            castShadow
            receiveShadow
          >
            <cylinderGeometry args={[8, 8, 3, 32]} />
          </mesh>
          <mesh position={[0, 5.8, 0]} material={materials.glass} castShadow>
            <cylinderGeometry args={[8, 8, 5.8, 32]} />
          </mesh>
          <mesh
            position={[0, 8.9, 0]}
            material={materials.roof}
            castShadow
            receiveShadow
          >
            <cylinderGeometry args={[8.75, 8.75, 0.5, 32]} />
          </mesh>
          {Array.from({ length: 16 }, (_, i) => {
            const a = (i * Math.PI) / 8;
            return (
              <Box
                key={i}
                position={[Math.cos(a) * 8.05, 5.8, Math.sin(a) * 8.05]}
                scale={[0.13, 5.8, 0.13]}
                material="edge"
              />
            );
          })}
        </group>
      ))}
      {[-5, 0, 5].map((z) => (
        <Box
          key={`seam-${z}`}
          position={[0, 9.18, z]}
          scale={[length, 0.05, 0.08]}
          material="edge"
        />
      ))}
      {[-1, 1].map((side) => (
        <Box
          key={side}
          position={[0, 9.35, side * 8.5]}
          scale={[length + 0.7, 0.5, 0.22]}
          material="edge"
        />
      ))}
    </group>
  );
}

export function JetBridge({
  position,
  rotation = 0,
}: {
  position: Point;
  rotation?: number;
}) {
  const ribs: Block[] = Array.from({ length: 12 }, (_, i) => ({
    position: [0, 4.1, 2 + i * 0.8],
    scale: [3.4, 0.12, 0.12],
  }));
  return (
    <group position={position} rotation-y={rotation}>
      <mesh position={[0, 4, 0]} material={materials.edge} castShadow>
        <cylinderGeometry args={[2, 2, 3, 16]} />
      </mesh>
      <Box position={[0, 4, 6]} scale={[3.2, 2.6, 12]} material="edge" />
      <Box position={[0, 4.2, 6]} scale={[3.24, 1.35, 11.5]} material="glass" />
      <Box position={[0, 5.5, 6]} scale={[3.5, 0.3, 12.5]} material="roof" />
      <Blocks blocks={ribs} material="edge" />
      <Box position={[0, 3.9, 12.6]} scale={[3.8, 3.1, 2]} material="rubber" />
      <Box position={[0, 4, 13.7]} scale={[3.4, 2.7, 0.25]} material="edge" />
      <Box position={[0, 1.7, 9]} scale={[0.6, 3.4, 0.6]} material="edge" />
      <Box position={[0, 0.7, 9]} scale={[3.5, 0.5, 1.4]} material="dark" />
      {[-1.5, 1.5].map((x) => (
        <mesh
          key={x}
          position={[x, 0.5, 9]}
          material={materials.rubber}
          rotation-z={Math.PI / 2}
        >
          <cylinderGeometry args={[0.5, 0.5, 0.4, 10]} />
        </mesh>
      ))}
      {Array.from({ length: 10 }, (_, i) => (
        <Box
          key={i}
          position={[2.3, 0.35 + i * 0.32, 11 - i * 0.6]}
          scale={[1.3, 0.2, 0.65]}
          material="edge"
        />
      ))}
    </group>
  );
}

function Tower() {
  return (
    <group position={[-100, 0, -46]}>
      <mesh position={[0, 18, 0]} material={materials.concrete} castShadow>
        <cylinderGeometry args={[2.8, 4, 36, 12]} />
      </mesh>
      <mesh position={[0, 36, 0]} material={materials.glass} castShadow>
        <cylinderGeometry args={[6, 4.7, 5, 8]} />
      </mesh>
      <mesh position={[0, 39, 0]} material={materials.roof} castShadow>
        <cylinderGeometry args={[6.6, 6.6, 1, 8]} />
      </mesh>
      <Box position={[0, 43, 0]} scale={[0.25, 8, 0.25]} material="edge" />
    </group>
  );
}

export const Terminal = memo(function Terminal() {
  return (
    <group>
      {concourses.map((concourse, index) => (
        <Concourse key={index} {...concourse} />
      ))}
      <Tower />
      {[-80, -49, -18, 13, 44, 75].map((x) => (
        <JetBridge key={x} position={[x - 6, 0, 9]} />
      ))}
      {northStandXs.map((x) => (
        <JetBridge key={x} position={[x + 6, 0, -9]} rotation={Math.PI} />
      ))}
      {[-65, -32, 1, 34, 67].map((x) => (
        <JetBridge key={x} position={[x - 6, 0, -74]} />
      ))}
    </group>
  );
});
import { memo } from "react";
