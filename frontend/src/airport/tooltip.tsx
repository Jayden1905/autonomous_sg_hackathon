import { Html } from "@react-three/drei";
import type { RefObject } from "react";
import { Plane } from "lucide-react";
import { Vector3 } from "three";
import type { Camera, Object3D } from "three";
import { relativeMinutes, displayPlan } from "@/workspace";
import type { FlightView } from "@/workspace";
import type { Point } from "./layout";
import styles from "./airport.module.css";

/** Reserve the shared inspector's right-hand area without depending on its DOM. */
export function tooltipPosition(
  object: Object3D,
  camera: Camera,
  size: { width: number; height: number },
  inspectorWidth: number,
): [number, number] {
  const point = new Vector3()
    .setFromMatrixPosition(object.matrixWorld)
    .project(camera);
  const right = size.width >= 900 ? inspectorWidth + 72 : 16;
  return [
    Math.max(
      16,
      Math.min(
        ((point.x + 1) * size.width) / 2 - 110,
        size.width - right - 220,
      ),
    ),
    Math.max(
      16,
      Math.min(((-point.y + 1) * size.height) / 2 - 170, size.height - 190),
    ),
  ];
}

export function AircraftTooltip({
  view,
  position,
  inspectorWidth,
  portal,
}: {
  view: FlightView;
  position: Point;
  inspectorWidth: number;
  portal: RefObject<HTMLDivElement>;
}) {
  const { scenario, proposal, context } = view;
  const plan = displayPlan(view);
  return (
    <Html
      portal={portal}
      position={[position[0], 8, position[2]]}
      calculatePosition={(o, c, s) => tooltipPosition(o, c, s, inspectorWidth)}
      zIndexRange={[12, 10]}
      style={{ pointerEvents: "none" }}
    >
      <div className={styles.tooltip}>
        <strong>
          <Plane size={16} />
          {scenario.flight}
        </strong>
        <p>
          {scenario.origin_info?.city ?? scenario.origin} →{" "}
          {scenario.destination_info?.city ?? scenario.destination}
        </p>
        <div>
          <span>
            {proposal
              ? context === "no_legal_option"
                ? "Last attempted arrival"
                : "Proposed arrival"
              : "Earliest arrival"}
          </span>
          <b>
            {relativeMinutes(
              proposal?.arrival_min ?? scenario.earliest_arrival_min,
            )}
          </b>
        </div>
        <p>
          {proposal
            ? `${proposal.runway} · ${proposal.gate}`
            : "Runway / gate unassigned"}
        </p>
        <small
          className={context === "no_legal_option" ? styles.failure : undefined}
        >
          {plan.label}
        </small>
      </div>
    </Html>
  );
}
