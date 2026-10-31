"""The three negotiating agents. Each has its own prompt, priorities and tool loop.

An action (propose, or respond to a proposal) is a tool-calling loop, the
pattern of ACM's NativeToolLoop copied down to what this needs:

    for step in 1..max_steps:
        call Claude with lookup tools + one submit tool
        submit tool called  -> validate it into Proposal / AgentResponse, done
        lookup tools called -> run them, return results, loop

Everything goes through the semantic model (semantic/model.yaml):
  - data retrieval is `query_metric`: model metrics and dimensions only, SQL
    compiled from the model (metrics.py). There is no free-SQL tool.
  - `check_proposal` reports model rule ids and the passages they cite.
  - `lookup_concept` returns the model's definition of a term.
  - submitted evidence must cite model elements; grounding.py checks each
    citation against the model and against what the agent queried this
    action, and gives the agent one round to repair ungrounded claims.
Every call is recorded as a `ToolCall` (with `model_refs`) and streamed.

`MockAgent` is a scripted stand-in for tests and offline UI work. It makes
real tool calls (rule engine, and SQL when the data is present) so the UI
sees the same event shapes, but no LLM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Protocol

import anthropic

from . import fallback
from .grounding import Grounder, Ledger
from .guardrails import Guardrails, holders_of
from .metrics import MetricCatalog, build_catalog
from .schemas import (AgentResponse, Evaluation, Evidence, GuardrailReport, Proposal, RunStats, Scenario, ToolCall,
                      TurnRecord, Verdict)
from .sqlengine import SqlEngine, dataset_available
from .sqlengine import default_engine as default_sql_engine
from .tools import SUBMIT_PROPOSAL, SUBMIT_RESPONSE, Toolbox, ToolOutcome, evaluation_brief, tool_defs

DEFAULT_MODEL = os.environ.get("ATC_MODEL", "claude-opus-5-5")
# Effort per LLM call. "low" keeps a full 3-turn negotiation to a few minutes; raise for quality runs.
DEFAULT_EFFORT = os.environ.get("ATC_EFFORT", "low")
MAX_STEPS = int(os.environ.get("ATC_MAX_STEPS", "10"))
# Server-side refusal fallback: if a safety classifier declines, the API reruns on a fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SHARED_RULES = """\
You are one of three agents resolving a flight disruption: ATC, the pilot in
command, and ground operations. The others cover the domains you do not.

Protocol:
- Times are minutes relative to the flight's scheduled arrival. Negative is early.
- A separate rule engine, not you, decides whether a plan is legal. Never accept
  a plan it marks infeasible. Use check_proposal to test a plan before you
  submit it as a proposal or counter.
- You may counter with exactly one alternative plan. Make it concrete.
- Prefer accepting a feasible plan that is tolerable for your domain over
  countering for a small gain. The negotiation must finish within 3 turns.
- Read the negotiation so far and answer the other agents' objections, not
  just the plan.
- Finish every action by calling submit_proposal or submit_response exactly once.

Grounding (the semantic model below is the vocabulary of this negotiation):
- Speak in the model's terms: its concepts, metric names and rule ids.
- History comes only from query_metric, which answers in model metrics over
  real 2015 US DOT flights. Fields in the scenario's synthetic_fields (runways,
  gates, fuel, connections, crew) are generated and have no history.

Work before you submit (checked by code; a submit that skips it is sent back):
1. Query at least two different metrics: your role's main metric at this
   destination, and a second one that cuts the question another way (another
   delay cause, group_by arrival_hour, or the route). Say how each bears on
   your plan.
2. lookup_concept at least one rule or concept your decision rests on, so you
   use the model's definition and threshold, not your memory.
3. check_proposal exactly the plan you submit (your proposal, or your counter).
Call independent tools together in one step; they run in parallel.
- Every number you rely on goes in `evidence` as {claim, source}. source is
  metric:<name> (queried this action), rule:<id>, passage:<id>,
  code:<CodeSet>.<value>, scenario:<field>, or check_proposal. Sources are
  checked against the model; a metric you did not query this action is
  rejected. Never invent a statistic, rule or regulation.
