import { describe, expect, it } from "vitest";
import type { Evaluation, Proposal, Trace } from "@/workspace";
import { emptyRun, runReducer, selectedPlan, responseLabel } from "./state";

const proposal: Proposal = {
  arrival_min: 28,
  runway: "27R",
  gate: "B14",
  rationale: "Proposed plan",
};
const evaluation: Evaluation = {
  proposal,
  feasible: true,
  cost: 4,
  results: [],
};
const turn: Trace["turns"][number] = {
  turn: 1,
  proposer: "atc",
  proposal,
  evaluation,
  responses: { pilot: { verdict: "accept", summary: "Accepted" } },
  counter_evaluations: {},
};
const trace: Trace = {
  scenario_id: "test",
  model: "mock",
  started_at: "2026-10-31T00:00:00Z",
  duration_s: 1,
  outcome: "consensus",
  turns: [turn],
  final: proposal,
  final_evaluation: evaluation,
};

describe("run state isolation and display", () => {
  it("clears the previous turn while the next proposer is still thinking", () => {
    const state = {
      ...emptyRun(1),
      status: "running" as const,
      turn: 1,
      proposal,
      evaluation,
    };
    const next = runReducer(state, {
      type: "event",
      id: 1,
      event: {
        type: "thinking",
        data: { turn: 2, agent: "atc", action: "propose" },
      },
    });
    expect(next.turn).toBe(2);
    expect(next.proposal).toBeNull();
    expect(next.evaluation).toBeNull();
  });
  it("ignores late events after scenario switch and terminal completion", () => {
    const running = runReducer(emptyRun(), { type: "start", id: 1 });
    const reset = runReducer(running, { type: "reset", id: 2 });
    expect(
      runReducer(reset, {
        type: "event",
        id: 1,
        event: { type: "done", data: trace },
      }),
    ).toBe(reset);
    const done = runReducer(running, {
      type: "event",
      id: 1,
      event: { type: "done", data: trace },
    });
    expect(
      runReducer(done, { type: "failure", id: 1, message: "late error" }),
    ).toBe(done);
  });
  it("clears acceptances and matching evaluation when a new proposal arrives", () => {
    let state = runReducer(emptyRun(), { type: "start", id: 1 });
    state = runReducer(state, {
      type: "event",
      id: 1,
      event: { type: "proposal", data: { turn: 1, proposer: "atc", proposal } },
    });
    state = runReducer(state, {
      type: "event",
      id: 1,
      event: {
        type: "response",
        data: {
          turn: 1,
          agent: "pilot",
          response: { verdict: "accept", summary: "Accepted" },
          counter_evaluation: null,
          vetoed: false,
        },
      },
    });
    state = runReducer(state, {
      type: "event",
      id: 1,
      event: { type: "evaluation", data: { turn: 1, evaluation } },
    });
    state = runReducer(state, {
      type: "event",
      id: 1,
      event: {
        type: "proposal",
        data: { turn: 2, proposer: "ground", proposal },
      },
    });
    expect(state.responses).toEqual({});
    expect(state.evaluation).toBeNull();
  });
  it("preserves no-legal-option context even when a last attempt is present", () => {
    const state = runReducer(emptyRun(), {
      type: "restore",
      id: 1,
      trace: { ...trace, outcome: "no_legal_option" },
    });
    expect(selectedPlan(state, null).context).toBe("no_legal_option");
    expect(selectedPlan(state, { turn: 1 }).context).toBe("history");
    expect(selectedPlan(state, null).context).toBe("no_legal_option");
  });
  it("gives blocked or vetoed accepts priority over Accepted", () => {
    expect(
      responseLabel(
        {
          verdict: "accept",
          summary: "Accepted",
          guardrail: { passed: false, checked_claims: 1, attempts: 1 },
        },
        false,
        false,
      ),
    ).toBe("Reply blocked");
    expect(
      responseLabel({ verdict: "accept", summary: "Accepted" }, true, false),
    ).toBe("Acceptance vetoed");
    expect(
      responseLabel({ verdict: "accept", summary: "Accepted" }, false, true),
    ).toBe("Reply blocked");
  });
  it("leaves a failed partial run as a proposal, not a final recommendation", () => {
    let state = runReducer(emptyRun(), { type: "start", id: 1 });
    state = runReducer(state, {
      type: "event",
      id: 1,
      event: { type: "proposal", data: { turn: 1, proposer: "atc", proposal } },
    });
    state = runReducer(state, {
      type: "failure",
      id: 1,
      message: "Disconnected",
    });
    expect(selectedPlan(state, null).context).toBe("proposal");
    expect(state.trace).toBeNull();
  });
});
