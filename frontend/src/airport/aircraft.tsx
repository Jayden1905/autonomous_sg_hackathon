import { memo } from "react";
import { Edges } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import { materials } from "./geometry";
import { aircraftGeometry } from "./aircraft-model";
import type { Point } from "./layout";

export const Aircraft = memo(function Aircraft({
  position,
  rotation = 0,
  selected = false,
  onSelect,
  moving = false,
}: {
  position: Point;
  rotation?: number;
  selected?: boolean;
  onSelect?: () => void;
  moving?: boolean;
}) {
  const click = onSelect
    ? (event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation();
        onSelect();
      }
    : undefined;
  return (
    <group
      name={moving ? "ambient-aircraft" : "parked-aircraft"}
      position={position}
      rotation-y={rotation}
      onClick={click}
      dispose={null}
    >
      <mesh
        geometry={aircraftGeometry.white}
        material={materials.white}
        castShadow={!moving}
      />
      <mesh geometry={aircraftGeometry.dark} material={materials.dark} />
      <mesh geometry={aircraftGeometry.gear} material={materials.rubber} />
      <mesh geometry={aircraftGeometry.cockpit} material={materials.glass} />
      {selected && (
        <Edges
          geometry={aircraftGeometry.fuselage}
          color="#2453ff"
          threshold={24}
        />
      )}
    </group>
  );
});
