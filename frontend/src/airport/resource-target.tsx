import { useState } from "react";
import type { RefObject } from "react";
import { Html, Line, useCursor } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import type { FlightView } from "@/workspace";
import type { Point } from "./layout";
import styles from "./airport.module.css";

export function Footprint({
  position,
  width = 28,
  depth = 39,
  previous = false,
}: {
  position: Point;
  width?: number;
  depth?: number;
  previous?: boolean;
}) {
  const [x, , z] = position;
  const color = previous ? "#757e86" : "#2453ff";
  return (
    <group>
      <mesh position={[x, 0.12, z]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[width, depth]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={previous ? 0.035 : 0.1}
          depthWrite={false}
        />
      </mesh>
      <Line
        points={[
          [x - width / 2, 0.15, z - depth / 2],
          [x + width / 2, 0.15, z - depth / 2],
          [x + width / 2, 0.15, z + depth / 2],
          [x - width / 2, 0.15, z + depth / 2],
          [x - width / 2, 0.15, z - depth / 2],
        ]}
        color={color}
        lineWidth={previous ? 1 : 1.4}
        dashed={previous}
        dashSize={3}
        gapSize={2}
      />
    </group>
  );
}

/** A real ground hit surface plus an equivalent keyboard-accessible label. */
export function ResourceTarget({
  kind,
  id,
  position,
  labelPosition,
  width,
  depth,
  portal,
  selected,
  proposed,
  previous,
  status,
  onSelect,
}: {
  kind: "gate" | "runway";
  id: string;
  position: Point;
  labelPosition: Point;
  width: number;
  depth: number;
  portal: RefObject<HTMLDivElement>;
  selected: boolean;
  proposed: boolean;
  previous: boolean;
  status?: string;
  onSelect: FlightView["onSelect"];
}) {
  const [hovered, setHovered] = useState(false);
  const canvas = useThree((s) => s.gl.domElement);
  useCursor(hovered, "pointer", "auto", canvas);
  const select = () => onSelect({ kind, id });
  return (
    <group>
      <mesh
        name={`resource-${kind}-${id}`}
        position={[position[0], 0.2, position[2]]}
        rotation-x={-Math.PI / 2}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={() => setHovered(false)}
        onClick={(e) => {
          e.stopPropagation();
          if (e.delta <= 4) select();
        }}
      >
        <planeGeometry args={[width, depth]} />
        <meshBasicMaterial
          transparent
          opacity={0}
          depthWrite={false}
          colorWrite={false}
        />
      </mesh>
      {(selected || hovered) && !proposed && (
        <Footprint position={position} width={width} depth={depth} />
      )}
      <Html
        portal={portal}
        position={labelPosition}
        center
        zIndexRange={[9, 1]}
      >
        <button
          className={`${kind === "gate" ? styles.gate : styles.runway} ${selected || proposed ? styles.activeGate : ""}`}
          aria-label={`Select ${kind} ${id}`}
          aria-pressed={selected}
          title={`Inspect ${kind} ${id}${status ? ` · ${status}` : ""}`}
          onPointerEnter={() => setHovered(true)}
          onPointerLeave={() => setHovered(false)}
          onFocus={() => setHovered(true)}
          onBlur={() => setHovered(false)}
          onClick={select}
        >
          {status === "closed" && <span className={styles.cross}>×</span>}
          {id}
          {status && ` · ${status}`}
          {proposed ? (
            <small>Plan</small>
          ) : previous ? (
            <small>Previous</small>
          ) : null}
        </button>
      </Html>
    </group>
  );
}
