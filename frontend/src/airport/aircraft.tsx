import { useMemo } from "react";
import { Edges } from "@react-three/drei";
import { Shape, Vector2 } from "three";
import type { ThreeEvent } from "@react-three/fiber";
import { Box, Blocks, materials } from "./geometry";
import type { Block } from "./geometry";
import type { Point } from "./layout";

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
].map(([r, z]) => new Vector2(r, z));
function Wing({
  points,
  position = [0, 0, 0],
  vertical = false,
}: {
  points: [number, number][];
  position?: Point;
  vertical?: boolean;
}) {
  const shape = useMemo(
    () => new Shape(points.map(([x, y]) => new Vector2(x, y))),
    [points],
  );
  return (
    <mesh
      position={position}
      rotation-x={vertical ? 0 : -Math.PI / 2}
      material={materials.white}
      castShadow
    >
      <extrudeGeometry args={[shape, { depth: 0.18, bevelEnabled: false }]} />
    </mesh>
  );
}

export function Aircraft({
  position,
  rotation = 0,
  selected = false,
  onSelect,
}: {
  position: Point;
  rotation?: number;
  selected?: boolean;
  onSelect?: () => void;
}) {
  const windows: Block[] = [];
  for (const side of [-1, 1])
    for (let z = -10; z < 10; z += 1.1)
      windows.push({
        position: [side * 1.82, 3.5, z],
        scale: [0.05, 0.32, 0.46],
      });
  const click = (event: ThreeEvent<MouseEvent>) => {
    if (onSelect) {
      event.stopPropagation();
      onSelect();
    }
  };
  return (
    <group position={position} rotation-y={rotation} onClick={click}>
      <mesh
        position={[0, 3, 0]}
        rotation-x={Math.PI / 2}
        material={materials.white}
        castShadow
      >
        <latheGeometry args={[profile, 28]} />
        {selected && <Edges color="#2453ff" threshold={24} />}
      </mesh>
      <Blocks blocks={windows} material="dark" />
      <Box
        position={[0, 3.75, -14.2]}
        scale={[2.1, 0.52, 1.3]}
        material="glass"
      />
      {[-1, 1].map((side) => (
        <group key={side} scale={[side, 1, 1]}>
          <Wing
            position={[0, 2.8, 0]}
            points={[
              [1, -5],
              [14, -0.1],
              [16, 3],
              [5, 3],
              [1, 5],
            ]}
          />
          <Wing
            position={[0, 3, 11]}
            points={[
              [0.7, -2],
              [6, 1],
              [6.5, 3],
              [1, 2],
            ]}
          />
          <mesh
            position={[7, 2.1, -1.5]}
            rotation-x={Math.PI / 2}
            material={materials.white}
            castShadow
          >
            <cylinderGeometry args={[1.15, 0.9, 3.8, 20]} />
          </mesh>
          <mesh
            position={[7, 2.1, -3.42]}
            rotation-x={Math.PI / 2}
            material={materials.dark}
          >
            <circleGeometry args={[0.9, 20]} />
          </mesh>
          <Box position={[2, 1.1, 3]} scale={[0.22, 2, 0.22]} material="edge" />
          {[2.6, 3.5].map((z) => (
            <mesh
              key={z}
              position={[2, 0.55, z]}
              rotation-z={Math.PI / 2}
              material={materials.rubber}
            >
              <cylinderGeometry args={[0.55, 0.55, 0.7, 10]} />
            </mesh>
          ))}
          <Box
            position={[15.2, 3.5, 1.4]}
            scale={[0.22, 2, 1.5]}
            material="white"
          />
        </group>
      ))}
      <mesh
        position={[0, 5.5, 12.5]}
        rotation-y={Math.PI / 2}
        material={materials.white}
        castShadow
      >
        <extrudeGeometry
          args={[
            new Shape([
              new Vector2(-3, 0),
              new Vector2(2, 0),
              new Vector2(2, 6),
              new Vector2(0.5, 6),
            ]),
            { depth: 0.25, bevelEnabled: false },
          ]}
        />
      </mesh>
      <Box position={[0, 1.1, -11]} scale={[0.22, 2, 0.22]} material="edge" />
      <mesh
        position={[0, 0.5, -11]}
        rotation-z={Math.PI / 2}
        material={materials.rubber}
      >
        <cylinderGeometry args={[0.45, 0.45, 0.8, 10]} />
      </mesh>
    </group>
  );
}
