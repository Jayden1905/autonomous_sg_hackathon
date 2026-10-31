"""In-memory index over a SemanticModel. Built once, read many times. No I/O after init.

Everything an agent prompt or the API needs is a lookup here, so neither has to walk lists.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

from .model import (
    CodeSet, Concept, Domain, EntityType, KnowledgePassage, Metric, Rule, SemanticModel,
)


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").split())


class SemanticEngine:
    def __init__(self, model: SemanticModel) -> None:
        self.model = model
        self.concept_by_name = {c.name: c for c in model.concepts}
        self.type_by_name = {t.name: t for t in model.entity_types}
        self.metric_by_name = {m.name: m for m in model.metrics}
        self.rule_by_id = {r.id: r for r in model.rules}
        self.code_set_by_name = {c.name: c for c in model.code_sets}
        self.passage_by_id = {p.id: p for p in model.passages}

        self._links_by_target: dict[tuple[str, str], list[str]] = defaultdict(list)
        for k in model.knowledge_links:
            self._links_by_target[(k.target_kind, k.target)].append(k.passage_id)

        # alias index: surface form → (kind, name). Concept aliases, type aliases, vocabulary.
        self._alias: dict[str, tuple[str, str]] = {}
        for c in model.concepts:
            for a in [c.name, *c.aliases]:
                self._alias.setdefault(_norm(a), ("concept", c.name))
        for t in model.entity_types:
            for a in [t.name, *t.aliases]:
                self._alias.setdefault(_norm(a), ("type", t.name))
        for m in model.metrics:
            self._alias.setdefault(_norm(m.name), ("metric", m.name))
        for v in model.vocabulary:
            self._alias[_norm(v.term)] = (v.target_kind, v.target)

    # ── per-domain slices (what a briefing is built from) ──

    def rules_for(self, domain: Domain, include_shared: bool = True) -> list[Rule]:
        return [r for r in self.model.rules
                if r.domain == domain or (include_shared and r.domain == "shared")]

    def metrics_for(self, domain: Domain, include_shared: bool = True) -> list[Metric]:
        return [m for m in self.model.metrics
                if m.domain == domain or (include_shared and m.domain == "shared")]

    def concepts_for(self, domain: Domain, include_shared: bool = True) -> list[Concept]:
        return [c for c in self.model.concepts if not c.abstract
                and (c.domain == domain or (include_shared and c.domain == "shared"))]

    def types_for(self, domain: Domain, include_shared: bool = True) -> list[EntityType]:
        return [t for t in self.model.entity_types
                if t.domain == domain or (include_shared and t.domain == "shared")]

    def passages_for(self, domain: Domain, include_shared: bool = True) -> list[KnowledgePassage]:
        return [p for p in self.model.passages
                if p.domain == domain or (include_shared and p.domain == "shared")]

    # ── element lookups ──

    def passages_about(self, kind: str, name: str) -> list[KnowledgePassage]:
        return [self.passage_by_id[p] for p in self._links_by_target.get((kind, name), [])
                if p in self.passage_by_id]

    def code_sets_for(self, domain: Domain) -> list[CodeSet]:
        wanted = {t.name for t in self.types_for(domain)}
        return [cs for cs in self.model.code_sets
                if any(cs.name == s or cs.column and cs.column.split(".")[0] in wanted
                       for s in wanted) or domain == "shared"]

    def resolve(self, text: str) -> tuple[str, str] | None:
        """'tail number' → ('type', 'Aircraft'). None if unknown. Exact-after-normalise only; no fuzzy."""
        return self._alias.get(_norm(text))

    def rule_params(self, rule_id: str) -> dict:
        r = self.rule_by_id.get(rule_id)
        return dict(r.params) if r else {}

    def synthetic_types(self) -> list[EntityType]:
        return [t for t in self.model.entity_types if t.synthetic]

    def column_profile(self, table: str, column: str):
        for t in self.model.tables:
            if t.name == table:
                for c in t.columns:
                    if c.name == column:
                        return c
        return None


@lru_cache(maxsize=1)
def default_engine() -> SemanticEngine:
    return SemanticEngine(SemanticModel.load())
