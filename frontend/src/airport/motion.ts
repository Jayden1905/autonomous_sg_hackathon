import { CatmullRomCurve3, Vector3 } from "three";
import type { Scenario } from "@/workspace";
import type { AirportLayout } from "./layout";

export type Weather = "clear" | "rain" | "storm";
export type WeatherChoice = "scenario" | Weather;
export type Quality = "auto" | "eco" | "high";
/** A visual preset inferred from the brief, never a meteorological observation. */
export function scenarioWeather(disruption: string): Weather {
  if (/thunder|storm/i.test(disruption)) return "storm";
  if (/rain|shower|drizzle/i.test(disruption)) return "rain";
  return "clear";
}
export function trafficRunway(scenario: Scenario, layout: AirportLayout) {
  return scenario.runways.find(
    (r) => r.open && !r.taxiway_blocked && layout.runways[r.name],
  );
}
export function sceneBudget(
  quality: Quality,
  compact: boolean,
  degraded: boolean,
) {
  const eco =
    quality === "eco" || (quality === "auto" && (compact || degraded));
  return {
    eco,
    fps: eco ? 24 : 30,
    dpr: eco ? 1 : 1.5,
    rain: eco ? 700 : 2200,
    shadows: eco ? 1024 : 2048,
  };
}
export function makeTrafficRoutes(runwayZ: number) {
  const curve = (points: number[][]) =>
    new CatmullRomCurve3(
      points.map((p) => new Vector3(...(p as [number, number, number]))),
      false,
      "centripetal",
    );
  return {
    departure: curve([
      [-550, 0, 122],
      [-180, 0, 122],
      [140, 0, 122],
      [235, 0, 122],
      [282, 0, 45],
      [282, 0, -110],
      [282, 0, runwayZ],
      [210, 0, runwayZ],
      [20, 0, runwayZ],
      [-120, 0, runwayZ],
      [-230, 18, runwayZ],
      [-450, 100, runwayZ],
      [-950, 260, runwayZ],
    ]),
    arrival: curve([
      [950, 220, runwayZ],
      [480, 90, runwayZ],
      [260, 10, runwayZ],
      [190, 0, runwayZ],
      [-90, 0, runwayZ],
      [-120, 0, runwayZ + 30],
      [-120, 0, -113],
      [-250, 0, -113],
      [-285, 0, -80],
      [-285, 0, 122],
      [-550, 0, 122],
    ]),
  };
}
/** Exclude pauses and clamp resumed frames to prevent aircraft jumping. */
export function advanceSceneTime(
  time: number,
  delta: number,
  running: boolean,
) {
  return running ? time + Math.min(Math.max(delta, 0), 0.1) : time;
}
