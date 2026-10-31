import type { Events, StreamEvent } from "@/api";
import type { Evaluation, Proposal, Trace } from "@/workspace";
import { sameProposal } from "@/workspace";

export interface RunState {
  id: number;
  status: "idle" | "running" | "done" | "error";
  turn: number;
  proposer: string;
  proposal: Proposal | null;
  evaluation: Evaluation | null;
  responses: Record<string, Events["response"]>;
  thinking: Events["thinking"] | null;
  tools: Events["tool_call"][];
  guards: Events["guardrail"][];
  turns: Trace["turns"];
  trace: Trace | null;
  error: string | null;
  model: string | null;
}

export const emptyRun = (id = 0): RunState => ({
  id,
  status: "idle",
  turn: 0,
  proposer: "",
  proposal: null,
  evaluation: null,
  responses: {},
  thinking: null,
  tools: [],
  guards: [],
  turns: [],
  trace: null,
  error: null,
  model: null,
});
type Action =
  | { type: "reset"; id: number }
  | { type: "start"; id: number }
  | { type: "event"; id: number; event: StreamEvent }
  | { type: "failure"; id: number; message: string }
  | { type: "restore"; id: number; trace: Trace };

export function runReducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return emptyRun(action.id);
  if (action.type === "start")
    return { ...emptyRun(action.id), status: "running" };
  if (action.type === "restore")
    return {
      ...emptyRun(action.id),
      status: "done",
      trace: action.trace,
      turns: action.trace.turns,
      model: action.trace.model,
    };
  if (state.id !== action.id || state.status !== "running") return state;
  if (action.type === "failure")
    return { ...state, status: "error", error: action.message, thinking: null };
  const event = action.event;
  switch (event.type) {
    case "started":
      return { ...state, model: event.data.model };
    case "thinking":
      return event.data.turn > state.turn
        ? {
            ...state,
            turn: event.data.turn,
            proposer: event.data.action === "propose" ? event.data.agent : "",
            proposal: null,
            evaluation: null,
            responses: {},
            thinking: event.data,
          }
        : { ...state, thinking: event.data };
    case "tool_call":
      return { ...state, tools: [...state.tools, event.data] };
    case "guardrail":
      return { ...state, guards: [...state.guards, event.data] };
    case "proposal":
      return {
        ...state,
        turn: event.data.turn,
        proposer: event.data.proposer,
        proposal: event.data.proposal,
        evaluation: null,
        responses: {},
        thinking: null,
      };
    case "evaluation":
      return event.data.turn === state.turn
        ? { ...state, evaluation: event.data.evaluation }
        : state;
    case "response":
      return event.data.turn === state.turn
        ? {
            ...state,
            responses: { ...state.responses, [event.data.agent]: event.data },
            thinking: null,
          }
        : state;
    case "turn_complete":
      return {
        ...state,
        turns: [
          ...state.turns.filter((t) => t.turn !== event.data.turn),
          event.data,
        ],
        thinking: null,
      };
    case "done":
      return {
        ...state,
        status: "done",
        trace: event.data,
        turns: event.data.turns,
        thinking: null,
      };
    case "error":
      return {
        ...state,
        status: "error",
        error: event.data.message,
        thinking: null,
      };
  }
}

export interface Attempt {
  turn: number;
  agent?: string;
}
export function selectedPlan(state: RunState, selected: Attempt | null) {
  const turn = selected
    ? state.turns.find((t) => t.turn === selected.turn)
    : undefined;
  if (turn) {
    const counter = selected?.agent
      ? turn.responses[selected.agent]?.counter
      : null;
    return {
      proposal: counter ?? turn.proposal,
      evaluation: selected?.agent
        ? (turn.counter_evaluations[selected.agent] ?? null)
        : turn.evaluation,
      context: "history" as const,
      awaitingProposal: false,
      turn,
    };
  }
  if (state.trace)
    return {
      proposal: state.trace.final,
      evaluation: state.trace.final_evaluation,
      context: state.trace.outcome,
      awaitingProposal: false,
      turn: state.trace.turns.at(-1),
    };
  const previous =
    state.status === "running" && !state.proposal
      ? state.turns.at(-1)?.proposal
      : null;
  return {
    proposal: state.proposal ?? previous ?? null,
    evaluation: state.proposal ? state.evaluation : null,
    context:
      state.proposal || previous
        ? ("proposal" as const)
        : ("scenario" as const),
    awaitingProposal: Boolean(previous),
    turn: undefined,
  };
}

export function planComparison(state: RunState, selected: Attempt | null) {
  const plan = selectedPlan(state, selected);
  if (!plan.proposal) return null;
  if (selected?.agent && plan.turn?.responses[selected.agent]?.counter)
    return {
      proposal: plan.turn.proposal,
      label: `Compared with turn ${plan.turn.turn} proposal`,
    };
  const turns = state.trace?.turns ?? state.turns;
  const last = turns.at(-1);
  // A final result often repeats the last turn. Do not compare it with itself.
  const limit =
    selected?.turn ??
    (state.trace
      ? last && sameProposal(last.proposal, plan.proposal)
        ? last.turn
        : Infinity
      : state.turn);
  const previous = turns.filter((turn) => turn.turn < limit).at(-1);
  return previous
    ? {
        proposal: previous.proposal,
        label: `Compared with turn ${previous.turn}`,
      }
    : null;
}

export function responseLabel(
  response: Events["response"]["response"],
  vetoed: boolean,
  blocked: boolean,
) {
  if (blocked || response.guardrail?.passed === false) return "Reply blocked";
  if (vetoed) return "Acceptance vetoed";
  return response.verdict === "accept" ? "Accepted" : "Countered";
}
