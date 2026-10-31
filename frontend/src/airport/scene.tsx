import { Component, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { Canvas } from "@react-three/fiber";
import { Environment } from "@react-three/drei";
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
  ChevronDown,
} from "lucide-react";
import type { FlightView } from "@/workspace";
import { IconButton, Select } from "@/workspace";
import { Aircraft } from "./aircraft";
import { AircraftShadows } from "./aircraft-shadows";
import { Footprint, ResourceTarget } from "./resource-target";
import { parkedAircraft } from "./scenery-layout";
import { Terminal } from "./terminal";
import { Ground } from "./ground";
import { SurfaceLibrary } from "./surface-library";
import { AirportCamera } from "./camera";
import type { CameraIntent } from "./camera";
import { AircraftTooltip } from "./tooltip";
import { resolveScene, unmappedResources } from "./layout";
import type { AirportLayout } from "./layout";
import styles from "./airport.module.css";
import { AirportTraffic, SceneClockDriver } from "./life";
import { Rain, weatherLighting } from "./weather";
import { StaticBatch } from "./static-batch";
import { scenarioWeather, sceneBudget, trafficRunway } from "./motion";
import type { Quality, Weather, WeatherChoice } from "./motion";
import { WebGLNodesHandler } from "three/addons/tsl/WebGLNodesHandler.js";

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
      <hemisphereLight args={["#d2dce4", "#464840", light.ambient]} />
      <directionalLight
        position={[-120, 150, 65]}
        intensity={light.sun}
        color="#fff4e4"
        castShadow
        shadow-mapSize={[budget.shadows, budget.shadows]}
        shadow-camera-left={-180}
        shadow-camera-right={180}
        shadow-camera-top={180}
        shadow-camera-bottom={-180}
        shadow-camera-far={550}
        shadow-normalBias={0.1}
        shadow-bias={-0.0001}
      />
      <Environment
        files="/materials/daylight.hdr"
        environmentIntensity={weather === "clear" ? 0.6 : 0.4}
        environmentRotation={[0, 1.5, 0]}
      />
      <SurfaceLibrary />
      <Ground wet={weather !== "clear"} />
      <AircraftShadows revision={shadowKey} eco={budget.eco} />
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
      {parkedAircraft
        .filter(
          ({ position: [x, , z] }) =>
            z < 0 || Math.abs(x - scene.aircraft[0]) > 1,
        )
        .map((aircraft) => (
          <Aircraft key={aircraft.position.join(",")} {...aircraft} />
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
      {scene.emphasize &&
        view.comparison &&
        (() => {
          const before = view.comparison.proposal;
          const gate =
            before.gate !== view.proposal?.gate &&
            scenario.gates.some((g) => g.name === before.gate)
              ? layout.gates[before.gate]
              : undefined;
          const runway =
            before.runway !== view.proposal?.runway &&
            scenario.runways.some((r) => r.name === before.runway)
              ? layout.runways[before.runway]
              : undefined;
          return (
            <>
              {gate && (
                <Footprint position={[gate[0], 0, gate[2] + 15]} previous />
              )}
              {runway && (
                <Footprint position={runway} width={490} depth={24} previous />
              )}
            </>
          );
        })()}
      {scenario.gates.map((g) => {
        const anchor = layout.gates[g.name];
        if (!anchor) return null;
        return (
          <ResourceTarget
            key={`gate-${g.name}`}
            kind="gate"
            id={g.name}
            position={[anchor[0], 0, anchor[2] + 15]}
            labelPosition={[anchor[0] + 12, 1, anchor[2] + 30]}
            width={28}
            depth={39}
            portal={labels}
            selected={selection?.kind === "gate" && selection.id === g.name}
            proposed={scene.emphasize && view.proposal?.gate === g.name}
            previous={
              scene.emphasize &&
              view.comparison?.proposal.gate === g.name &&
              view.proposal?.gate !== g.name
            }
            onSelect={onSelect}
          />
        );
      })}
      {scenario.runways.map((r) => {
        const anchor = layout.runways[r.name];
        if (!anchor) return null;
        return (
          <ResourceTarget
            key={`runway-${r.name}`}
            kind="runway"
            id={r.name}
            position={anchor}
            labelPosition={[anchor[0] - 60, 2, anchor[2]]}
            width={490}
            depth={24}
            portal={labels}
            selected={selection?.kind === "runway" && selection.id === r.name}
            proposed={scene.emphasize && view.proposal?.runway === r.name}
            previous={
              scene.emphasize &&
              view.comparison?.proposal.runway === r.name &&
              view.proposal?.runway !== r.name
            }
            status={
              !r.open
                ? "closed"
                : r.taxiway_blocked
                  ? "taxiway blocked"
                  : undefined
            }
            onSelect={onSelect}
          />
        );
      })}
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
              gl.setNodesHandler(new WebGLNodesHandler());
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
          <ChevronDown size={14} className={styles.disclosureArrow} />
        </summary>
        <div className={styles.sceneOptions}>
          <h3>Airport atmosphere</h3>
          <p>
            Preview weather and motion. The selected flight stays a plan
            preview.
          </p>
          <label>
            Weather
            <Select
              label="Scene weather"
              value={weatherChoice}
              onChange={(value) => setWeatherChoice(value as WeatherChoice)}
              options={[
                {
                  value: "scenario",
                  label: "From scenario",
                  description: "Use the disruption's weather preset",
                },
                {
                  value: "clear",
                  label: "Clear",
                  description: "Dry apron and clear visibility",
                },
                {
                  value: "rain",
                  label: "Rain",
                  description: "Rainfall and damp surfaces",
                },
                {
                  value: "storm",
                  label: "Storm",
                  description: "Heavier rain and reduced visibility",
                },
              ]}
            />
          </label>
          <p>
            {weatherChoice === "scenario"
              ? "Visual preset from the disruption description; not measured weather."
              : "Manual weather preview; scenario rules are unchanged."}
          </p>
          <label>
            Quality
            <Select
              label="Scene quality"
              value={quality}
              onChange={(value) => setQuality(value as Quality)}
              options={[
                {
                  value: "auto",
                  label: "Auto",
                  description: "Adjust to this device",
                },
                {
                  value: "eco",
                  label: "Eco",
                  description: "Lighter rain and resolution",
                },
                {
                  value: "high",
                  label: "High",
                  description: "Detailed rain and shadows",
                },
              ]}
            />
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
