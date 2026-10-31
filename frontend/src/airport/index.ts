import { lazy } from "react";

export const AirportScene = lazy(() =>
  import("./scene").then((module) => ({ default: module.AirportScene })),
);
export { demoLayout, stormLayout, datasetLayout } from "./layout";
export type { AirportLayout } from "./layout";
