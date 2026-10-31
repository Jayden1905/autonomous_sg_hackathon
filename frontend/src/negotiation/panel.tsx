import { Check, AlertTriangle } from "lucide-react";
import { contextLabel } from "@/workspace";
import {
  CitedText,
  Guardrail,
  PlanDetails,
  Rules,
  ToolActivity,
} from "./details";
import { responseLabel, selectedPlan } from "./state";
import type { Attempt, RunState } from "./state";

export function NegotiationPanel({
  state,
  selected,
  onLatest,
}: {
  state: RunState;
  selected: Attempt | null;
  onLatest: () => void;
}) {
  const plan = selectedPlan(state, selected);
  const turn = plan.turn;
  const responses = turn
    ? Object.entries(turn.responses).map(([agent, response]) => ({
        agent,
        response,
        vetoed: turn.vetoed_accepts?.includes(agent) ?? false,
        blocked: turn.guardrail_blocked?.includes(agent) ?? false,
        counter_evaluation: turn.counter_evaluations[agent],
      }))
    : Object.values(state.responses).map((r) => ({ ...r, blocked: false }));
  const proposer = turn?.proposer ?? state.proposer;
  const proposal = turn?.proposal ?? state.proposal;
  const turnNumber = turn?.turn ?? state.turn;
  const tools =
    turn?.tool_calls ??
    state.tools.filter((t) => t.turn === turnNumber || !turnNumber);
  return (
    <>
      {selected && (
        <div className="history-notice">
          <span>
            Viewing turn {selected.turn}
            {selected.agent ? ` · ${selected.agent.toUpperCase()} counter` : ""}
          </span>
          <button className="text-button" onClick={onLatest}>
            Back to latest
          </button>
        </div>
      )}
      {!selected && state.trace && (
        <div
          className={`outcome ${state.trace.outcome === "consensus" ? "success" : state.trace.outcome === "fallback" ? "caution" : "failure"}`}
        >
          {state.trace.outcome === "consensus" ? (
            <Check size={16} />
          ) : (
            <AlertTriangle size={16} />
          )}
          <strong>{contextLabel(state.trace.outcome)}</strong>
        </div>
      )}
      {!selected && state.status === "error" && (
        <div className="run-error" role="alert">
          <strong>Run incomplete</strong>
          <p>{state.error}</p>
          <p>The last attempt is not a recommendation. You can retry below.</p>
        </div>
      )}
      {state.status === "idle" && (
        <div className="empty">
          <h3>Ready to negotiate</h3>
          <p>
            ATC, Pilot and Ground will propose an arrival plan and check it
            against the same operational rules.
          </p>
          <p>Choose an agent mode below, then run the negotiation.</p>
        </div>
      )}
      {state.status === "running" && !selected && (
        <p className="progress-text">
          {state.thinking
            ? `${state.thinking.agent.toUpperCase()} is ${state.thinking.action === "propose" ? "proposing a plan" : "evaluating the proposal"}…`
            : "Negotiation running…"}
        </p>
      )}
      {plan.proposal && (
        <PlanDetails
          proposal={plan.proposal}
          title={
            selected
              ? "Historical proposal"
              : state.status === "error" ||
                  state.trace?.outcome === "no_legal_option"
                ? "Last attempt · not a recommendation"
                : state.trace
                  ? state.trace.outcome === "fallback"
                    ? "Solver recommendation"
                    : "Agreed recommendation"
                  : "Proposal preview"
          }
        />
      )}
      {!selected && state.trace?.fallback_reason && (
        <p className="muted">{state.trace.fallback_reason}</p>
      )}
      {(turnNumber > 0 || state.thinking) && (
        <section className="detail-section">
          <h3>
            Agent activity <span className="muted">Turn {turnNumber || 1}</span>
          </h3>
          {(["atc", "pilot", "ground"] as const).map((agent) => {
            const result = responses.find((r) => r.agent === agent);
            const isProposer = agent === proposer;
            const blocked =
              isProposer &&
              (proposal?.guardrail?.passed === false ||
                turn?.guardrail_blocked?.includes(agent));
            const thinking =
              !selected &&
              state.status === "running" &&
              state.thinking?.agent === agent;
            const label = thinking
              ? "Thinking…"
              : isProposer
                ? blocked
                  ? "Reply blocked"
                  : "Proposed"
                : result
                  ? responseLabel(
                      result.response,
                      result.vetoed,
                      result.blocked,
                    )
                  : "Waiting";
            return (
              <details className="agent-row" key={`${turnNumber}-${agent}`}>
                <summary>
                  <strong>
                    {agent === "atc"
                      ? "ATC"
                      : agent === "pilot"
                        ? "Pilot"
                        : "Ground"}
                  </strong>
                  <span
                    className={
                      /blocked|vetoed/.test(label)
                        ? "failure"
                        : label === "Accepted"
                          ? "success"
                          : "muted"
                    }
                  >
                    {label}
                  </span>
                </summary>
                {isProposer && proposal && (
                  <>
                    <CitedText
                      text={proposal.rationale}
                      evidence={proposal.evidence}
                    />
                    <Guardrail report={proposal.guardrail} />
                  </>
                )}
                {result && (
                  <>
                    <CitedText
                      text={[
                        result.response.summary,
                        ...(result.response.objections ?? []),
                      ]
                        .filter(Boolean)
                        .join("\n\n")}
                      evidence={result.response.evidence}
                    />
                    <Guardrail report={result.response.guardrail} />
                    {result.vetoed && (
                      <p className="failure">
                        The rule engine vetoed this acceptance.
                      </p>
                    )}
                    {result.response.counter && (
                      <>
                        <PlanDetails
                          proposal={result.response.counter}
                          title="Counterproposal"
                        />
                        <Rules evaluation={result.counter_evaluation ?? null} />
                      </>
                    )}
                    {result.response.verdict === "counter" &&
                      !result.response.counter && (
                        <p>No alternative supplied.</p>
                      )}
                  </>
                )}
                {!result && !isProposer && (
                  <p className="muted">
                    {thinking
                      ? "Reviewing the plan and its evidence."
                      : "No response for this turn yet."}
                  </p>
                )}
              </details>
            );
          })}
        </section>
      )}
      <ToolActivity calls={tools} />
      {!selected && state.guards.length > 0 && (
        <details className="disclosure">
          <summary>Citation check history · {state.guards.length}</summary>
          {state.guards.map((g, i) => (
            <p key={i}>
              {g.agent.toUpperCase()} · Turn {g.turn} ·{" "}
              {g.report.passed
                ? "Passed"
                : "Check failed; repair requested or reply blocked"}{" "}
              · attempt {g.report.attempts}
            </p>
          ))}
        </details>
      )}
      {plan.proposal && <Rules evaluation={plan.evaluation} />}
      {!selected && state.trace && (
        <p className="muted run-metadata">
          {state.trace.model} · {state.trace.duration_s.toFixed(1)} s ·{" "}
          {state.trace.stats?.tool_calls ?? 0} tool calls
        </p>
      )}
    </>
  );
}
