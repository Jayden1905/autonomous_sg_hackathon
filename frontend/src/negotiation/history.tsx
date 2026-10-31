import type { Trace } from "@/workspace";
import { relativeMinutes } from "@/workspace";
import type { Attempt } from "./state";

export function TurnHistory({
  turns,
  selected,
  onSelect,
  onLatest,
}: {
  turns: Trace["turns"];
  selected: Attempt | null;
  onSelect: (attempt: Attempt) => void;
  onLatest: () => void;
}) {
  return (
    <section className="detail-section">
      <h3>Compare recorded proposals</h3>
      <p className="muted">
        Select an attempt to inspect its plan, replies and rule evaluation.
      </p>
      {!turns.length ? (
        <p className="muted">Completed turns will appear here.</p>
      ) : (
        <div className="table-scroll" tabIndex={0}>
          <table className="comparison">
            <caption>
              Actual proposals and counters · relative arrival times
            </caption>
            <thead>
              <tr>
                <th>Attempt</th>
                <th>Arrival</th>
                <th>Runway / gate</th>
                <th>Rules / cost</th>
              </tr>
            </thead>
            <tbody>
              {turns
                .flatMap((turn) => [
                  {
                    key: `${turn.turn}`,
                    selection: { turn: turn.turn },
                    label: `T${turn.turn} · ${turn.proposer.toUpperCase()}`,
                    proposal: turn.proposal,
                    evaluation: turn.evaluation,
                    blocked: turn.guardrail_blocked?.includes(turn.proposer),
                  },
                  ...Object.entries(turn.responses)
                    .filter(([, r]) => r.counter)
                    .map(([agent, r]) => ({
                      key: `${turn.turn}-${agent}`,
                      selection: { turn: turn.turn, agent },
                      label: `↳ ${agent.toUpperCase()}`,
                      proposal: r.counter!,
                      evaluation: turn.counter_evaluations[agent],
                      blocked:
                        turn.guardrail_blocked?.includes(agent) ||
                        r.guardrail?.passed === false,
                    })),
                ])
                .map((row) => (
                  <tr
                    key={row.key}
                    data-selected={
                      selected?.turn === row.selection.turn &&
                      selected?.agent ===
                        ("agent" in row.selection
                          ? row.selection.agent
                          : undefined)
                    }
                  >
                    <td>
                      <button
                        onClick={() => onSelect(row.selection)}
                        aria-label={`Inspect ${row.label}`}
                      >
                        {row.label}
                      </button>
                      {row.blocked && (
                        <small className="failure">Reply blocked</small>
                      )}
                    </td>
                    <td>{relativeMinutes(row.proposal.arrival_min)}</td>
                    <td>
                      {row.proposal.runway} / {row.proposal.gate}
                    </td>
                    <td>
                      {row.evaluation ? (
                        <>
                          {row.evaluation.feasible ? "Feasible" : "Infeasible"}
                          <br />
                          <span className="muted">{row.evaluation.cost}</span>
                        </>
                      ) : (
                        "Not evaluated"
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <button className="text-button" onClick={onLatest}>
          Back to latest
        </button>
      )}
    </section>
  );
}