- Cite like a paper: evidence items are numbered from 1 in order, and every
  factual sentence in your rationale, summary and objections ends with the
  markers of the items behind it, e.g. "A 16 min hold leaves 39 min of fuel,
  above the 30 min final reserve [2][3]." A counter's rationale cites the
  counter's own evidence list. Text without markers, or markers that point at
  no item, is sent back. When a rule comes from a regulation, cite the rule
  (rule:<id>); its passage is attached automatically.
- Guardrails check every reply in code before anyone sees it: each sentence
  needs a marker; each number in a claim must appear in the tool output or
  model text of the source it cites (or be simple arithmetic on those
  numbers); each number in a sentence must come from the evidence that
  sentence cites; metric claims need at least 10 flights behind them. Copy
  numbers exactly from tool output. A reply that fails is sent back with the
  reasons; one that still fails does not count in the negotiation.
- If a term is unclear, lookup_concept it rather than assume.
- Keep rationale, objections and evidence short and factual. No pleasantries.
"""

ROLE_PROMPTS = {
    "atc": """\
Role: Air Traffic Control.
Your priorities: runway wake separation, keeping blocked taxiways out of use,
and maximising sector throughput (least total delay across the sequence).
You open the negotiation by proposing a revised arrival slot, runway and gate.
Ground your slot in history: weather_delay_min and air_system_delay_min at the
destination for this month, one of them grouped by arrival_hour so you can see
whether the disruption usually clears later. Look up atc.wake_separation.""",
    "pilot": """\
Role: Pilot in command.
Your priorities: never erode final reserve fuel, flight safety, avoid long
holds, and protect passengers' onward connections where that costs nothing
in safety.
Ground your position in history: arrival_delay on this route (origin and
destination), and late_aircraft_delay_min at the destination for this month.
Look up pilot.final_reserve_fuel.""",
    "ground": """\
