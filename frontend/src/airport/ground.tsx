import { useMemo } from "react";
import { Line } from "@react-three/drei";
import { Box, Blocks, materials } from "./geometry";
import type { Block } from "./geometry";
import { ApronMaterial } from "./apron-material";

function markings(strips: readonly number[]) {
  const dashes: Block[] = [];
  const thresholds: Block[] = [];
  for (const z of strips) {
    for (let x = -240; x <= 240; x += 16)
      dashes.push({ position: [x, 0.07, z], scale: [8, 0.04, 0.6] });
    for (const side of [-1, 1])
      for (let i = -5; i <= 5; i++)
        thresholds.push({
          position: [side * 222, 0.08, z + i * 1.3],
          scale: [15, 0.04, 0.7],
        });
  }
  return { dashes, thresholds };
}

function ServiceVehicle({
  x,
  z,
  long = false,
}: {
  x: number;
  z: number;
  long?: boolean;
}) {
  return (
    <group position={[x, 0, z]} rotation-y={Math.PI / 2}>
      <Box
        position={[0, 0.8, 0]}
        scale={[2, 1.3, long ? 5 : 3.3]}
        material="white"
      />
      <Box position={[0, 1.7, -0.9]} scale={[1.9, 0.8, 1.5]} material="white" />
      <Box
        position={[0, 1.7, -1.7]}
        scale={[1.6, 0.55, 0.08]}
        material="glass"
      />
      {[-1, 1].flatMap((side) =>
        [-1, 1].map((end) => (
          <mesh
            key={`${side}-${end}`}
            position={[side, 0.45, end]}
            rotation-z={Math.PI / 2}
            material={materials.rubber}
          >
            <cylinderGeometry args={[0.4, 0.4, 0.25, 8]} />
          </mesh>
        )),
      )}
    </group>
  );
}

/** `strips`: z of each runway to draw, one per runway in the scenario. */
export function Ground({
  wet = false,
  strips = [-158, -218],
}: {
  wet?: boolean;
  strips?: readonly number[];
}) {
  const { dashes, thresholds } = useMemo(() => markings(strips), [strips]);
  return (
    <group>
      <Box
        position={[0, -0.3, 0]}
        scale={[2400, 0.5, 2400]}
        material="grass"
        castShadow={false}
      />
      <mesh position={[0, -0.04, 20]} scale={[1200, 0.08, 300]} receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <ApronMaterial wet={wet} />
      </mesh>
      {strips.map((z) => (
        <group key={z}>
          <Box
            position={[0, 0.025, z]}
            scale={[530, 0.05, 23]}
            material="asphalt"
          />
          {[-1, 1].map((side) => (
            <Box
              key={side}
              position={[0, 0.065, z + side * 10.6]}
              scale={[524, 0.025, 0.2]}
              material="white"
            />
          ))}
        </group>
      ))}
      <Blocks blocks={dashes} material="white" shadows={false} />
      <Blocks blocks={thresholds} material="white" shadows={false} />
      <Box
        position={[0, 0.025, -113]}
        scale={[550, 0.04, 15]}
        material="asphalt"
      />
      <Box
        position={[282, 0.025, -48]}
        scale={[16, 0.04, 340]}
        material="asphalt"
        castShadow={false}
      />
      <Box
        position={[245, 0.025, -218]}
        scale={[90, 0.04, 16]}
        material="asphalt"
        castShadow={false}
      />
      {[-120, 0, 160].map((x) => (
        <Box
          key={x}
          position={[x, 0.024, -165]}
          scale={[16, 0.04, 110]}
          material="asphalt"
        />
      ))}
      <Line
        points={[
          [-270, 0.09, -113],
          [260, 0.09, -113],
        ]}
        color="#d0ba72"
        lineWidth={1}
      />
      <Line
        points={[
          [-550, 0.09, 122],
          [235, 0.09, 122],
          [282, 0.09, 45],
          [282, 0.09, -218],
          [210, 0.09, -218],
        ]}
        color="#c7ad60"
        lineWidth={1}
      />
      {[-80, -49, -18, 13, 44, 75].map((x) => (
        <group key={x}>
          <Line
            points={[
              [x, 0.08, 22],
              [x, 0.08, 62],
              [x + 8, 0.08, 74],
              [x + 18, 0.08, 81],
            ]}
            color="#cbb269"
            lineWidth={1}
          />
          <Line
            points={[
              [x - 13, 0.08, 22],
              [x - 13, 0.08, 57],
              [x + 13, 0.08, 57],
              [x + 13, 0.08, 22],
            ]}
            color="#bcb38f"
            lineWidth={0.7}
          />
          <Line
            points={[
              [x - 5, 0.08, 28],
              [x + 5, 0.08, 28],
            ]}
            color="#d0b36a"
            lineWidth={1}
          />
          <ServiceVehicle x={x + 11} z={17} />
          <ServiceVehicle x={x + 12} z={47} long />
        </group>
      ))}
      {[-90, -45, 0, 45, 90].map((x) => (
        <group key={x} position={[x, 0, 95]}>
          <Box position={[0, 9, 0]} scale={[0.22, 18, 0.22]} material="edge" />
          <Box position={[0, 18, 0]} scale={[4, 0.3, 1]} material="white" />
        </group>
      ))}
    </group>
  );
}
