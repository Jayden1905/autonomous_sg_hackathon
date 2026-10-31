import { useEffect, useRef } from "react";
import { CameraControls } from "@react-three/drei";
import type { Point } from "./layout";

export type CameraIntent = {
  action: "home" | "top" | "focus" | "in" | "out";
  sequence: number;
};
export function AirportCamera({
  intent,
  target,
  reducedMotion,
}: {
  intent: CameraIntent;
  target: Point;
  reducedMotion: boolean;
}) {
  const camera = useRef<CameraControls>(null);
  const targetRef = useRef(target);
  targetRef.current = target;
  useEffect(() => {
    const controls = camera.current;
    if (!controls) return;
    const animate = !reducedMotion;
    const [x, y, z] = targetRef.current;
    switch (intent.action) {
      case "home":
        void controls.setLookAt(140, 155, 180, -10, 0, -35, animate);
        break;
      case "top":
        void controls.setLookAt(0, 340, 1, 0, 0, -25, animate);
        break;
      case "focus":
        void controls.setLookAt(x + 52, y + 65, z + 75, x, y, z, animate);
        break;
      case "in":
        void controls.dolly(30, animate);
        break;
      case "out":
        void controls.dolly(-30, animate);
        break;
    }
  }, [intent, reducedMotion]);
  return (
    <CameraControls
      ref={camera}
      makeDefault
      minDistance={35}
      maxDistance={560}
      maxPolarAngle={Math.PI / 2.2}
      minPolarAngle={0.02}
      draggingSmoothTime={reducedMotion ? 0 : 0.12}
      smoothTime={reducedMotion ? 0 : 0.25}
    />
  );
}
