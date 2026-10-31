"""The semantic model as a node/edge graph for the viewer and for anyone who wants to draw it.

Layers (colour in the viewer):  ontology | rules | knowledge
Kinds  (shape in the viewer):   concept, type, metric | rule, code_set | passage
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .engine import SemanticEngine, default_engine

LAYER_OF = {"concept": "ontology", "type": "ontology", "metric": "ontology",
            "rule": "rules", "code_set": "rules", "passage": "knowledge"}


def _nid(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def build_graph(engine: SemanticEngine | None = None) -> dict[str, Any]:
    eng = engine or default_engine()
    m = eng.model
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def node(kind: str, name: str, label: str, domain: str, **detail: Any) -> None:
        nodes.append({"id": _nid(kind, name), "kind": kind, "layer": LAYER_OF[kind],
                      "label": label, "domain": domain, **detail})

    def edge(src: str, dst: str, rel: str) -> None:
        edges.append({"source": src, "target": dst, "rel": rel})

    for c in m.concepts:
        node("concept", c.name, c.name, c.domain, definition=c.definition, aliases=c.aliases, abstract=c.abstract)
        if c.extends:
            edge(_nid("concept", c.name), _nid("concept", c.extends), "extends")

    for t in m.entity_types:
        where = (f"Scenario.{t.scenario_field}" if t.synthetic and t.scenario_field
                 else f"{t.table}.{t.id_column}" if t.table and t.id_column
                 else t.table or t.scenario_field or "")
        node("type", t.name, t.name, t.domain, description=t.description, synthetic=t.synthetic,
             bound_to=where, columns=t.attribute_columns, status=t.status,
             evidence=[e.model_dump() for e in t.evidence])
        edge(_nid("type", t.name), _nid("concept", t.concept), "is_a")

    for r in m.relation_types:
        edge(_nid("type", r.source_type), _nid("type", r.target_type), r.name)

    for mt in m.metrics:
        node("metric", mt.name, mt.name, mt.domain, description=mt.description, unit=mt.unit,
             formula=mt.formula, inputs=mt.inputs, range=[mt.range_lo, mt.range_hi])
        for g in mt.grain:
            if g in eng.type_by_name:
                edge(_nid("metric", mt.name), _nid("type", g), "measures")

    for r in m.rules:
        node("rule", r.id, r.id, r.domain, text=r.text, kind_of_rule=r.kind, hard=r.hard,
             params=r.params, enforced_by=r.enforced_by, source=r.source, status=r.status)
        for s in r.subjects:
            if s in eng.type_by_name:
                edge(_nid("rule", r.id), _nid("type", s), "constrains")
            elif s in eng.metric_by_name:
                edge(_nid("rule", r.id), _nid("metric", s), "constrains")
            elif s in eng.code_set_by_name:
                edge(_nid("rule", r.id), _nid("code_set", s), "constrains")
        if r.source and r.source in eng.passage_by_id:
            edge(_nid("rule", r.id), _nid("passage", r.source), "cites")

    for cs in m.code_sets:
        node("code_set", cs.name, cs.name, "shared", description=cs.description, column=cs.column,
             entries={k: {"label": v.label, "definition": v.definition} for k, v in cs.entries.items()},
             source=cs.source)
        if cs.source and cs.source in eng.passage_by_id:
            edge(_nid("code_set", cs.name), _nid("passage", cs.source), "cites")

    for p in m.passages:
        node("passage", p.id, p.id, p.domain, doc=p.doc, title=p.title, text=p.text,
             kind_of_passage=p.kind, url=p.url, retrieved=p.retrieved)

    have = {n["id"] for n in nodes}
    for k in m.knowledge_links:
        src, dst = _nid(k.target_kind, k.target), _nid("passage", k.passage_id)
        if src in have and dst in have and not any(e["source"] == src and e["target"] == dst for e in edges):
            edge(src, dst, k.kind)

    counts = {k: sum(1 for n in nodes if n["kind"] == k) for k in LAYER_OF}
    return {
        "project": m.project.model_dump(),
        "version": m.version,
        "counts": {**counts, "edges": len(edges)},
        "domains": ["atc", "pilot", "ground", "shared"],
        "nodes": nodes,
        "edges": edges,
    }


@lru_cache(maxsize=1)
def default_graph() -> dict[str, Any]:
    return build_graph()
