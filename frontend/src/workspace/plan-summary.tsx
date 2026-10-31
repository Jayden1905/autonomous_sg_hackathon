import { ArrowRight } from "lucide-react";
import type { FlightView, Proposal } from "./types";
import { relativeMinutes } from "./presentation";
import { DataRow, DataSection } from "./controls";
import styles from "./workspace.module.css";

/** Comparison values come only from another recorded proposal, never scenery. */
export function PlanSummary({
  proposal,
  title,
  comparison,
  onSelect,
  moves,
}: {
  proposal: Proposal;
  title: string;
  comparison?: FlightView["comparison"];
  onSelect?: FlightView["onSelect"];
  moves?: FlightView["scenario"]["moves"];
}) {
  const previous = comparison?.proposal;
  const fields = ["arrival_min", "runway", "gate"] as const;
  const actionsChanged =
    previous &&
    JSON.stringify([...(previous.moves ?? [])].sort()) !==
      JSON.stringify([...(proposal.moves ?? [])].sort());
  const actionNames = (ids: string[] = []) =>
    ids.length
      ? ids
          .map(
            (id) =>
              moves?.find((move) => move.id === id)?.label ??
              `Unknown action: ${id}`,
          )
          .join("; ")
      : "None";
  const count = previous
    ? fields.filter((key) => previous[key] !== proposal[key]).length +
      Number(actionsChanged)
    : 0;
  return (
    <DataSection title={title} note="Relative to scheduled arrival">
      {comparison && (
        <p className={styles.comparisonNote}>
          {comparison.label} ·{" "}
          {count
            ? `${count} ${count === 1 ? "change" : "changes"}`
            : "Plan unchanged"}
        </p>
      )}
      {fields.map((key) => {
        const changed = previous && previous[key] !== proposal[key];
        const format = (plan: Proposal) =>
          key === "arrival_min" ? relativeMinutes(plan[key]) : plan[key];
        const value = (plan: Proposal, old = false) =>
          key !== "arrival_min" && onSelect ? (
            <button
              className={styles.planLink}
              onClick={() => onSelect({ kind: key, id: plan[key] })}
              aria-label={`Inspect ${old ? "previous " : ""}${key} ${plan[key]}`}
            >
              {format(plan)}
            </button>
          ) : (
            format(plan)
          );
        return (
          <DataRow
            key={key}
            label={
              key === "arrival_min"
                ? "Arrival"
                : key === "runway"
                  ? "Runway"
                  : "Gate"
            }
          >
            <span className={styles.planValue} data-changed={Boolean(changed)}>
              {changed && (
                <>
                  <span className={styles.previousValue}>
                    {value(previous, true)}
                  </span>
                  <ArrowRight size={13} aria-label="changes to" />
                </>
              )}
              <span>{value(proposal)}</span>
            </span>
            {changed && key === "arrival_min" && (
              <small className={styles.delta}>
                {Math.abs(proposal.arrival_min - previous.arrival_min)} min{" "}
                {proposal.arrival_min > previous.arrival_min
                  ? "later"
                  : "earlier"}
              </small>
            )}
          </DataRow>
        );
      })}
      {proposal.moves?.length || previous?.moves?.length ? (
        <DataRow label="Agent actions">
          <span
            className={styles.planValue}
            data-changed={Boolean(actionsChanged)}
          >
            {actionsChanged && (
              <>
                <span className={styles.previousValue}>
                  {actionNames(previous.moves)}
                </span>
                <ArrowRight size={13} aria-label="changes to" />
              </>
            )}
            <span>{actionNames(proposal.moves)}</span>
          </span>
        </DataRow>
      ) : null}
      {!comparison && (
        <p className={styles.comparisonNote}>No earlier proposal to compare.</p>
      )}
    </DataSection>
  );
}
