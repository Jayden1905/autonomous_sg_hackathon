import { Component, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { Canvas } from "@react-three/fiber";
import { Environment, Lightformer, Html, Line } from "@react-three/drei";
import {
  Focus,
  Minus,
  Plus,
  RotateCcw,
  MousePointer2,
  Map,
  Box as BoxIcon,
  Pause,
  Play,
  CloudRain,
} from "lucide-react";
import type { FlightView } from "@/workspace";
import { IconButton } from "@/workspace";
import { Aircraft } from "./aircraft";
import { Terminal } from "./terminal";
import { Ground } from "./ground";
import { AirportCamera } from "./camera";
import type { CameraIntent } from "./camera";
import { AircraftTooltip } from "./tooltip";
import { resolveScene, unmappedResources } from "./layout";
import type { AirportLayout, Point } from "./layout";
import styles from "./airport.module.css";
import { AirportTraffic, SceneClockDriver } from "./life";
import { Rain, Puddles, weatherLighting } from "./weather";
import { StaticBatch } from "./static-batch";
import { scenarioWeather, sceneBudget, trafficRunway } from "./motion";
import type { Quality, Weather, WeatherChoice } from "./motion";

class RendererBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <RendererUnavailable /> : this.props.children;
  }
}
function RendererUnavailable() {
  return (
    <div className={styles.unavailable} role="status">
      <strong>3D view unavailable</strong>
      <p>Use the Flight tab’s resource list to inspect the scenario.</p>
    </div>
  );
}

function Footprint({
  position,
  width = 28,
  depth = 39,
}: {
  position: Point;
  width?: number;
  depth?: number;
}) {
  const [x, , z] = position;
  return (
    <group>
      <mesh position={[x, 0.12, z]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[width, depth]} />
        <meshBasicMaterial
          color="#2453ff"
          transparent
          opacity={0.1}
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
        color="#2453ff"
        lineWidth={1.4}
      />
    </group>
  );
}

function AirportContents({
  view,
  layout,
  intent,
  reducedMotion,
  inspectorWidth,
  labels,
  weather,
  running,
  budget,
  onSlow,
}: {
  view: FlightView;
  layout: AirportLayout;
  intent: CameraIntent;
  reducedMotion: boolean;
  inspectorWidth: number;
  labels: RefObject<HTMLDivElement>;
  weather: Weather;
  running: boolean;
  budget: ReturnType<typeof sceneBudget>;
  onSlow: () => void;
}) {
  const clock = useRef(18);
  const scene = resolveScene(view, layout);
  const { scenario, selection, onSelect } = view;
  const selectedFlight =
    selection?.kind === "flight" && selection.id === scenario.flight;
  const light = weatherLighting[weather];
  const runway = trafficRunway(scenario, layout);
  const shadowKey = `${scenario.scenario_id}:${scene.aircraft.join(",")}:${budget.shadows}`;
  return (
    <>
      <SceneClockDriver
        clock={clock}
        running={running}
        fps={budget.fps}
        shadowKey={shadowKey}
        onSlow={onSlow}
      />
      <color attach="background" args={[light.background]} />
      <fog attach="fog" args={[light.fog, light.near, light.far]} />
      <hemisphereLight args={["#e3edf5", "#827e6c", light.ambient]} />
      <directionalLight
        position={[-100, 200, 60]}
        intensity={light.sun}
        color="#fff4e4"
        castShadow
        shadow-mapSize={[budget.shadows, budget.shadows]}
        shadow-camera-left={-240}
        shadow-camera-right={240}
        shadow-camera-top={240}
        shadow-camera-bottom={-240}
        shadow-camera-far={550}
        shadow-normalBias={0.1}
        shadow-bias={-0.0001}
      />
      <Environment resolution={128} frames={1}>
        <Lightformer
          form="rect"
          intensity={2}
          scale={[400, 400, 1]}
          position={[0, 200, 0]}
          rotation-x={Math.PI / 2}
        />
        <Lightformer
          form="rect"
          intensity={1}
          scale={[200, 100, 1]}
          position={[-200, 80, 0]}
          rotation-y={Math.PI / 2}
        />
      </Environment>
      <Ground wet={weather !== "clear"} />
      <Puddles wet={weather !== "clear"} />
      <StaticBatch>
        <Terminal />
      </StaticBatch>
      <AirportTraffic
        clock={clock}
        runwayZ={runway ? layout.runways[runway.name][2] : null}
      />
      <Rain
        clock={clock}
        weather={weather}
        count={budget.rain}
        reducedMotion={reducedMotion}
      />
      {[-80, -49, -18, 44, 75]
        .filter((x) => Math.abs(x - scene.aircraft[0]) > 1)
        .map((x) => (
          <Aircraft key={`south-${x}`} position={[x, 0, 39]} />
        ))}
      {[-80, -18, 44, 75].map((x) => (
        <Aircraft
          key={`north-${x}`}
          position={[x, 0, -38]}
          rotation={Math.PI}
        />
      ))}

      <Aircraft
        position={scene.aircraft}
        selected={selectedFlight}
        onSelect={() => onSelect({ kind: "flight", id: scenario.flight })}
      />
      {scene.gate && (
        <Footprint position={[scene.gate[0], 0, scene.gate[2] + 15]} />
      )}
      {scene.runway && (
        <Footprint position={scene.runway} width={490} depth={24} />
      )}
      {scene.selectedAnchor && (
        <Footprint
          position={scene.selectedAnchor}
          width={selection?.kind === "runway" ? 490 : 28}
          depth={selection?.kind === "runway" ? 24 : 38}
        />
      )}
      {scenario.gates.map(
        (g) =>
          layout.gates[g.name] && (
            <Html
              key={g.name}
              portal={labels}
              position={[
                layout.gates[g.name][0] + 12,
                1,
                layout.gates[g.name][2] + 30,
              ]}
              center
              zIndexRange={[9, 1]}
            >
              <button
                className={`${styles.gate} ${view.proposal?.gate === g.name && scene.emphasize ? styles.activeGate : ""}`}
                aria-label={`Select gate ${g.name}`}
                onClick={() => onSelect({ kind: "gate", id: g.name })}
              >
                {g.name}
              </button>
            </Html>
          ),
      )}
      {scenario.runways.map(
        (r) =>
          layout.runways[r.name] && (
            <Html
              key={r.name}
              portal={labels}
              position={[
                layout.runways[r.name][0] - 60,
                2,
                layout.runways[r.name][2],
              ]}
              center
              zIndexRange={[9, 1]}
            >
              <button
                className={styles.runway}
                aria-label={`Select runway ${r.name}`}
                onClick={() => onSelect({ kind: "runway", id: r.name })}
              >
                {!r.open && <span className={styles.cross}>×</span>}
                {r.name}
                {!r.open
                  ? " closed"
                  : r.taxiway_blocked
                    ? " · taxiway blocked"
                    : ""}
              </button>
            </Html>
          ),
      )}
      {selectedFlight && (
        <AircraftTooltip
          view={view}
          position={scene.aircraft}
          inspectorWidth={inspectorWidth}
          portal={labels}
        />
      )}
      <AirportCamera
        intent={intent}
        target={scene.selectedAnchor ?? scene.aircraft}
        reducedMotion={reducedMotion}
      />
    </>
  );
}

