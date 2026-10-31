import { useEffect, useMemo, useRef } from "react";
import type { RefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Vector3 } from "three";
import type { Group } from "three";
import { Aircraft } from "./aircraft";
import { advanceSceneTime, makeTrafficRoutes } from "./motion";

export type SceneClock = RefObject<number>;

/** Demand rendering stays asleep when paused; only ambient frames are capped. */
export function SceneClockDriver({
  clock,
  running,
  fps,
  shadowKey,
  onSlow,
}: {
  clock: SceneClock;
  running: boolean;
  fps: number;
  shadowKey: string;
  onSlow: () => void;
}) {
  const { invalidate, gl } = useThree();
  const sample = useRef({ elapsed: 0, frames: 0, slow: 0, reported: false });
  useEffect(() => {
    if (!running) return;
    invalidate();
    const timer = window.setInterval(invalidate, 1000 / fps);
    return () => window.clearInterval(timer);
  }, [running, fps, invalidate]);
  useEffect(() => {
    const previous = gl.shadowMap.autoUpdate;
    gl.shadowMap.autoUpdate = false;
    gl.shadowMap.needsUpdate = true;
    invalidate();
    return () => {
      gl.shadowMap.autoUpdate = previous;
    };
  }, [gl, invalidate, shadowKey]);
  useFrame((_, delta) => {
    clock.current = advanceSceneTime(clock.current, delta, running);
    if (!running) {
      sample.current.elapsed = 0;
      sample.current.frames = 0;
      return;
    }
    const s = sample.current;
    s.elapsed += Math.min(delta, 0.25);
    s.frames++;
    if (s.elapsed >= 1) {
      const measured = s.frames / s.elapsed;
      s.slow = measured < fps * 0.65 ? s.slow + 1 : 0;
      if (s.slow >= 3 && !s.reported) {
        s.reported = true;
        onSlow();
      }
      if (import.meta.env.DEV) {
        gl.domElement.dataset.sceneTime = clock.current.toFixed(2);
        gl.domElement.dataset.sceneFps = measured.toFixed(1);
        gl.domElement.dataset.drawCalls = String(gl.info.render.calls);
        gl.domElement.dataset.triangles = String(gl.info.render.triangles);
      }
      s.elapsed = 0;
      s.frames = 0;
    }
  }, -1);
  return null;
}

const origin: [number, number, number] = [0, 0, 0];
/** Decorative traffic has no flight IDs, no negotiation state and no authority. */
export function AirportTraffic({
  clock,
  runwayZ,
}: {
  clock: SceneClock;
  runwayZ: number | null;
}) {
  const flight = useRef<Group>(null),
    holding = useRef<Group>(null);
  const routes = useMemo(() => makeTrafficRoutes(runwayZ ?? -218), [runwayZ]);
  const tangent = useMemo(() => new Vector3(), []);
  useFrame(() => {
    const t = clock.current;
    if (flight.current) {
      const phase = t % 200;
      const departure = phase < 100;
      const progress = (phase % 100) / 92;
      flight.current.visible = runwayZ !== null && progress < 1;
      if (flight.current.visible) {
        const route = departure ? routes.departure : routes.arrival;
        route.getPointAt(Math.min(progress, 1), flight.current.position);
        flight.current.position.y = Math.max(0, flight.current.position.y);
        route.getTangentAt(Math.min(progress, 1), tangent);
        flight.current.rotation.set(
          Math.asin(Math.max(-0.2, Math.min(0.2, tangent.y))),
          Math.atan2(-tangent.x, -tangent.z),
          0,
          "YXZ",
        );
      }
    }
    if (holding.current) {
      const angle = t * 0.038 + 2;
      holding.current.position.set(
        -100 + Math.sin(angle) * 150,
        52 + Math.sin(angle * 0.5) * 5,
        -50 + Math.cos(angle) * 90,
      );
      holding.current.rotation.set(
        0,
        Math.atan2(-Math.cos(angle) * 150, Math.sin(angle) * 90),
        -0.12,
        "YXZ",
      );
    }
  });
  return (
    <group name="illustrative-traffic">
      <group ref={flight} name="taxi-departure-arrival">
        <Aircraft position={origin} moving />
      </group>
      <group ref={holding} name="holding-aircraft">
        <Aircraft position={origin} moving />
      </group>
    </group>
  );
}
