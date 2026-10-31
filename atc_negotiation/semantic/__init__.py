"""Semantic model: what the agents are grounded in, as data.

Layers (mirrors the ACM semantic-engine layout, trimmed for one use case):
  schema     - tables/columns profiled from the CSVs (semantic/schema.yaml, generated, never hand-edited)
  ontology   - concepts, entity types bound to columns, relations, metrics (semantic/model.yaml, curated)
  codes      - what each coded value means (BTS delay causes, ICAO wake categories)
  rules      - every operational threshold/constraint, typed, with its source
  knowledge  - passages from the challenge brief and the regulations, linked to model elements

Every element carries Evidence (who said so, where) and a status. The runtime
never parses prose: `engine.py` indexes the model, `briefing.py` renders one
agent's slice of it into that agent's system prompt, and `rules.py` cites rule
ids so the trace links back here.

Public API (stable; the agent loop and the API depend on these two):
    brief_for(role)  -> str   grounding section for one agent's system prompt
    lookup(term)     -> str   what a term means in this model, with its source; '' if unknown
"""

from __future__ import annotations

from .engine import default_engine
from .model import Domain


def brief_for(role: Domain) -> str:
    """Grounding text for one agent. Static per role, so it caches as a prompt prefix."""
    from .briefing import render_brief
    return render_brief(default_engine(), role)


def lookup(term: str) -> str:
    """Resolve a word an agent uses to its model element and describe it with its source.

    Returns '' when the term is unknown so a tool wrapper can say so instead of guessing.
    """
    eng = default_engine()
    hit = eng.resolve(term)
    if hit is None:
        # maybe it's a rule id, a passage id or a code
        if term in eng.rule_by_id:
            hit = ("rule", term)
        elif term in eng.passage_by_id:
            p = eng.passage_by_id[term]
            return f"[{p.id}] {p.doc}, {p.title}: {p.text.strip()}"
        else:
            for cs in eng.model.code_sets:
                if term.upper() in cs.entries:
                    e = cs.entries[term.upper()]
                    return f"{term.upper()} in {cs.name}: {e.label}. {e.definition} (source: {cs.source})"
            return ""

    kind, name = hit
    if kind == "concept":
        c = eng.concept_by_name[name]
        passages = eng.passages_about("concept", name)
        src = f" Sources: {', '.join(p.id for p in passages)}." if passages else ""
        return f"{name} (concept, {c.domain}): {c.definition}{src}"
    if kind == "type":
        t = eng.type_by_name[name]
        where = (f"synthetic; lives on Scenario.{t.scenario_field}" if t.synthetic
                 else f"{t.table}.{t.id_column}" if t.table else "scenario field")
        return f"{name} (entity type, concept {t.concept}, {where}): {t.description or eng.concept_by_name[t.concept].definition}"
    if kind == "metric":
        m = eng.metric_by_name[name]
        return f"{name} (metric, {m.unit or 'n/a'}, {m.domain}): {m.description}" + (f" Formula: {m.formula}" if m.formula else "")
    if kind == "rule":
        r = eng.rule_by_id[name]
        hard = "hard" if r.hard else "soft" if r.hard is False else "protocol"
        params = f" Params: {r.params}." if r.params else ""
        return f"{name} ({hard} {r.kind}, {r.domain}): {r.text}{params} Source: {r.source or 'brief'}."
    if kind == "code":
        for cs in eng.model.code_sets:
            if name in cs.entries:
                e = cs.entries[name]
                return f"{name} in {cs.name}: {e.label}. {e.definition} (source: {cs.source})"
    return ""


__all__ = ["brief_for", "lookup", "default_engine"]
