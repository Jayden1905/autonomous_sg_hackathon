"""Elicitation: the build stage that asks people what the documents could not say.

Three pure steps, same shape as ACM's knowledge_review (compute → decide → apply):

  gaps(model)            what the model assumed without a source: synthetic types, defaulted
                         parameters, concepts no passage describes, unsourced metrics/rules
  questions(model)       one Question per gap, per role, with the current assumption spelled out
  apply_answers(model)   fold confirmed answers into the model as first-class elements with
                         source=operator: a passage quoting the operator, and a rule / metric /
                         concept update that cites it. Last confirmed answer per question wins.

Nothing here calls an LLM. `interpret()` is the one place a model *may* help (turn a sentence
into the structured fields), and it is a proposal the operator confirms, never applied blind.

Agents cannot loosen a regulatory hard rule through an answer: an operator can tighten
thresholds, add rules, set costs, correct synthetic defaults and add vocabulary, but
`protected_rules()` lists the ones whose hard parameters only a regulation can change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .model import (
    Answer, Concept, Elicitation, Evidence, KnowledgePassage, Metric, Operator, Question, Rule,
    SemanticModel, VocabTerm,
)

PROTECTED_RULE_IDS = {"atc.wake_separation", "pilot.final_reserve_fuel", "atc.runway_open",
                      "atc.taxiway_clear"}  # regulatory / physical: operators may not weaken


def protected_rules() -> set[str]:
    return set(PROTECTED_RULE_IDS)


# ─── 1. gaps ─────────────────────────────────────────────────────────────────────────────────────

def gaps(m: SemanticModel) -> dict[str, list[Any]]:
    linked = {(k.target_kind, k.target) for k in m.knowledge_links}
    passages = {p.id for p in m.passages}
    out: dict[str, list[Any]] = {
        "synthetic_type": [t for t in m.entity_types if t.synthetic],
        "default_param": [r for r in m.rules if r.kind != "protocol" and any(
            k.startswith("default") or k.startswith("cost") or (k == "value" and r.hard is False)
            for k in r.params)],
        "undescribed_concept": [c for c in m.concepts if not c.abstract and ("concept", c.name) not in linked],
        "unsourced_metric": [mt for mt in m.metrics if not mt.evidence and ("metric", mt.name) not in linked],
        "unsourced_rule": [r for r in m.rules if r.kind != "protocol" and (not r.source or r.source not in passages)],
    }
    return out


# ─── 2. questions ────────────────────────────────────────────────────────────────────────────────

_SYNTH_Q = {
    "Runway": ("How many runways does {airport} actually run for arrivals during a weather event, which ones, "
               "and which exit taxiway is the usual bottleneck?",
               "The generator invents two parallel runways and closes or blocks one at random."),
    "Gate": ("How reliable is the gate board? When a gate shows free at time T, how late is it typically "
             "actually free, and which gates are the chronic offenders?",
             "The generator gives each gate a clean free window; the engine trusts it exactly."),
    "GroundCrew": ("When does a ramp crew's shift actually end relative to the roster, and how much overtime "
                   "will they absorb before someone has to be called?",
                   "The generator sets shift end 30–90 min after earliest arrival; any minute past it is costed."),
    "Connection": ("For this airline at {airport}, what is the real minimum connect time you'd protect, and "
                   "which connections do you hold for regardless (last flight of the day, international)?",
                   "The model uses 35 min for everyone and treats every passenger the same."),
    "Turnaround": ("What turnaround does your operation plan for this fleet at {airport}, and what is the "
                   "shortest you'd accept under disruption?",
                   "The model uses 45 min flat, from Airbus's A320 figure."),
}


def questions(m: SemanticModel) -> list[Question]:
    g = gaps(m)
    airport = "the hub"
    qs: list[Question] = []

    for t in g["synthetic_type"]:
        text, why = _SYNTH_Q.get(t.name, (f"What does {t.name} look like in your operation?", "Synthetic in every scenario."))
        qs.append(Question(id=f"q.{t.domain}.type.{t.name.lower()}", role=t.domain, kind="synthetic_type",
                           target_kind="type", target=t.name, text=text.format(airport=airport), why=why,
                           priority=1 if t.name in ("Runway", "Gate") else 2))

    for r in g["default_param"]:
        params = {k: v for k, v in r.params.items() if k != "derivation"}
        qs.append(Question(
            id=f"q.{r.domain}.param.{r.id.split('.', 1)[1]}", role=r.domain, kind="default_param",
            target_kind="rule", target=r.id,
            text=f"Rule {r.id}: {r.text} Is {params} right for your operation? What would you use, and should it be "
                 f"{'a hard limit' if r.hard is False else 'a cost'} instead?",
            why=f"Current source: {r.source or 'none'}; these are typical values, not yours.",
            priority=2))

    for c in g["undescribed_concept"]:
        qs.append(Question(
            id=f"q.{c.domain}.concept.{c.name.lower()}", role=c.domain, kind="undescribed_concept",
            target_kind="concept", target=c.name,
            text=f"The model defines {c.name} as: \"{c.definition}\" Is that how you'd put it? What do you call it, "
                 f"and what does it leave out?",
            why="No document passage describes this concept; the definition is the model author's.",
            priority=3))

    for mt in g["unsourced_metric"]:
        qs.append(Question(
            id=f"q.{mt.domain}.metric.{mt.name}", role=mt.domain, kind="unsourced_metric",
            target_kind="metric", target=mt.name,
            text=f"Metric {mt.name} ({mt.unit or 'n/a'}): {(mt.description or mt.formula).rstrip('.')}. "
                 f"Is this the number you watch, and at what value does it start to worry you?",
            why="Formula is the model author's; no operator has confirmed it matters or where the thresholds sit.",
            priority=2))

    for r in g["unsourced_rule"]:
        qs.append(Question(
            id=f"q.{r.domain}.rule.{r.id.split('.', 1)[1]}", role=r.domain, kind="unsourced_rule",
            target_kind="rule", target=r.id,
            text=f"Rule {r.id}: {r.text} Where does this come from in your operation, and is it right?",
            why="No source passage.", priority=2))

    # One open question per role, because the gap list only knows what the model already names.
    for role, text in (
        ("atc", "What do you know about sequencing arrivals in a weather event here that no manual says? "
                "Which heuristics do you actually use when the rate is cut?"),
        ("pilot", "When you're holding with fuel getting tight, what decides it for you: divert now, or wait for the slot? "
                  "What do you need ATC and ground to tell you?"),
        ("ground", "What makes a recovery plan unworkable on the ramp even when the board says it fits? "
                   "What do controllers and crews not see?"),
    ):
        qs.append(Question(id=f"q.{role}.open", role=role, kind="open", target_kind="none", target="",
                           text=text, why="The model can only ask about what it already names.", priority=1))

    order = {1: 0, 2: 1, 3: 2}
    qs.sort(key=lambda q: (order[q.priority], q.role, q.id))
    return qs


# ─── 3. apply ────────────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def latest_confirmed(e: Elicitation) -> dict[str, Answer]:
    """Last confirmed answer per question wins. Skips and not-applicable count as decisions, not knowledge."""
    out: dict[str, Answer] = {}
    for a in e.answers:
        if a.confirmed and a.action == "answer" and a.structured is not None:
            out[a.question_id] = a
    return out


EXAMPLE_LABEL = "operator knowledge (worked example)"
INTERVIEW_LABEL = "operator knowledge (interview)"


def passage_label(op: Operator | None) -> str:
    """What the citation shows. Downstream (guardrails, FE) uses doc/title as the label, so it lives here."""
    return INTERVIEW_LABEL if op and op.status == "interviewed" else EXAMPLE_LABEL


def _passage_for(a: Answer, q: Question, op: Operator | None) -> KnowledgePassage:
    who = f"{op.name}, {op.title}" if op and op.title else (op.name if op else a.by)
    return KnowledgePassage(
        id=f"operator:{a.by}:{q.id.split('.', 1)[1]}",
        doc=f"{passage_label(op)}: {who}",
        title=q.text[:80].rstrip(".?") + ("…" if len(q.text) > 80 else ""),
        text=a.text, kind="operator", retrieved=a.at[:10], domain=q.role, by=a.by,
    )


def apply_answers(m: SemanticModel) -> list[str]:
    """Fold confirmed answers into the model. Returns a log of what changed. Idempotent."""
    e = m.elicitation
    if not e.answers:
        return []
    ops = {o.id: o for o in e.operators}
    qs = {q.id: q for q in e.questions} or {q.id: q for q in questions(m)}
    have_passages = {p.id for p in m.passages}
    rules = {r.id: r for r in m.rules}
    metrics = {mt.name: mt for mt in m.metrics}
    concepts = {c.name: c for c in m.concepts}
    log: list[str] = []

    for qid, a in latest_confirmed(e).items():
        q = qs.get(qid)
        if q is None:
            continue
        p = _passage_for(a, q, ops.get(a.by))
        if p.id not in have_passages:
            m.passages.append(p); have_passages.add(p.id)
        s = a.structured or {}
        ev = Evidence(by="operator", what=f"{a.by} on {a.at[:10]}: {a.text[:80]}", ref=p.id)

        # Rule parameter / hardness updates (never weakening a protected hard rule)
        if q.target_kind == "rule" and q.target in rules and "params" in s:
            r = rules[q.target]
            if r.id in PROTECTED_RULE_IDS and r.hard:
                log.append(f"REFUSED {r.id}: protected regulatory rule; operator answer kept as passage only")
            else:
                r.params.update(s["params"])
                if "hard" in s and r.id not in PROTECTED_RULE_IDS:
                    r.hard = bool(s["hard"])
                r.evidence.append(ev)
                if "text" in s:
                    r.text = s["text"]
                log.append(f"rule {r.id}: params <- {s['params']}" + (f", hard={r.hard}" if "hard" in s else ""))

        # A brand-new rule the operator stated (local rule)
        if "new_rule" in s:
            nr = dict(s["new_rule"])
            rid = nr.get("id") or f"operator.{q.role}.{q.id.split('.')[-1]}"
            if rid not in rules:
                op = ops.get(a.by)
                label = passage_label(op)
                text = nr["text"] if label.lower() in nr["text"].lower() else f"{nr['text']} [{label}]"
                r = Rule(id=rid, kind=nr.get("kind", "threshold"), text=text, domain=q.role,
                         hard=nr.get("hard", False), subjects=nr.get("subjects", [q.target] if q.target else []),
                         params=nr.get("params", {}), source=p.id, enforced_by=nr.get("enforced_by"),
                         evidence=[ev], status="confirmed")
                m.rules.append(r); rules[rid] = r
                log.append(f"new rule {rid} ({'hard' if r.hard else 'soft'}): {r.text}")

        # Metric: thresholds / description
        if q.target_kind == "metric" and q.target in metrics:
            mt = metrics[q.target]
            for k in ("range_lo", "range_hi", "description"):
                if k in s:
                    setattr(mt, k, s[k])
            mt.evidence.append(ev)
            log.append(f"metric {mt.name}: " + ", ".join(f"{k}={s[k]}" for k in ("range_lo", "range_hi") if k in s))

        # Concept: operator's own definition and words
        if q.target_kind == "concept" and q.target in concepts:
            c = concepts[q.target]
            if "definition" in s:
                c.definition = s["definition"]
            for al in s.get("aliases", []):
                if al not in c.aliases:
                    c.aliases.append(al)
            log.append(f"concept {c.name}: definition/aliases from operator")

        # Vocabulary, from any answer
        for v in s.get("vocabulary", []):
            m.vocabulary.append(VocabTerm(term=v["term"], target_kind=v["target_kind"], target=v["target"],
                                          source="operator"))
            log.append(f"vocab {v['term']!r} -> {v['target_kind']}:{v['target']}")

        # Knowledge link from the passage to the target, so the viewer and briefs connect them
        if q.target_kind != "none" and q.target:
            from .model import KnowledgeLink
            tk = {"type": "type", "rule": "rule", "concept": "concept", "metric": "metric"}[q.target_kind]
            if not any(k.passage_id == p.id and k.target == q.target for k in m.knowledge_links):
                m.knowledge_links.append(KnowledgeLink(passage_id=p.id, target_kind=tk, target=q.target, kind="describes"))
    return log


# ─── coverage ────────────────────────────────────────────────────────────────────────────────────

def coverage(m: SemanticModel) -> dict[str, Any]:
    """How much of what the documents could not say has a person said? Per role and overall."""
    qs = m.elicitation.questions or questions(m)
    decided = {a.question_id for a in m.elicitation.answers if a.confirmed or a.action in ("skip", "not_applicable")}
    answered = set(latest_confirmed(m.elicitation))
    by_role: dict[str, dict[str, int]] = {}
    for q in qs:
        d = by_role.setdefault(q.role, {"questions": 0, "answered": 0, "decided": 0, "p1_open": 0})
        d["questions"] += 1
        d["answered"] += q.id in answered
        d["decided"] += q.id in decided
        d["p1_open"] += (q.priority == 1 and q.id not in decided)
    total = sum(d["questions"] for d in by_role.values())
    ans = sum(d["answered"] for d in by_role.values())
    p1 = sum(d["p1_open"] for d in by_role.values())
    status = "red" if p1 else "amber" if ans < total else "green"
    return {"status": status, "questions": total, "answered": ans, "priority1_open": p1, "by_role": by_role,
            "operators": [o.model_dump() for o in m.elicitation.operators]}


# ─── ledger I/O ──────────────────────────────────────────────────────────────────────────────────

def load_ledger(path: Path) -> Elicitation:
    return Elicitation.model_validate(yaml.safe_load(path.read_text()) or {}) if path.exists() else Elicitation()


def save_ledger(e: Elicitation, path: Path) -> None:
    path.write_text(yaml.safe_dump(e.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True,
                                   width=110))


def record_answer(path: Path, m: SemanticModel, question_id: str, by: str, text: str, *,
                  structured: dict[str, Any] | None = None, confirmed: bool = False,
                  action: str = "answer", via: str = "cli") -> Answer:
    """Append one answer to the ledger. Regenerates the question list if the ledger has none."""
    e = load_ledger(path)
    if not e.questions:
        e.questions = questions(m)
    if question_id not in {q.id for q in e.questions}:
        raise KeyError(f"unknown question {question_id!r}; run `atc semantic elicit` to list them")
    if by not in {o.id for o in e.operators}:
        raise KeyError(f"unknown operator {by!r}; add them to elicitation.yaml operators first")
    a = Answer(question_id=question_id, by=by, at=_now(), text=text, action=action,  # type: ignore[arg-type]
               structured=structured, confirmed=confirmed, via=via)  # type: ignore[arg-type]
    e.answers.append(a)
    save_ledger(e, path)
    return a


def init_ledger(path: Path, m: SemanticModel, operators: list[Operator]) -> Elicitation:
    """Create elicitation.yaml with the generated questions and the named operators, no answers yet."""
    e = Elicitation(operators=operators, questions=questions(m), answers=[])
    save_ledger(e, path)
    return e
