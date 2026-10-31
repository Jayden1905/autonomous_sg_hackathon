import { Check, AlertTriangle, Plane, ArrowRight } from "lucide-react";
import {
  DataRow,
  DataSection,
  displayPlan,
  provenanceLabel,
  recordedFlight,
  relativeMinutes,
  PlanSummary,
} from "@/workspace";
import type { FlightView, Scenario } from "@/workspace";
import styles from "./flight.module.css";
import { ResourceDetails } from "./resource";

function Airport({
  code,
  info,
}: {
  code: string;
  info: Scenario["origin_info"];
}) {
  return (
    <div>
      <strong>{info ? <abbr title={info.name}>{code}</abbr> : code}</strong>
      <span>
        {info ? `${info.city}, ${info.state}` : "Airport metadata unavailable"}
      </span>
    </div>
  );
}

export function FlightTab(view: FlightView) {
  const { scenario: s, proposal, context, selection, onSelect } = view;
  const plan = displayPlan(view);
  const margin = s.fuel_endurance_min - s.final_reserve_min;
  const record = recordedFlight(s);
  // A hand-written sample is labelled once above; marking rows would tag every value.
  const synthetic = (field: keyof Scenario) =>
    record && s.synthetic_fields?.includes(field) ? "Synthetic" : undefined;
  if (selection && selection.kind !== "flight")
    return <ResourceDetails {...view} />;
  return (
    <div className={styles.flight}>
      <div className={styles.route}>
        <Airport code={s.origin} info={s.origin_info} />
        <ArrowRight size={18} />
        <Airport code={s.destination} info={s.destination_info} />
      </div>
      <p className={styles.airline}>{s.airline_name ?? s.airline}</p>
      <p className={styles.source}>{provenanceLabel(s)}</p>
      <section className={styles.disruption}>
        <h3>Disruption</h3>
        <p>{s.disruption}</p>
        {synthetic("disruption") && (
          <small>
            Synthetic description. Delay minutes come from the DOT record.
          </small>
        )}
      </section>
      {proposal && (
        <PlanSummary
          proposal={proposal}
          title={
            context === "no_legal_option"
              ? "Last attempt"
              : plan.recommended
                ? "Recommended arrival"
                : "Displayed proposal"
          }
          comparison={view.comparison}
          onSelect={onSelect}
        />
      )}
      {record && (
        <DataSection
          title="DOT flight record"
          note="US DOT 2015 data · arrival relative to schedule"
        >
          <DataRow label="Date">{record.date}</DataRow>
          <DataRow label="Scheduled arrival">
            {s.scheduled_arrival_hhmm} local
          </DataRow>
          <DataRow label="Actual arrival">
            {record.arrivalDelayMin === null
              ? "Unavailable"
              : relativeMinutes(record.arrivalDelayMin)}
          </DataRow>
          <DataRow label="Weather delay">{s.weather_delay_min} min</DataRow>
          <DataRow label="Late-aircraft delay">
            {s.late_aircraft_delay_min} min
          </DataRow>
        </DataSection>
      )}
      <p
        className={`${styles.status} ${context === "no_legal_option" ? styles.failure : context === "fallback" ? styles.caution : plan.recommended ? styles.success : ""}`}
        role="status"
      >
        {plan.recommended && context !== "fallback" ? (
          <Check size={14} />
        ) : context === "no_legal_option" || context === "fallback" ? (
          <AlertTriangle size={14} />
        ) : (
          <Plane size={14} />
        )}{" "}
        {plan.label}
      </p>
      {context === "no_legal_option" && (
        <p className={styles.failure}>
          No legal option — human decision required.
        </p>
      )}
      {context === "no_legal_option" && plan.assessment && (
        <ul className={styles.failures}>
          {plan.assessment.results
            .filter((r) => r.hard && !r.passed)
            .map((r) => (
              <li key={r.rule}>{r.detail}</li>
            ))}
        </ul>
      )}
      <DataSection
        title="Flight constraints"
        note="Times relative to scheduled arrival"
      >
        <DataRow
          label="Earliest arrival"
          note={synthetic("earliest_arrival_min")}
        >
          {relativeMinutes(s.earliest_arrival_min)}
        </DataRow>
        <DataRow
          label={margin < 0 ? "Fuel reserve deficit" : "Holding budget"}
          tone={margin < 0 ? "danger" : undefined}
          note={synthetic("fuel_endurance_min")}
        >
          {Math.abs(margin)} min
        </DataRow>
        <DataRow label="Connecting passengers" note={synthetic("connections")}>
          {(s.connections ?? []).reduce((n, c) => n + c.passengers, 0)}
        </DataRow>
        <DataRow
          label="Crew shift ends"
          note={synthetic("crew_shift_ends_min")}
        >
          {relativeMinutes(s.crew_shift_ends_min)}
        </DataRow>
        <DataRow label="Turnaround" note={synthetic("turnaround_min")}>
          {s.turnaround_min} min
        </DataRow>
      </DataSection>
      <section className={styles.entities}>
        <h3>Airport resources</h3>
        <p>
          Choose a resource to inspect it in the scene.
          {(synthetic("runways") || synthetic("gates")) &&
            " Runways and gates are synthetic, not this airport's real layout."}
        </p>
        <button
          className={styles.entity}
          onClick={() => onSelect({ kind: "flight", id: s.flight })}
          aria-pressed={
            selection?.kind === "flight" && selection.id === s.flight
          }
        >
          <span>
            <Plane size={14} /> {s.flight}
          </span>
          <span>Flight</span>
        </button>
        {s.runways.map((r) => (
          <button
            key={r.name}
            className={styles.entity}
            onClick={() => onSelect({ kind: "runway", id: r.name })}
            aria-pressed={
              selection?.kind === "runway" && selection.id === r.name
            }
          >
            <span>Runway {r.name}</span>
            <span className={!r.open ? styles.failure : undefined}>
              {!r.open
                ? "× Closed"
                : r.taxiway_blocked
                  ? "Taxiway blocked"
                  : "Open"}
            </span>
          </button>
        ))}
        {s.gates.map((g) => (
          <button
            key={g.name}
            className={styles.entity}
            onClick={() => onSelect({ kind: "gate", id: g.name })}
            aria-pressed={selection?.kind === "gate" && selection.id === g.name}
          >
            <span>Gate {g.name}</span>
            <span>
              {relativeMinutes(g.free_from_min)} →{" "}
              {relativeMinutes(g.free_until_min)}
            </span>
          </button>
        ))}
        <p>Gate windows are relative to scheduled arrival.</p>
      </section>
      <details className={styles.provenance}>
        <summary>Data & provenance</summary>
        <p>
          Illustrative airport layout. Geometry, aircraft placement and scenery
          are presentation data, not airport telemetry.
        </p>
        <h4>Scenario source</h4>
        {Object.keys(s.source ?? {}).length ? (
          <dl>
            {Object.entries(s.source ?? {}).map(([key, value]) => (
              <DataRow key={key} label={key}>
                {typeof value === "string" ? value : JSON.stringify(value)}
              </DataRow>
            ))}
          </dl>
        ) : (
          <p>No external source supplied.</p>
        )}
        <h4>Synthetic fields</h4>
        {s.synthetic_fields?.length ? (
          <ul>
            {s.synthetic_fields.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        ) : (
          <p>No synthetic field information supplied.</p>
        )}
      </details>
    </div>
  );
}
