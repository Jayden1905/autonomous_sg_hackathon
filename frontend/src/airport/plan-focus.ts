import type { FlightView } from "@/workspace";
import { relativeMinutes } from "@/workspace";
import { resolveScene } from "./layout";
import type { AirportLayout, Point } from "./layout";

export interface PlanFocus {
  key: string;
  target: Point;
  distance: number;
  label: string;
}

/** Camera destinations use mapped resources and recorded proposals, never narrative guesses. */
export function planFocus(
  view: FlightView,
  layout: AirportLayout,
  idle: Point,
): PlanFocus {
  const scene = resolveScene(view, layout, idle);
  const p = view.proposal,
    previous = view.comparison?.proposal;
  const key = JSON.stringify([
    view.scenario.scenario_id,
    view.context,
    p && [p.arrival_min, p.gate, p.runway, [...(p.moves ?? [])].sort()],
    scene.emphasize,
  ]);
  const flight = {
    key,
    target: scene.aircraft,
    distance: 125,
    label: `${view.scenario.flight} · Scenario aircraft`,
  };
  if (view.context === "no_legal_option")
    return { ...flight, label: "No legal option · Human decision required" };
  if (!scene.emphasize || !p) return flight;
  const prefix = scene.label;
  const gateChanged = previous && previous.gate !== p.gate;
  const runwayChanged = previous && previous.runway !== p.runway;
  const final = view.context === "consensus" || view.context === "fallback";
  const addedMove = (p.moves ?? []).find(
    (id) => !previous?.moves?.includes(id),
  );
  const move = view.scenario.moves?.find((option) => option.id === addedMove);
  if (move && !gateChanged && !runwayChanged && !final) {
    const gateName = move.effect.gate_free_from?.gate;
    const runwayName =
      move.effect.runway_opens?.runway ?? move.effect.arrival_moved?.runway;
    const gate =
      typeof gateName === "string" &&
      view.scenario.gates.some((g) => g.name === gateName)
        ? layout.gates[gateName]
        : null;
    const runway =
      typeof runwayName === "string" &&
      view.scenario.runways.some((r) => r.name === runwayName)
        ? layout.runways[runwayName]
        : null;
    return {
      key,
      target: gate ? [gate[0], 0, gate[2] + 16] : (runway ?? scene.aircraft),
      distance: runway ? 230 : 125,
      label: `${prefix} · ${move.label}`,
    };
  }
  if (!final && runwayChanged && !gateChanged && scene.runway) {
    return {
      key,
      target: [scene.runway[0] - 55, 0, scene.runway[2]],
      distance: 230,
      label: `${prefix} · Runway ${previous.runway} → ${p.runway}`,
    };
  }
  if (!final && gateChanged && !runwayChanged && scene.gate) {
    return {
      key,
      target: scene.aircraft,
      distance: 125,
      label: `${prefix} · Gate ${previous.gate} → ${p.gate}`,
    };
  }
  if (
    scene.gate &&
    scene.runway &&
    (final || !previous || (gateChanged && runwayChanged))
  ) {
    const target: Point = [
      (scene.aircraft[0] + scene.runway[0] - 55) / 2,
      0,
      (scene.aircraft[2] + scene.runway[2]) / 2,
    ];
    return {
      key,
      target,
      distance: 420,
      label: `${prefix} · ${p.runway} → ${p.gate} · ${relativeMinutes(p.arrival_min)}`,
    };
  }
  if (!scene.gate || !scene.runway)
    return {
      ...flight,
      label: `${prefix} · Unmapped resources remain in the inspector`,
    };
  return {
    ...flight,
    label: `${prefix} · ${relativeMinutes(p.arrival_min)} · ${p.runway} → ${p.gate}`,
  };
}
