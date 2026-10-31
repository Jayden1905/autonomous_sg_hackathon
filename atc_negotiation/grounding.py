"""Checks that what an agent says is anchored in the semantic model.

An agent's submitted evidence is a list of {claim, source}. `source` must
resolve to something real:

    metric:<name>          a model metric the agent queried in THIS action
    rule:<id>              a rule in the model (what check_proposal reports)
    passage:<id>           a knowledge passage (regulation, brief)
    code:<CodeSet>.<value> a coded value, e.g. code:DelayCause.WEATHER_DELAY
    scenario:<field>       a field of the scenario being negotiated
    check_proposal         the rule engine's verdict on a plan in this action

Anything else is marked `grounded=False` and the agent is sent back to fix
it. This is what stops an agent from citing a statistic it never retrieved,
or a regulation the model doesn't contain.

Citations: evidence items are numbered, and the agent's prose (rationale,
objections, summary) refers to them as [1], [2]. `check_markers` rejects prose
with no markers or with markers that point at nothing; `resolve` turns each
source into a `Citation` (label, quote, URL) read from the model, so the UI
can render footnotes without guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import Citation, Evidence, Scenario

PREFIXES = ("metric:", "rule:", "passage:", "code:", "scenario:")


@dataclass
class Ledger:
    """What one agent action actually observed, so its citations can be checked against it."""

    metrics_queried: set[str] = field(default_factory=set)
    checked_plan: bool = False
    plans_checked: set[tuple[int, str, str]] = field(default_factory=set)  # (arrival_min, runway, gate)
    lookups: int = 0
    # What the agent was shown this action, by source key ("metric:taxi_in", "check_proposal",
    # "lookup:<term>", "task"). guardrails.py checks the numbers in claims against these.
    observed: dict[str, list[str]] = field(default_factory=dict)
    metric_samples: dict[str, list[int]] = field(default_factory=dict)  # metric -> n per result row

    def saw(self, key: str, text: str) -> None:
        self.observed.setdefault(key, []).append(text)


class Grounder:
    def __init__(self, engine, scenario: Scenario):
        self.engine = engine
        self.scenario_fields = set(Scenario.model_fields)
        self.scenario = scenario

    def check(self, ev: Evidence, ledger: Ledger) -> str | None:
        """None if grounded, else the reason it isn't (shown to the agent)."""
        src = ev.source.strip()
        if src == "check_proposal":
            return None if ledger.checked_plan else "cites check_proposal but no plan was checked this action"
        kind, _, ref = src.partition(":")
        if kind == "metric":
            if ref not in self.engine.metric_by_name:
                return f"metric {ref!r} is not in the semantic model"
            if ref not in ledger.metrics_queried:
                return f"metric {ref!r} was not queried this action; call query_metric first or drop the claim"
            return None
        if kind == "rule":
            return None if ref in self.engine.rule_by_id else f"rule {ref!r} is not in the semantic model"
        if kind == "passage":
            return None if ref in self.engine.passage_by_id else f"passage {ref!r} is not in the semantic model"
        if kind == "code":
            cs, _, value = ref.partition(".")
            code_set = self.engine.code_set_by_name.get(cs)
            return None if code_set and value in code_set.entries else f"code {ref!r} is not in the semantic model"
        if kind == "scenario":
            return None if ref.split(".")[0].split("[")[0] in self.scenario_fields else f"no scenario field {ref!r}"
        return f"source must start with one of {', '.join(PREFIXES)} or be 'check_proposal'"

    def stamp(self, evidence: list[Evidence], ledger: Ledger) -> tuple[list[Evidence], list[str]]:
        """Returns evidence with `grounded` set, and the problems found."""
        out, problems = [], []
        for ev in evidence:
            reason = self.check(ev, ledger)
            out.append(ev.model_copy(update={"grounded": reason is None}))
            if reason:
                problems.append(f"{ev.source}: {reason}")
        return out, problems


    def resolve(self, ev: Evidence) -> Citation:
        """What the cited source says, read from the model."""
        e, src = self.engine, ev.source.strip()
        if src == "check_proposal":
            return Citation(kind="rule_engine", ref="check_proposal", label="Rule engine (rules.py)",
                            text="Deterministic check of this plan against every hard and soft rule in the model.")
        kind, _, ref = src.partition(":")
        if kind == "rule" and ref in e.rule_by_id:
            r = e.rule_by_id[ref]
            p = e.passage_by_id.get(r.source)
            hardness = "hard" if r.hard else "soft" if r.hard is False else "protocol"
            return Citation(kind="rule", ref=ref, label=f"Rule {ref} ({hardness})" + (f", {_passage_label(p)}" if p else ""),
                            text=r.text, url=(p.url or None) if p else None, passage_id=r.source or None)
        if kind == "passage" and ref in e.passage_by_id:
            p = e.passage_by_id[ref]
            return Citation(kind="passage", ref=ref, label=_passage_label(p), text=p.text.strip(),
                            url=p.url or None, passage_id=ref)
        if kind == "metric" and ref in e.metric_by_name:
            m = e.metric_by_name[ref]
            ps = e.passages_about("metric", ref)
            return Citation(kind="metric", ref=ref,
                            label=f"Metric {ref} ({m.unit}), 2015 US DOT on-time data via query_metric",
                            text=m.description or m.formula, url=(ps[0].url or None) if ps else None,
                            passage_id=ps[0].id if ps else None)
        if kind == "code":
            cs_name, _, value = ref.partition(".")
            cs = e.code_set_by_name.get(cs_name)
            if cs and value in cs.entries:
                entry = cs.entries[value]
                p = e.passage_by_id.get(cs.source)
                return Citation(kind="code", ref=ref, label=f"{cs_name} {value}: {entry.label}",
                                text=entry.definition or entry.label, url=(p.url or None) if p else None,
                                passage_id=cs.source or None)
        if kind == "scenario":
            field_name = ref.split(".")[0].split("[")[0]
            if field_name in self.scenario_fields:
                synthetic = field_name in self.scenario.synthetic_fields
                return Citation(kind="scenario", ref=ref, label=f"Scenario {self.scenario.scenario_id}: {ref}",
                                text=("Generated for this scenario (synthetic, not in the DOT data)." if synthetic
                                      else "From the scenario / DOT row being negotiated."))
        return Citation(kind="unknown", ref=src, label=src, text="Not found in the semantic model.")

    def finalize(self, evidence: list[Evidence], ledger: Ledger) -> tuple[list[Evidence], list[str]]:
        """Number, ground and resolve evidence. Returns the evidence and grounding problems."""
        stamped, problems = self.stamp(evidence, ledger)
        out = [ev.model_copy(update={"id": i, "citation": self.resolve(ev)}) for i, ev in enumerate(stamped, 1)]
        return out, problems


_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def markers(text: str) -> set[int]:
    """[1], [2, 3] -> {1, 2, 3}"""
    return {int(n) for group in _MARKER.findall(text) for n in group.split(",")}


def check_markers(texts: list[tuple[str, str]], n_evidence: int) -> list[str]:
    """Each (name, text) with content must cite at least one evidence item, and only ones that exist."""
    problems = []
    for name, text in texts:
        if not text.strip():
            continue
        found = markers(text)
        if not found:
            problems.append(f"{name} has no [n] citation markers; cite the evidence items it relies on")
        bad = sorted(n for n in found if not 1 <= n <= n_evidence)
        if bad:
            problems.append(f"{name} cites {bad} but evidence has items 1..{n_evidence}")
    return problems


def _passage_label(p) -> str:
    return f"{p.doc}, {p.title}"


def rule_refs(results) -> list[str]:
    return [f"rule:{r.rule_id}" for r in results if r.rule_id]
