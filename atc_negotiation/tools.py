"""Tools the agents can call while deciding, and the two terminal "submit" tools.

Pattern borrowed from ACM's NativeToolLoop (copied, not imported): the agent
calls lookup tools as often as it needs, then ends its action by calling one
submit tool whose input is the typed answer. Tool inputs are strict JSON
schemas, so a submit call always parses into `Proposal` / `AgentResponse`.

Every tool goes through the semantic model, as ACM's tools go through its
semantic layer:

  query_metric    data retrieval. The agent names a model metric and model
                  dimensions; SQL is compiled from the model (metrics.py).
                  There is no free-SQL tool.
  check_proposal  the rule engine; each result names its model rule id and
                  the passage that rule cites.
  lookup_concept  the model's definition of a term, rule, code or passage.

Each call records the model elements it touched (`model_refs`) and what the
agent observed (`Ledger`), which grounding.py uses to check the agent's
submitted evidence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .grounding import Ledger, rule_refs
from .metrics import MetricCatalog, MetricError, run_metric
from .rules import evaluate
from .schemas import Proposal, Scenario, SqlResult
from .sqlengine import SqlEngine, SqlError

OUTPUT_LIMIT = 4000  # chars of tool output shown to the agent and stored in the trace

_EVIDENCE_SCHEMA = {
    "type": "array",
    "description": ("Every fact you rely on, each with the semantic-model element it comes from. Items are "
                    "numbered 1, 2, ... in order; refer to them in your text as [1], [2]. Only cite what a tool "
                    "returned this action or the scenario states."),
    "items": {
        "type": "object",
        "properties": {
            "claim": {"type": "string", "description": "Short factual statement with the number"},
            "source": {"type": "string", "description": (
                "metric:<name> (you queried it this action) | rule:<id> | passage:<id> | "
                "code:<CodeSet>.<value> | scenario:<field> | check_proposal")},
        },
        "required": ["claim", "source"],
        "additionalProperties": False,
    },
}
_PLAN_PROPS = {
    "arrival_min": {"type": "integer", "description": "Minutes after scheduled arrival"},
    "runway": {"type": "string"},
    "gate": {"type": "string"},
    "moves": {"type": "array", "items": {"type": "string"}, "description": (
        "Ids of moves the plan relies on: yours from 'Your private moves', or ones another agent has put on "
        "the table. Empty if none. The rule engine applies them, then checks every rule as usual")},
}
_PROPOSAL_PROPS = {
    **_PLAN_PROPS,
    "rationale": {"type": "string", "description": (
        "One or two sentences, plain language. Every factual sentence ends with citation markers for the "
        "evidence items behind it, e.g. 'Fuel stays above final reserve [2][3].'")},
    "evidence": _EVIDENCE_SCHEMA,
}
_PROPOSAL_SCHEMA = {"type": "object", "properties": _PROPOSAL_PROPS,
                    "required": list(_PROPOSAL_PROPS), "additionalProperties": False}



def query_metric_tool(catalog: MetricCatalog) -> dict:
    """Schema generated from the semantic model: metric and dimension names are enums of what it defines."""
    dims = {}
    for d in catalog.dims.values():
        if d.kind == "int":
            dims[d.name] = {"anyOf": [{"type": "integer"}, {"type": "array", "items": {"type": "integer"}},
                                      {"type": "null"}], "description": f"{d.description}. Value or [lo, hi]"}
        else:
            dims[d.name] = {"anyOf": [{"type": "string"}, {"type": "null"}], "description": d.description}
    return {
        "name": "query_metric",
        "description": (
            "Retrieve historical statistics (n, avg, median, p90, max) for one semantic-model metric over the "
            "2015 DOT flights, filtered and optionally grouped by model dimensions. This is the only way to read "
            "the data; SQL is compiled from the model. Set unused filters to null. Example: metric 'taxi_in', "
            "filters {destination: 'ORD', month: 1, all others null}, group_by []."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": list(catalog.metrics)},
                "filters": {"type": "object", "properties": dims, "required": list(dims),
                            "additionalProperties": False},
                "group_by": {"type": "array", "items": {"type": "string", "enum": list(catalog.dims)},
                             "description": "0-2 dimensions"},
            },
            "required": ["metric", "filters", "group_by"],
            "additionalProperties": False,
        },
    }

CHECK_PROPOSAL = {
    "name": "check_proposal",
    "description": (
        "Run the rule engine on a draft plan for this scenario. Every result names its semantic-model rule id "
        "and the passage that rule comes from. Use before submitting a proposal or counter."
    ),
    "input_schema": {"type": "object", "properties": _PLAN_PROPS, "required": list(_PLAN_PROPS),
                     "additionalProperties": False},
}
LOOKUP_CONCEPT = {
    "name": "lookup_concept",
    "description": (
        "Look up a term, rule id, code or regulation passage in the semantic model (e.g. 'final reserve "
        "fuel', 'atc.wake_separation', 'WEATHER_DELAY', 'MCT') and get its definition and source id."
    ),
    "input_schema": {"type": "object", "properties": {"term": {"type": "string"}},
                     "required": ["term"], "additionalProperties": False},
}
SUBMIT_PROPOSAL = {
    "name": "submit_proposal",
    "description": "Submit your proposal. This ends your action; call it exactly once, last.",
    "input_schema": _PROPOSAL_SCHEMA,
}
SUBMIT_RESPONSE = {
    "name": "submit_response",
    "description": ("Submit your verdict on the proposal on the table. This ends your action; call it exactly "
                    "once, last. counter is required when verdict is counter and must be null when accepting."),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "counter"]},
            "summary": {"type": "string", "description": (
                "One or two sentences on why you accept or counter, with [n] citation markers.")},
            "objections": {"type": "array", "items": {"type": "string"},
                           "description": "Empty when accepting. Each one carries [n] citation markers."},
            "counter": {"anyOf": [_PROPOSAL_SCHEMA, {"type": "null"}]},
            "evidence": _EVIDENCE_SCHEMA,
        },
        "required": ["verdict", "summary", "objections", "counter", "evidence"],
        "additionalProperties": False,
    },
}

def tool_defs(terminal: dict, catalog: MetricCatalog | None) -> list[dict]:
    # Order is fixed and the catalog is static per process, so the tools prefix stays cacheable.
    lookups = [CHECK_PROPOSAL, LOOKUP_CONCEPT]
    if catalog is not None and catalog.metrics:
        lookups.insert(0, query_metric_tool(catalog))
    return [{**t, "strict": True} for t in [*lookups, terminal]]


@dataclass
class ToolOutcome:
    output: str
    is_error: bool = False
    duration_ms: float = 0.0
    sql_result: SqlResult | None = None
    sql: str | None = None
    model_refs: list[str] = field(default_factory=list)


@dataclass
class Toolbox:
    """Executes lookup tools for one agent action and records what it observed."""

    scenario: Scenario
    sql: SqlEngine | None
    lookup: Callable[[str], str] | None
    catalog: MetricCatalog | None = None
    semantic: object | None = None  # SemanticEngine, for rule sources and alias resolution
    ledger: Ledger = field(default_factory=Ledger)
    _handlers: dict = field(init=False)

    def __post_init__(self) -> None:
        self._handlers = {"query_metric": self._query_metric, "check_proposal": self._check,
                          "lookup_concept": self._lookup}

    def run(self, name: str, args: dict) -> ToolOutcome:
        t0 = time.perf_counter()
        handler = self._handlers.get(name)
        if handler is None:
            out = ToolOutcome(f"unknown tool {name!r}", is_error=True)
        else:
            try:
                out = handler(args)
            except (MetricError, SqlError, KeyError, ValueError, TypeError) as e:  # bad input, shown back
                out = ToolOutcome(f"{type(e).__name__}: {e}", is_error=True)
        out.output = out.output[:OUTPUT_LIMIT]
        out.duration_ms = (time.perf_counter() - t0) * 1000
        return out

    def _query_metric(self, args: dict) -> ToolOutcome:
        if self.sql is None or self.catalog is None:
            return ToolOutcome("historical dataset or semantic model not loaded on this server", is_error=True)
        metric, group_by = args["metric"], args.get("group_by") or []
        filters = {k: v for k, v in (args.get("filters") or {}).items() if v is not None}
        text, r, sql = run_metric(self.catalog, self.sql, metric, filters, group_by)
        self.ledger.metrics_queried.add(metric)
        self.ledger.saw(f"metric:{metric}", text)
        if "n" in r.columns:
            i = r.columns.index("n")
            self.ledger.metric_samples.setdefault(metric, []).extend(int(row[i] or 0) for row in r.rows)
        refs = [f"metric:{metric}", *(self.catalog.dims[d].model_ref for d in [*filters, *group_by])]
        return ToolOutcome(text, sql=sql, model_refs=list(dict.fromkeys(refs)),
                           sql_result=SqlResult(columns=r.columns, rows=r.rows, truncated=r.truncated))

    def _check(self, args: dict) -> ToolOutcome:
        ev = evaluate(self.scenario, Proposal(**args, rationale="draft"))
        self.ledger.checked_plan = True
        self.ledger.plans_checked.add(plan_key(Proposal(**args, rationale="draft")))
        text = evaluation_brief(ev, self.semantic)
        self.ledger.saw("check_proposal", text)
        return ToolOutcome(text, model_refs=rule_refs(ev.results))

    def _lookup(self, args: dict) -> ToolOutcome:
        if self.lookup is None:
            return ToolOutcome("semantic model not available", is_error=True)
        term = args["term"]
        self.ledger.lookups += 1
        hit = self.lookup(term)
        if not hit:
            return ToolOutcome(f"{term!r} is not in the semantic model. Don't guess its meaning.")
        self.ledger.saw(f"lookup:{term}", hit)
        refs = []
        if self.semantic is not None:
            resolved = self.semantic.resolve(term)
            if resolved:
                refs.append(f"{resolved[0]}:{resolved[1]}")
            elif term in self.semantic.rule_by_id:
                refs.append(f"rule:{term}")
            elif term in self.semantic.passage_by_id:
                refs.append(f"passage:{term}")
        return ToolOutcome(hit, model_refs=refs)


def plan_key(p: Proposal) -> tuple:
    """What makes two plans the same plan: slot, runway, gate and the moves it uses."""
    return p.arrival_min, p.runway, p.gate, tuple(sorted(set(p.moves)))


def evaluation_brief(ev, semantic=None) -> str:
    """Rule engine verdict as text. With the semantic engine, each line also names the rule's source."""
    rows = []
    for r in ev.results:
        ref = f"rule:{r.rule_id}" if r.rule_id else f"{r.domain}/{r.rule}"
        rule = semantic.rule_by_id.get(r.rule_id) if semantic is not None and r.rule_id else None
        src = f" [passage:{rule.source}]" if rule is not None and rule.source else ""
        rows.append(f"- [{'PASS' if r.passed else 'FAIL'}{' hard' if r.hard else ''}] {ref}{src}: {r.detail}"
                    + (f" (cost {r.cost:g})" if r.cost else ""))
    status = "FEASIBLE" if ev.feasible else "INFEASIBLE"
    return f"Rule engine verdict: {status}, total soft cost {ev.cost:g}\n" + "\n".join(rows)
