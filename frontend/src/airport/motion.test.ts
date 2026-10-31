import { describe, expect, it } from "vitest";
import weather from "../../../scenarios/sample_weather.json";
import type { Scenario } from "@/workspace";
import { demoLayout } from "./layout";
import {
  advanceSceneTime,
  makeTrafficRoutes,
  sceneBudget,
  scenarioWeather,
  trafficRunway,
} from "./motion";
import { aircraftGeometry } from "./aircraft-model";

describe("illustrative motion boundaries", () => {
  it("does not route decorative traffic onto closed, blocked or unmapped runways", () => {
    const scenario = weather as Scenario;
    expect(trafficRunway(scenario, demoLayout)?.name).toBe("27R");
    expect(
      trafficRunway(
        {
          ...scenario,
          runways: scenario.runways.map((r) => ({ ...r, open: false })),
        },
        demoLayout,
      ),
    ).toBeUndefined();
    expect(
      trafficRunway(
        {
          ...scenario,
          runways: scenario.runways.map((r) => ({
            ...r,
            taxiway_blocked: true,
          })),
        },
        demoLayout,
      ),
    ).toBeUndefined();
    expect(trafficRunway(scenario, { gates: {}, runways: {} })).toBeUndefined();
  });
  it("freezes paused time and clamps a resumed frame", () => {
    expect(advanceSceneTime(12, 40, false)).toBe(12);
    expect(advanceSceneTime(12, 40, true)).toBe(12.1);
    expect(advanceSceneTime(12, -1, true)).toBe(12);
  });
  it("reduces the rendering budget on small and struggling devices", () => {
    expect(sceneBudget("auto", true, false).eco).toBe(true);
    expect(sceneBudget("auto", false, true).rain).toBeLessThan(
      sceneBudget("high", false, false).rain,
    );
    expect(sceneBudget("eco", false, false).fps).toBeLessThanOrEqual(30);
  });
  it("distinguishes rain presets from unspecified weather", () => {
    expect(scenarioWeather("Thunderstorm cell")).toBe("storm");
    expect(scenarioWeather("Heavy rain")).toBe("rain");
    expect(scenarioWeather("Gate unavailable")).toBe("clear");
  });
  it("keeps flight route resets outside the terminal and gives aircraft altitude", () => {
    const routes = makeTrafficRoutes(-218);
    expect(routes.departure.getPointAt(0).x).toBeLessThan(-500);
    expect(routes.departure.getPointAt(1).y).toBeGreaterThan(200);
    expect(routes.arrival.getPointAt(0).x).toBeGreaterThan(500);
    expect(routes.arrival.getPointAt(1).x).toBeLessThan(-500);
  });
  it("preserves the aircraft silhouette in shared geometry", () => {
    aircraftGeometry.white.computeBoundingBox();
    const bounds = aircraftGeometry.white.boundingBox!;
    expect(bounds.min.x).toBeLessThanOrEqual(-16);
    expect(bounds.max.x).toBeGreaterThanOrEqual(16);
    expect(bounds.min.z).toBeLessThanOrEqual(-17);
    expect(bounds.max.z).toBeGreaterThanOrEqual(17);
    expect(
      aircraftGeometry.white.getAttribute("position").count,
    ).toBeGreaterThan(100);
  });
});
