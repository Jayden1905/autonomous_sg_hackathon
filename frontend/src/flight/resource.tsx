import { ArrowLeft, ArrowUpRight } from "lucide-react";
import {
  Select,
  DataRow,
  DataSection,
  displayPlan,
  relativeMinutes,
} from "@/workspace";
import type { FlightView } from "@/workspace";
import styles from "./flight.module.css";

export function ResourceDetails(view: FlightView) {
  const { selection, scenario, proposal, comparison, onSelect } = view;
  if (!selection || selection.kind === "flight") return null;
  const kind = selection.kind;
  const gate =
    selection.kind === "gate"
      ? scenario.gates.find((g) => g.name === selection.id)
      : undefined;
  const runway =
    selection.kind === "runway"
      ? scenario.runways.find((r) => r.name === selection.id)
      : undefined;
  const plan = displayPlan(view);
  const inPlan = proposal?.[selection.kind] === selection.id;
  const wasInPlan = comparison?.proposal[kind] === selection.id;
  return (
    <div className={styles.flight}>
      <button
        className={styles.back}
        onClick={() => onSelect({ kind: "flight", id: scenario.flight })}
      >
        <ArrowLeft size={14} /> Back to flight
      </button>
      <section
        className={styles.resourceHeading}
        aria-label="Selected resource"
      >
        <h2>
          {selection.kind === "gate" ? "Gate" : "Runway"} {selection.id}
        </h2>
        <p>{scenario.destination} · Scenario resource</p>
        <p className={styles.resourceState}>
          {gate
            ? "Availability window"
            : runway
              ? !runway.open
                ? "× Closed"
                : runway.taxiway_blocked
                  ? "Taxiway blocked"
                  : "Open"
              : "Resource unavailable in this scenario"}
        </p>
      </section>
      {gate && (
        <DataSection title="Gate window" note="Relative to scheduled arrival">
          <DataRow label="Free from">
            {relativeMinutes(gate.free_from_min)}
          </DataRow>
          <DataRow label="Free until">
            {relativeMinutes(gate.free_until_min)}
          </DataRow>
          <p className={styles.resourceNote}>
            A time window, not live occupancy. The rule engine checks the
            complete arrival plan.
          </p>
        </DataSection>
      )}
      {runway && (
        <>
          <DataSection title="Runway conditions">
            <DataRow label="Runway" tone={!runway.open ? "danger" : undefined}>
              {runway.open ? "Open" : "Closed"}
            </DataRow>
            <DataRow
              label="Taxiway"
              tone={runway.taxiway_blocked ? "danger" : undefined}
            >
              {runway.taxiway_blocked ? "Blocked" : "Not blocked"}
            </DataRow>
          </DataSection>
          <DataSection
            title="Scheduled arrivals"
            note="Scenario slots · relative to scheduled arrival"
          >
            {runway.arrivals?.length ? (
              [...runway.arrivals]
                .sort((a, b) => a.time_min - b.time_min)
                .map((arrival, i) => (
                  <DataRow key={i} label={relativeMinutes(arrival.time_min)}>
                    Category {arrival.category}
                  </DataRow>
                ))
            ) : (
              <p className={styles.resourceNote}>No arrival slots supplied.</p>
            )}
          </DataSection>
        </>
      )}
      <DataSection title="In the displayed plan">
        {proposal ? (
          <>
            <p className={styles.resourceNote}>{plan.label}</p>
            <p>
              {inPlan
                ? `This ${selection.kind} is in the displayed ${plan.recommended ? "recommendation" : "attempt"}.`
                : wasInPlan
                  ? `Replaced by ${proposal[kind]} in the displayed attempt.`
                  : `The displayed attempt uses ${proposal[kind]}.`}
            </p>
            <DataRow label="Proposed arrival">
              {relativeMinutes(proposal.arrival_min)}
            </DataRow>
            {!inPlan && (
              <button
                className={styles.back}
                onClick={() => onSelect({ kind, id: proposal[kind] })}
              >
                Inspect {selection.kind} {proposal[kind]}{" "}
                <ArrowUpRight size={14} />
              </button>
            )}
          </>
        ) : (
          <p className={styles.resourceNote}>
            No proposal yet. Inspecting a resource does not assign it to this
            flight.
          </p>
        )}
      </DataSection>
      <label className={styles.resourceSwitch}>
        Inspect another resource
        <Select
          label="Inspect another resource"
          value={`${selection.kind}:${selection.id}`}
          onChange={(value) => {
            const [kind, ...id] = value.split(":");
            onSelect({ kind: kind as "gate" | "runway", id: id.join(":") });
          }}
          options={[
            ...scenario.runways.map((r) => ({
              value: `runway:${r.name}`,
              label: `Runway ${r.name}`,
              group: "Runways",
              meta: !r.open
                ? "Closed"
                : r.taxiway_blocked
                  ? "Taxiway blocked"
                  : "Open",
            })),
            ...scenario.gates.map((g) => ({
              value: `gate:${g.name}`,
              label: `Gate ${g.name}`,
              group: "Gates",
            })),
          ]}
        />
      </label>
      <p className={styles.resourceNote}>
        Illustrative layout. Resource states and windows come from this
        scenario, not a live airport feed.
      </p>
    </div>
  );
}
