"""Citation guardrails: deterministic checks every agent reply must pass.

grounding.py answers "does this source exist in the semantic model, and did
the agent observe it?". This module answers "is each claim actually supported
by the source it cites?", and runs on every submit before the orchestrator
sees it. Code only, no LLM judging an LLM.

  G1 uncited_sentence    every factual sentence in rationale / summary / objections ends in [n]
  G2 dangling_marker     every [n] points at an evidence item that exists
  G3 ungrounded_source   source resolves in the model and was observed (grounding.Grounder)
  G4 unsupported_number  every number in a claim is in its cited source, or a time on the plan's
                         timeline: its arrival +/- a source number (t+38 + 13 min taxi-in = t+51)
  G5 off_source          a number the claim uses is real (the agent observed it) but came from a
                         different source than the one cited
  G6 unsupported_prose   every number in a sentence is in the evidence that sentence cites, or a
                         time on the plan's timeline derived from it
  G7 thin_sample         a metric claim rests on at least MIN_SAMPLE flights

A failing reply goes back to the agent with the violations (agents.py, up to
`Depth.max_repairs` times). If it still fails, it is returned with
`guardrail.passed = False` and the orchestrator does not let it count.

Trust is reported, not enforced: `high` for regulations, the rule engine and
well-sampled metrics; `medium` for brief-derived assumptions and thin
samples; `low` for synthetic scenario fields.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from .grounding import MARKER, Grounder, Ledger, check_markers, markers
from .schemas import AgentResponse, Evidence, GuardrailReport, GuardrailViolation, Proposal, Scenario

MIN_SAMPLE = 10
# Numbers that carry no factual weight: list ordinals and the dataset year. Citation markers are stripped first.
_FREE_NUMBERS = {0.0, 1.0, 2.0, 3.0, 2015.0}
_NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
# Identifiers whose digits are names, not quantities: 27R, B12, UA1234, H>M, 2015 dataset year, t+38 is a number.
_CODE = re.compile(r"\b(?:[A-Z]{1,3}\d+[A-Z]?|\d{1,2}[LRC])\b")


def numbers(text: str) -> set[float]:
    text = _CODE.sub(" ", MARKER.sub(" ", text))
    return {float(m.replace(",", "")) for m in _NUM.findall(text)} - _FREE_NUMBERS


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.strip()) if s.strip()]


def _derivable(n: float, pool: set[float], anchors: set[float] = frozenset()) -> bool:
    """n is literally in the pool, or a time on the plan's timeline: anchor +/- a pool number.

    Anchors are the plan's arrival minute and the scenario's earliest arrival, so "on-block t+51 =
    38 + 13 [taxi_in]" and "16 min hold = 38 - 22" pass. Nothing else is derived: combining two stats,
    or scaling by 60, makes coincidences too likely, so "p90 is 47" must match the source literally.
    """
    if n in pool or abs(n) in pool:
        return True
    return any(n in (a + b, a - b, b - a) for a, b in itertools.product(pool, anchors))


@dataclass
class Guardrails:
    grounder: Grounder
    scenario: Scenario

    def check(self, answer, ledger: Ledger) -> GuardrailReport:
        """Run G1-G7 on a Proposal or AgentResponse (and its counter). Evidence must already be finalized."""
        violations: list[GuardrailViolation] = []
        holders = [("proposal", answer)] if isinstance(answer, Proposal) else \
            [("response", answer), *([("counter", answer.counter)] if answer.counter else [])]
        for where, h in holders:
            anchors = self._anchors(h if isinstance(h, Proposal) else None)
            violations += self._evidence(where, h.evidence, ledger, anchors)
            for name, text in self._prose(where, h):
                violations += self._sentences(name, text, h.evidence, ledger, anchors)
        trust = {e.id: self.trust(e, ledger) for _, h in holders for e in h.evidence}
        return GuardrailReport(passed=not violations, violations=violations,
                               checked_claims=sum(len(h.evidence) for _, h in holders),
                               low_trust=sorted(i for i, t in trust.items() if t == "low"))

    # ── per evidence item ──

    def _anchors(self, plan: Proposal | None) -> set[float]:
        """Numbers a reply may always combine with cited ones: the plan's arrival and the scenario's timeline."""
        s = self.scenario
        nums = {float(s.earliest_arrival_min)}
        if plan is not None:
            nums.add(float(plan.arrival_min))
        return nums

    def _evidence(self, where: str, evidence: list[Evidence], ledger: Ledger,
                  anchors: set[float]) -> list[GuardrailViolation]:
        out = []
        everything = numbers(self._everything(ledger))
        for e in evidence:
            if not e.grounded:
                reason = self.grounder.check(e, ledger) or "not in the semantic model"
                out.append(_v("G3", "ungrounded_source", where, e.id, f"[{e.id}] {e.source}: {reason}"))
                continue
            said = numbers(self._source_text(e, ledger))
            unsupported = [n for n in sorted(numbers(e.claim)) if not _derivable(n, said, anchors)]
            invented = [n for n in unsupported if n not in everything]
            borrowed = [n for n in unsupported if n in everything]
            if invented:
                out.append(_v("G4", "unsupported_number", where, e.id,
                              f"[{e.id}] {_fmt(invented)} in the claim is not in {e.source} or anything you observed "
                              f"this action; copy numbers exactly from tool output or drop them"))
            if borrowed:
                out.append(_v("G5", "off_source", where, e.id,
                              f"[{e.id}] {_fmt(borrowed)} did not come from {e.source}; split the claim and cite the "
                              f"source each number came from"))
            if e.source.startswith("metric:"):
                ns = ledger.metric_samples.get(e.source.split(":", 1)[1], [])
                if ns and max(ns) < MIN_SAMPLE:
                    out.append(_v("G7", "thin_sample", where, e.id,
                                  f"[{e.id}] rests on at most {max(ns)} flights (< {MIN_SAMPLE}); widen the filters "
                                  f"(drop hour or month) before relying on it"))
        return out

    # ── per sentence ──

    @staticmethod
    def _prose(where: str, h) -> list[tuple[str, str]]:
        if isinstance(h, Proposal):
            return [(f"{where} rationale", h.rationale)]
        return [("summary", h.summary), *((f"objection {i}", o) for i, o in enumerate(h.objections, 1))]

    def _sentences(self, name: str, text: str, evidence: list[Evidence], ledger: Ledger,
                   anchors: set[float]) -> list[GuardrailViolation]:
        out = [_v("G2" if "cites" in p else "G1", "dangling_marker" if "cites" in p else "uncited_sentence",
                  name, None, p) for p in check_markers([(name, text)], len(evidence))]
        by_id = {e.id: e for e in evidence}
        for sent in sentences(text):
            cited = markers(sent)
            if not cited:
                if numbers(sent) or len(sent.split()) > 4:
                    out.append(_v("G1", "uncited_sentence", name, None,
                                  f"{name}: sentence has no [n] marker: \"{_clip(sent)}\""))
                continue
            support = set()
            for i in cited:
                if i in by_id:
                    support |= numbers(by_id[i].claim) | numbers(self._source_text(by_id[i], ledger))
            missing = sorted(n for n in numbers(sent) if not _derivable(n, support, anchors))
            if missing:
                out.append(_v("G6", "unsupported_prose", name, None,
                              f"{name}: {_fmt(missing)} in \"{_clip(sent)}\" is not in the evidence it cites "
                              f"{sorted(cited)}; cite the item it comes from"))
        return out

    # ── what a source says ──

    def _source_text(self, e: Evidence, ledger: Ledger) -> str:
        """Everything the cited source said: model text, plus tool output observed under that source."""
        parts = [e.citation.text if e.citation else ""]
        src = e.source.strip()
        if src == "check_proposal":
            parts += ledger.observed.get("check_proposal", []) + ledger.observed.get("task", [])
        elif src.startswith("metric:"):
            parts += ledger.observed.get(src, [])
        elif src.startswith("rule:"):
            rid = src.split(":", 1)[1]
            rule = self.grounder.engine.rule_by_id.get(rid)
            if rule is not None:
                parts.append(_flatten(rule.params))
            parts += ledger.observed.get(f"lookup:{rid}", [])
            # only this rule's own lines from the rule-engine output, not every rule's numbers
            parts += [line for t in ledger.observed.get("check_proposal", []) + ledger.observed.get("task", [])
                      for line in t.splitlines() if f"rule:{rid}" in line]
        elif src.startswith("scenario:"):
            parts.append(self._scenario_value(src.split(":", 1)[1]))
        return "\n".join(p for p in parts if p)

    def _scenario_value(self, ref: str) -> str:
        field_name = ref.split(".")[0].split("[")[0]
        value = getattr(self.scenario, field_name, None)
        if hasattr(value, "model_dump_json"):
            return value.model_dump_json()
        if isinstance(value, list):
            return "[" + ", ".join(v.model_dump_json() if hasattr(v, "model_dump_json") else str(v) for v in value) + "]"
        return str(value)

    def _everything(self, ledger: Ledger) -> str:
        return "\n".join(t for texts in ledger.observed.values() for t in texts) + "\n" + \
            self.scenario.model_dump_json(exclude={"source"})

    # ── trust ──

    def trust(self, e: Evidence, ledger: Ledger) -> str:
        if not e.grounded:
            return "low"
        src = e.source.strip()
        if src == "check_proposal":
            return "high"
        kind, _, ref = src.partition(":")
        engine = self.grounder.engine
        if kind == "rule":
            rule = engine.rule_by_id.get(ref)
            passage = engine.passage_by_id.get(rule.source) if rule and rule.source else None
            return "high" if passage is not None and passage.kind in ("regulation", "standard") else "medium"
        if kind == "passage":
            p = engine.passage_by_id.get(ref)
            return "high" if p is not None and p.kind in ("regulation", "standard", "statistic") else "medium"
        if kind == "metric":
            ns = ledger.metric_samples.get(ref, [])
            return "high" if ns and max(ns) >= 100 else "medium"
        if kind == "code":
            return "high"
        if kind == "scenario":
            synth = self.scenario.synthetic_fields
            synthetic = ref.split(".")[0] in synth or any(f.startswith("everything") for f in synth)
            return "low" if synthetic else "medium"
        return "low"

    def stamp_trust(self, evidence: list[Evidence], ledger: Ledger) -> list[Evidence]:
        return [e.model_copy(update={"trust": self.trust(e, ledger)}) for e in evidence]


def _v(code: str, kind: str, where: str, evidence_id: int | None, message: str) -> GuardrailViolation:
    return GuardrailViolation(code=code, kind=kind, where=where, evidence_id=evidence_id, message=message)


def _fmt(ns: list[float]) -> str:
    return ", ".join(f"{n:g}" for n in ns)


def _clip(s: str, n: int = 90) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _flatten(obj) -> str:
    if isinstance(obj, dict):
        return " ".join(f"{k} {_flatten(v)}" for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten(v) for v in obj)
    return str(obj)


def holders_of(answer) -> list:
    return [answer] if isinstance(answer, Proposal) else [answer, *([answer.counter] if answer.counter else [])]


__all__ = ["Guardrails", "MIN_SAMPLE", "numbers", "sentences", "holders_of", "AgentResponse"]