export function AirportScene({
  view,
  layout,
  inspectorWidth = 340,
}: {
  view: FlightView;
  layout: AirportLayout;
  inspectorWidth?: number;
}) {
  // The label target must be stable while Canvas connects its event surface.
  // Drei's implicit target changes during that setup and recreates DOM roots,
  // leaving stale roots that fail to unmount when scenario gates change.
  const labels = useRef<HTMLDivElement>(null!);
  const [intent, setIntent] = useState<CameraIntent>({
    action: "home",
    sequence: 0,
  });
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [compact, setCompact] = useState(() => window.innerWidth < 900);
  const [weatherChoice, setWeatherChoice] = useState<WeatherChoice>("scenario");
  const [quality, setQuality] = useState<Quality>("auto");
  const [degraded, setDegraded] = useState(false);
  const weather =
    weatherChoice === "scenario"
      ? scenarioWeather(view.scenario.disruption)
      : weatherChoice;
  const budget = sceneBudget(quality, compact, degraded);
  const running = !paused && !reducedMotion && visible;
  const options = useRef<HTMLDetailsElement>(null);
  const optionTrigger = useRef<HTMLElement>(null);
  const [lost, setLost] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 899px)");
    const resize = () => setCompact(media.matches);
    const visibility = () => setVisible(!document.hidden);
    media.addEventListener("change", resize);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      media.removeEventListener("change", resize);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  const missing = [
    ...new Set([
      ...unmappedResources(view.scenario, layout),
      ...resolveScene(view, layout).missing,
    ]),
  ];
  const command = (action: CameraIntent["action"]) =>
    setIntent((i) => ({ action, sequence: i.sequence + 1 }));
  return (
    <section
      className={styles.airport}
      aria-label="Illustrative 3D airport"
      data-motion={running && !lost ? "playing" : "paused"}
      data-weather={weather}
      data-quality={budget.eco ? "eco" : "high"}
    >
      <div ref={labels} className={styles.labels} />
      <RendererBoundary>
        {lost ? (
          <RendererUnavailable />
        ) : (
          <Canvas
            shadows="percentage"
            dpr={[1, budget.dpr]}
            frameloop="demand"
            camera={{
              position: [140, 155, 180],
              fov: 42,
              near: 0.5,
              far: 1800,
            }}
            fallback={
              <span>
                Illustrative airport rendering. Use the Flight resource list for
                keyboard selection.
              </span>
            }
            onCreated={({ gl }) => {
              gl.domElement.addEventListener(
                "webglcontextlost",
                () => setLost(true),
                { once: true },
              );
            }}
            onPointerMissed={() => view.onSelect(null)}
          >
            <Suspense fallback={null}>
              <AirportContents
                view={view}
                layout={layout}
                intent={intent}
                reducedMotion={reducedMotion}
                inspectorWidth={inspectorWidth}
                labels={labels}
                weather={weather}
                running={running}
                budget={budget}
                onSlow={() => setDegraded(true)}
              />
            </Suspense>
          </Canvas>
        )}
      </RendererBoundary>
      <div className={styles.caption}>
        <span className={styles.dot} />
        Illustrative airport layout <span>·</span> Simulation
      </div>
      <details
        className={styles.atmosphere}
        ref={options}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            if (options.current) options.current.open = false;
            optionTrigger.current?.focus();
          }
        }}
      >
        <summary ref={optionTrigger}>
          <CloudRain size={14} />
          Scene ·{" "}
          {weather === "storm"
            ? "Storm"
            : weather === "rain"
              ? "Rain"
              : "Clear"}
          {!running && " · Paused"}
        </summary>
        <div className={styles.sceneOptions}>
          <h3>Airport atmosphere</h3>
          <p>
            Illustrative traffic and weather. The selected flight stays a plan
            preview.
          </p>
          <label>
            Weather
            <select
              aria-label="Scene weather"
              value={weatherChoice}
              onChange={(e) =>
                setWeatherChoice(e.target.value as WeatherChoice)
              }
            >
              <option value="scenario">From scenario</option>
              <option value="clear">Clear</option>
              <option value="rain">Rain</option>
              <option value="storm">Storm</option>
            </select>
          </label>
          <p>
            {weatherChoice === "scenario"
              ? "Visual preset from the disruption description; not measured weather."
              : "Manual weather preview; scenario rules are unchanged."}
          </p>
          <label>
            Quality
            <select
              aria-label="Scene quality"
              value={quality}
              onChange={(e) => {
                setQuality(e.target.value as Quality);
              }}
            >
              <option value="auto">Auto</option>
              <option value="eco">Eco</option>
              <option value="high">High</option>
            </select>
          </label>
          <p>
            {budget.eco
              ? "Eco · lighter rain and resolution"
              : "High · detailed rain and shadows"}
            {quality === "auto" && degraded
              ? " · adjusted for this device"
              : ""}
          </p>
          <button
            className={styles.motionButton}
            disabled={reducedMotion || lost}
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? <Play size={14} /> : <Pause size={14} />}
            {paused ? "Resume scene motion" : "Pause scene motion"}
          </button>
          {reducedMotion && (
            <p>Motion is off to respect your reduced-motion preference.</p>
          )}
          <p>Background motion pauses when this tab is hidden.</p>
        </div>
      </details>
      {missing.length > 0 && (
        <div className={styles.mapping} role="status">
          Not mapped in this layout: {missing.join(", ")}. Available in Flight
          details.
        </div>
      )}
      <div className={styles.dock} role="toolbar" aria-label="Camera controls">
        <IconButton
          icon={RotateCcw}
          label="Reset airport view"
          onClick={() => command("home")}
        />
        <span className={styles.separator} />
        <IconButton
          icon={Focus}
          label="Focus selection"
          onClick={() => command("focus")}
          disabled={
            !view.selection ||
            (view.selection.kind !== "flight" &&
              !resolveScene(view, layout).selectedAnchor)
          }
        />
        <IconButton
          icon={Minus}
          label="Zoom out"
          onClick={() => command("out")}
        />
        <IconButton icon={Plus} label="Zoom in" onClick={() => command("in")} />
        <span className={styles.separator} />
        <IconButton
          icon={Map}
          label="Top-down view"
          aria-pressed={intent.action === "top"}
          onClick={() => command("top")}
        />
        <IconButton
          icon={BoxIcon}
          label="3D airport view"
          aria-pressed={intent.action !== "top"}
          onClick={() => command("home")}
        />
      </div>
      <div className={styles.hint}>
        <MousePointer2 size={12} /> Drag to orbit · Right-drag to pan · Scroll
        to zoom
      </div>
    </section>
  );
}
