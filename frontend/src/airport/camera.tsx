import { useEffect, useRef } from "react";
import { useThree } from "@react-three/fiber";
import { CameraControls } from "@react-three/drei";
import type { Point } from "./layout";
import type { PlanFocus } from "./plan-focus";

export type CameraIntent = {
  action: "home" | "top" | "focus" | "in" | "out";
  sequence: number;
};
export function AirportCamera({
  intent,
  target,
  selectionKey,
  selectionDistance,
  cue,
  following,
  onExplore,
  inspectorWidth,
  reducedMotion,
  initialFocus,
}: {
  intent: CameraIntent;
  target: Point | null;
  selectionKey: string;
  selectionDistance: number;
  cue: PlanFocus;
  following: boolean;
  onExplore: () => void;
  inspectorWidth: number;
  reducedMotion: boolean;
  initialFocus: boolean;
}) {
  const camera = useRef<CameraControls>(null);
  const { size, invalidate } = useThree();
  const latest = useRef({ target, cue, selectionDistance });
  latest.current = { target, cue, selectionDistance };
  const previous = useRef<{
    selection: string;
    cue: string;
    command: number;
    following: boolean;
  } | null>(null);
  useEffect(() => {
    const controls = camera.current;
    if (!controls) return;
    const before = previous.current;
    previous.current = {
      selection: selectionKey,
      cue: cue.key,
      command: intent.sequence,
      following,
    };
    const animate = !reducedMotion;
    const frame = (point: Point, distance: number) => {
      const [x, y, z] = point;
      // Shift the subject into the visible canvas to the left of the inspector.
      const offset =
        (distance * Math.tan((21 * Math.PI) / 180) * inspectorWidth) /
        size.height;
      void controls.setFocalOffset(offset, 0, 0, animate);
      void controls.setLookAt(
        x + distance * 0.5,
        y + distance * 0.65,
        z + distance * 0.57,
        x,
        y,
        z,
        animate,
      );
      invalidate();
    };
    if (!before && initialFocus && latest.current.target) {
      frame(latest.current.target, latest.current.selectionDistance);
      return;
    }
    if (!before || before.command !== intent.sequence) {
      switch (intent.action) {
        case "home":
          void controls.setFocalOffset(0, 0, 0, animate);
          void controls.setLookAt(140, 155, 180, -10, 0, -35, animate);
          break;
        case "top":
          void controls.setFocalOffset(0, 0, 0, animate);
          void controls.setLookAt(0, 340, 1, 0, 0, -25, animate);
          break;
        case "focus":
          if (latest.current.target)
            frame(latest.current.target, latest.current.selectionDistance);
          break;
        case "in":
          void controls.dolly(30, animate);
          break;
        case "out":
          void controls.dolly(-30, animate);
          break;
      }
      invalidate();
      return;
    }
    if (before.selection !== selectionKey) {
      if (latest.current.target)
        frame(latest.current.target, latest.current.selectionDistance);
      return;
    }
    if (following && (before.cue !== cue.key || !before.following)) {
      // Coalesce fast proposal/evaluation bursts; latest result wins.
      const timer = window.setTimeout(
        () => frame(latest.current.cue.target, latest.current.cue.distance),
        reducedMotion ? 0 : 250,
      );
      return () => window.clearTimeout(timer);
    }
  }, [
    intent,
    selectionKey,
    cue.key,
    following,
    inspectorWidth,
    reducedMotion,
    size.height,
    invalidate,
    initialFocus,
  ]);
  return (
    <CameraControls
      ref={camera}
      makeDefault
      onControl={onExplore}
      minDistance={35}
      maxDistance={560}
      maxPolarAngle={Math.PI / 2.2}
      minPolarAngle={0.02}
      draggingSmoothTime={reducedMotion ? 0 : 0.12}
      smoothTime={reducedMotion ? 0 : 0.55}
    />
  );
}