Role: Ground operations.
Your priorities: a gate that is actually free at arrival, avoiding ground-crew
overtime, and keeping the turnaround on time.
Ground your position in history: taxi_in at the destination grouped by
arrival_hour (it moves the real on-block time, so add its median or p90 to the
arrival when judging the gate window and crew overtime), and
late_aircraft_delay_min at the destination (knock-on risk for the turnaround).
Look up the crew overtime rule.""",
}


@dataclass(frozen=True)
class Depth:
    """Minimum work an agent must show before its submit is accepted. Enforced in code, not just asked for."""

    min_metrics: int = int(os.environ.get("ATC_MIN_METRICS", "2"))
    min_lookups: int = int(os.environ.get("ATC_MIN_LOOKUPS", "1"))
    check_submitted_plan: bool = True
    max_repairs: int = 2  # submits sent back for missing work or ungrounded evidence

    @classmethod
    def none(cls) -> "Depth":
        return cls(min_metrics=0, min_lookups=0, check_submitted_plan=False)


class AgentError(RuntimeError):
    """The agent could not produce a valid answer (budget spent, refusal, truncation)."""


@dataclass
class ActionContext:
    """What the orchestrator hands an agent for one action."""

    turn: int
    history: list[TurnRecord]
    record: Callable[[ToolCall], None]
    stats: RunStats = field(default_factory=RunStats)
    # Called with every guardrail report (passed or not), so the UI sees rejections as they happen.
    guard: Callable[[str, GuardrailReport], None] = lambda agent, report: None


@dataclass
class Resources:
    """Read-only backends behind the tools. Any may be absent (tests, no data)."""

    sql: SqlEngine | None = None
    lookup: Callable[[str], str] | None = None
    semantic: object | None = None  # SemanticEngine
    catalog: MetricCatalog | None = None

    def toolbox(self, s: Scenario) -> Toolbox:
        return Toolbox(scenario=s, sql=self.sql, lookup=self.lookup, catalog=self.catalog,
                       semantic=self.semantic)


class Agent(Protocol):
    name: str

    def propose(self, s: Scenario, feedback: Evaluation | None, ctx: ActionContext) -> Proposal: ...
    def respond(self, s: Scenario, p: Proposal, ev: Evaluation, ctx: ActionContext) -> AgentResponse: ...


def _scenario_brief(s: Scenario) -> str:
    return s.model_dump_json(indent=1, exclude={"origin_info", "destination_info"})


def history_brief(history: list[TurnRecord]) -> str:
    if not history:
        return "Negotiation so far: none, this is the first turn."
    lines = ["Negotiation so far:"]
    for t in history:
        p = t.proposal
        lines.append(f"Turn {t.turn}: {t.proposer} proposed t+{p.arrival_min}, rwy {p.runway}, gate {p.gate} "
                     f"({'feasible' if t.evaluation.feasible else 'INFEASIBLE'}, cost {t.evaluation.cost:g}). "
                     f"Rationale: {p.rationale}")
        lines += [f"  [{e.id}] {e.claim} ({e.source}{'' if e.grounded else ', UNVERIFIED'})" for e in p.evidence]
        for name, r in t.responses.items():
            line = f"  {name}: {r.verdict.value}"
            if r.counter:
                c = r.counter
                ce = t.counter_evaluations.get(name)
                line += (f", counter t+{c.arrival_min}, rwy {c.runway}, gate {c.gate}"
                         + (f" ({'feasible' if ce.feasible else 'INFEASIBLE'}, cost {ce.cost:g})" if ce else ""))
            lines.append(line + (f": {r.summary}" if r.summary else ""))
            lines += [f"    objection: {o}" for o in r.objections]
            lines += [f"    [{e.id}] {e.claim} ({e.source}{'' if e.grounded else ', UNVERIFIED'})" for e in r.evidence]
        for v in t.vetoed_accepts:
            lines.append(f"  ! {v} accepted an infeasible plan; the rule engine vetoed it")
    return "\n".join(lines)


def _semantic_brief(role: str) -> str:
    try:
        from .semantic import brief_for
    except ImportError:
        return ""
    return brief_for(role)


def default_resources() -> Resources:
    from .semantic import default_engine as default_semantic_engine
    from .semantic import lookup
    semantic = default_semantic_engine()
    sql = default_sql_engine() if dataset_available() else None
    return Resources(sql=sql, lookup=lookup, semantic=semantic,
                     catalog=build_catalog(semantic) if sql is not None else None)


class LLMAgent:
    def __init__(self, name: str, resources: Resources, client: anthropic.Anthropic | None = None,
                 model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT, max_steps: int = MAX_STEPS,
                 depth: Depth = Depth()):
        self.name = name
        self.depth = depth
        self.resources = resources
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_steps = max_steps
        data = (resources.catalog.describe() if resources.catalog and resources.sql
                else "query_metric is unavailable on this server: the historical dataset is not loaded.")
        # Stable per role: shared rules, role, data catalogue, semantic grounding. Cached as a prefix.
        self.system = "\n\n".join(x for x in (SHARED_RULES, ROLE_PROMPTS[name], data, _semantic_brief(name)) if x)

    def propose(self, s: Scenario, feedback: Evaluation | None, ctx: ActionContext) -> Proposal:
        task = "Propose a revised arrival slot, runway and gate."
        if feedback is not None:
            task = (f"Your last proposal was rejected. Rule engine output:\n{evaluation_brief(feedback)}\n\n"
                    + task)
        return self._loop(s, ctx, task, SUBMIT_PROPOSAL, validate=Proposal.model_validate,
                          evidence_of=lambda p: [p], shown_verdict=feedback is not None)

    def respond(self, s: Scenario, p: Proposal, ev: Evaluation, ctx: ActionContext) -> AgentResponse:
        task = (f"Proposal on the table:\n{p.model_dump_json(indent=1)}\n\n{evaluation_brief(ev)}\n\n"
                "Accept it, or counter with one alternative.")
        return self._loop(s, ctx, task, SUBMIT_RESPONSE, validate=_validate_response,
                          evidence_of=lambda r: [r, *([r.counter] if r.counter else [])], shown_verdict=True)

    def _loop(self, s: Scenario, ctx: ActionContext, task: str, terminal: dict, validate, evidence_of,
              shown_verdict: bool):
        toolbox = self.resources.toolbox(s)
        toolbox.ledger.checked_plan = shown_verdict  # the task itself shows a rule-engine verdict
        if shown_verdict:
            toolbox.ledger.saw("task", task)
        grounder = Grounder(self.resources.semantic, s) if self.resources.semantic is not None else None
        guard = Guardrails(grounder, s) if grounder is not None else None
        attempts = 0
        repairs = 0
        tools = tool_defs(terminal, self.resources.catalog if self.resources.sql else None)
        messages: list[dict] = [{"role": "user", "content": (
            f"Scenario:\n{_scenario_brief(s)}\n\n{history_brief(ctx.history)}\n\n{task}\n\n"
            f"You have at most {self.max_steps} steps; finish with {terminal['name']}.")}]

        for step in range(1, self.max_steps + 1):
            resp = self._call(messages, tools, ctx.stats)
            messages.append({"role": "assistant", "content": resp.content})  # append-only, thinking kept
            calls = [b for b in resp.content if b.type == "tool_use"]
            submit = next((b for b in calls if b.name == terminal["name"]), None)
            if submit is not None:
                try:
                    answer = validate(submit.input)
                except ValueError as e:
                    self._reject(messages, calls, submit, f"Rejected: {e}")
                    continue
                attempts += 1
                gaps = self._depth_gaps(answer, toolbox)
                _stamp(answer, evidence_of, grounder, toolbox.ledger)
                report = _guard(answer, guard, toolbox.ledger, attempts)
                if report is not None:
                    ctx.guard(self.name, report)
                if (gaps or (report and not report.passed)) and repairs < self.depth.max_repairs \
                        and step < self.max_steps:
                    # Send it back: do the missing work, fix or drop the claims the guardrails flagged.
                    repairs += 1
                    why = (["Not enough work yet:", *(f"- {g}" for g in gaps)] if gaps else []) + \
                          (["Citation guardrails failed:", *(f"- {v.code} {v.message}" for v in report.violations)]
                           if report and not report.passed else [])
                    self._reject(messages, calls, submit, "Rejected.\n" + "\n".join(why)
                                 + f"\nDo that (call independent tools together), then call {terminal['name']} again.")
                    continue
                return answer
            if not calls:
                messages.append({"role": "user", "content": f"Finish by calling {terminal['name']}."})
                continue

            results = []
            for b in calls:
                out = toolbox.run(b.name, b.input)
                ctx.record(_tool_call(ctx, self.name, step, b.name, b.input, out))
                ctx.stats.tool_calls += 1
                text = out.output
                if step == self.max_steps - 1:
                    text += f"\n\nOne step left: call {terminal['name']} now."
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": text,
                                "is_error": out.is_error})
            messages.append({"role": "user", "content": results})
        raise AgentError(f"{self.name} did not call {terminal['name']} within {self.max_steps} steps")

    def _depth_gaps(self, answer, toolbox: Toolbox) -> list[str]:
        """What the agent still has to do before this submit counts. Skips tools this server can't offer."""
        d, led, gaps = self.depth, toolbox.ledger, []
        if toolbox.catalog is not None and toolbox.sql is not None and len(led.metrics_queried) < d.min_metrics:
            done = ", ".join(sorted(led.metrics_queried)) or "none"
            gaps.append(f"query_metric at least {d.min_metrics} different metrics (so far: {done})")
        if toolbox.lookup is not None and led.lookups < d.min_lookups:
            gaps.append(f"lookup_concept at least {d.min_lookups} rule or concept your decision rests on")
        plan = answer if isinstance(answer, Proposal) else answer.counter
        if d.check_submitted_plan and plan is not None and \
                (plan.arrival_min, plan.runway, plan.gate) not in led.plans_checked:
            gaps.append(f"check_proposal the exact plan you submit (t+{plan.arrival_min}, {plan.runway}, {plan.gate})")
        return gaps

    @staticmethod
    def _reject(messages: list[dict], calls, submit, why: str) -> None:
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "is_error": b is submit,
             "content": why if b is submit else "Not run: submit was rejected."} for b in calls]})

    def _call(self, messages: list[dict], tools: list[dict], stats: RunStats):
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=messages,
            cache_control={"type": "ephemeral"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        stats.llm_calls += 1
        stats.input_tokens += resp.usage.input_tokens
        stats.output_tokens += resp.usage.output_tokens
        stats.cache_read_tokens += resp.usage.cache_read_input_tokens or 0
        if resp.stop_reason == "refusal":
            raise AgentError(f"{self.name}: model declined the request")
        if resp.stop_reason == "max_tokens":
            raise AgentError(f"{self.name}: response hit max_tokens")
        return resp


def _tool_call(ctx: ActionContext, agent: str, step: int, tool: str, args: dict, out: ToolOutcome) -> ToolCall:
    return ToolCall(turn=ctx.turn, agent=agent, step=step, tool=tool, input=args, output=out.output,
                    is_error=out.is_error, duration_ms=out.duration_ms, sql_result=out.sql_result, sql=out.sql,
                    model_refs=out.model_refs)


def _stamp(answer, evidence_of, grounder: Grounder | None, ledger: Ledger) -> list[str]:
    """Number, ground and resolve every evidence item of the answer (and its counter). Returns the problems."""
    if grounder is None:
        return []
    problems = []
    for holder in evidence_of(answer):
        holder.evidence, found = grounder.finalize(holder.evidence, ledger)
        problems += found
    return problems


def _guard(answer, guard: Guardrails | None, ledger: Ledger, attempts: int) -> GuardrailReport | None:
    """Run the citation guardrails, stamp trust on the evidence and attach the report to the answer."""
    if guard is None:
        return None
    report = guard.check(answer, ledger).model_copy(update={"attempts": attempts})
    for h in holders_of(answer):
        h.evidence = guard.stamp_trust(h.evidence, ledger)
    answer.guardrail = report
    if isinstance(answer, AgentResponse) and answer.counter is not None:
        answer.counter.guardrail = report
    return report


def _validate_response(args: dict) -> AgentResponse:
    r = AgentResponse.model_validate(args)
    if r.verdict == Verdict.COUNTER and r.counter is None:
        raise ValueError("verdict is counter but counter is null; give one concrete plan or accept")
    if r.verdict == Verdict.ACCEPT:
        r.counter = None
    return r


class MockAgent:
    """Scripted agent: ATC opens naively, others counter with the solver's answer.

    Makes the same kinds of tool calls a real agent would (so the UI sees
    `tool_call` events) but decides by script, never by an LLM.
    """

    # The metric each role grounds itself in, as the real agents are told to.
    ROLE_METRIC = {"atc": "weather_delay_min", "pilot": "arrival_delay", "ground": "taxi_in"}

    def __init__(self, name: str, resources: Resources | None = None):
        self.name = name
        self.model = "mock"
        self.resources = resources or Resources()

    def propose(self, s: Scenario, feedback: Evaluation | None, ctx: ActionContext) -> Proposal:
        tb = self.resources.toolbox(s)
        evidence = self._history_evidence(s, tb, ctx)
        if feedback is None:
            plan = Proposal(arrival_min=s.earliest_arrival_min, runway=s.runways[0].name,
                            gate=s.gates[0].name, rationale="Earliest slot, first runway and gate.")
        else:
            best = fallback.solve(s)
            plan = best.proposal.model_copy() if best else Proposal(
                arrival_min=s.earliest_arrival_min, runway=s.runways[0].name, gate=s.gates[0].name,
                rationale="No feasible option found.")
        self._run(tb, ctx, "check_proposal", plan.model_dump(include={"arrival_min", "runway", "gate"}))
        plan.evidence = [Evidence(claim=f"Earliest possible arrival is t+{s.earliest_arrival_min}",
                                  source="scenario:earliest_arrival_min"),
                         Evidence(claim="The rule engine checked this plan", source="check_proposal"), *evidence]
        hist = f" {s.destination} history: {evidence[0].claim} [3]." if evidence else ""
        plan.rationale = f"{plan.rationale.rstrip('.')} [1][2].{hist}"
        self._finish(plan, lambda p: [p], s, tb, ctx)
        return plan

    def respond(self, s: Scenario, p: Proposal, ev: Evaluation, ctx: ActionContext) -> AgentResponse:
        tb = self.resources.toolbox(s)
        tb.ledger.checked_plan = True  # the verdict is in the task, as for the real agents
        tb.ledger.saw("task", evaluation_brief(ev))
        own = [r for r in ev.results if r.domain == self.name and (not r.passed or r.cost)]
        own_cost = sum(r.cost for r in own)
        best = fallback.solve(s)
        same = best is not None and best.proposal.model_dump(include={"arrival_min", "runway", "gate"}) \
            == p.model_dump(include={"arrival_min", "runway", "gate"})
        if ev.feasible and (own_cost == 0 or same):
            r = AgentResponse(verdict=Verdict.ACCEPT,
                              summary=("The plan is feasible and costs my domain nothing [1]." if own_cost == 0 else
                                       "The plan is feasible and nothing cheaper exists [1]."),
                              evidence=[Evidence(claim=f"Rule engine: feasible, soft cost {ev.cost:g}",
                                                 source="check_proposal")])
            self._finish(r, lambda x: [x], s, tb, ctx)
            return r
        counter = None
        if best is not None:
            self._run(tb, ctx, "check_proposal", best.proposal.model_dump(include={"arrival_min", "runway", "gate"}))
            counter = best.proposal.model_copy(update={
                "rationale": f"{best.proposal.rationale.rstrip('.')} [1].",
                "evidence": [Evidence(claim=f"Rule engine: feasible, soft cost {best.cost:g}",
                                      source="check_proposal")]})
        evidence = [Evidence(claim=f"{r.rule}: {r.detail}", source=f"rule:{r.rule_id}" if r.rule_id else "check_proposal")
                    for r in own] or [Evidence(claim=f"Rule engine: {'feasible' if ev.feasible else 'infeasible'}, "
                                                     f"soft cost {ev.cost:g}", source="check_proposal")]
        objections = [f"{r.rule}: {r.detail} [{i}]" for i, r in enumerate(own, 1)]
        if not objections:
            objections = (["Infeasible and no legal alternative exists [1]."] if not ev.feasible and best is None
                          else ["A cheaper feasible plan exists [1]."])
        r = AgentResponse(verdict=Verdict.COUNTER, objections=objections, counter=counter,
                          summary=f"Countering on {len(objections)} point(s) in my domain [1].", evidence=evidence)
        self._finish(r, lambda x: [x, *([x.counter] if x.counter else [])], s, tb, ctx)
        return r

    def _grounder(self, s: Scenario) -> Grounder | None:
        return Grounder(self.resources.semantic, s) if self.resources.semantic is not None else None

    def _finish(self, answer, evidence_of, s: Scenario, tb: Toolbox, ctx: ActionContext) -> None:
        """Same post-processing as a real agent's submit: ground, resolve, guardrails, trust."""
        grounder = self._grounder(s)
        _stamp(answer, evidence_of, grounder, tb.ledger)
        report = _guard(answer, Guardrails(grounder, s) if grounder else None, tb.ledger, 1)
        if report is not None:
            ctx.guard(self.name, report)

    def _history_evidence(self, s: Scenario, tb: Toolbox, ctx: ActionContext) -> list[Evidence]:
        cat = self.resources.catalog
        metric = self.ROLE_METRIC[self.name]
        if self.resources.sql is None or cat is None or metric not in cat.metrics:
            return []
        filters = {d: None for d in cat.dims} | {"destination": s.destination}
        out = self._run(tb, ctx, "query_metric", {"metric": metric, "filters": filters, "group_by": []})
        if out.is_error or out.sql_result is None or not out.sql_result.rows:
            return []
        n, avg, median, p90, _ = out.sql_result.rows[0]
        return [Evidence(claim=f"{s.destination} 2015, {n} disrupted arrivals: {metric} median {median}, "
                               f"p90 {p90} {cat.metrics[metric].unit}", source=f"metric:{metric}")]

    def _run(self, tb: Toolbox, ctx: ActionContext, tool: str, args: dict) -> ToolOutcome:
        out = tb.run(tool, args)
        ctx.record(_tool_call(ctx, self.name, 1, tool, args, out))
        ctx.stats.tool_calls += 1
        return out


def make_agents(mock: bool = False, model: str = DEFAULT_MODEL, resources: Resources | None = None,
                effort: str = DEFAULT_EFFORT, depth: Depth = Depth()) -> dict[str, Agent]:
    res = resources if resources is not None else default_resources()
    if mock:
        return {n: MockAgent(n, res) for n in ROLE_PROMPTS}
    client = anthropic.Anthropic()
    return {n: LLMAgent(n, res, client=client, model=model, effort=effort, depth=depth) for n in ROLE_PROMPTS}
