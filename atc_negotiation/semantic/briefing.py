"""Render one agent's slice of the semantic model as the grounding section of its system prompt.

What goes in, in this order, so the prompt cache prefix stays stable across turns:
  1. the concepts this agent owns, with definitions
  2. the metrics it reasons about, with units and formulas
  3. the rules it must respect, hard/soft, with parameters and a [passage-id] citation
  4. code sets it will see values from (delay causes, wake categories)
  5. the cited passages, verbatim excerpts, so the agent quotes rather than recalls
  6. what in the scenario is synthetic, so it does not over-trust those numbers

Nothing here is per-scenario. Scenario data goes in the user message.
"""

from __future__ import annotations

from .engine import SemanticEngine
from .model import Domain, Rule

EXCERPT = 420


def _fmt_params(r: Rule) -> str:
    """Inline parameters. `derivation` is prose and goes on its own line via _derivation()."""
    params = {k: v for k, v in r.params.items() if k != "derivation"}
    if not params:
        return ""
    if "table" in params and isinstance(params["table"], dict):
        rows = ", ".join(f"{k}: {v}" for k, v in params["table"].items())
        unit = params.get("unit", "")
        extra = {k: v for k, v in params.items() if k not in ("table", "unit")}
        tail = "; " + ", ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
        return f" [{rows}{(' ' + unit) if unit else ''}{tail}]"
    return " [" + ", ".join(f"{k}={v}" for k, v in params.items()) + "]"


def _derivation(r: Rule) -> str:
    d = r.params.get("derivation")
    return f"\n    derivation: {' '.join(str(d).split())}" if d else ""


def render_brief(engine: SemanticEngine, domain: Domain) -> str:
    m = engine.model
    out: list[str] = [f"## Grounding for the {domain.upper()} agent (semantic model v{m.version}, {m.project.name})", ""]

    out.append("### Concepts you own")
    for c in engine.concepts_for(domain, include_shared=False):
        alias = f" (also: {', '.join(c.aliases)})" if c.aliases else ""
        out.append(f"- {c.name}{alias}: {c.definition}")
    shared = [c.name for c in engine.concepts_for("shared", include_shared=False)]
    if shared:
        out.append(f"- Shared with the other agents: {', '.join(shared)}")
    out.append("")

    out.append("### Metrics")
    for mt in engine.metrics_for(domain):
        rng = ""
        if mt.range_lo is not None or mt.range_hi is not None:
            rng = f" range {mt.range_lo if mt.range_lo is not None else '-inf'}..{mt.range_hi if mt.range_hi is not None else 'inf'}"
        out.append(f"- {mt.name} ({mt.unit or 'n/a'}){rng}: {mt.description}"
                   + (f" Formula: {mt.formula}" if mt.formula else ""))
    out.append("")

    out.append("### Rules you must respect (the rule engine enforces these; you cannot waive them)")
    hard = [r for r in engine.rules_for(domain) if r.hard is True]
    soft = [r for r in engine.rules_for(domain) if r.hard is False]
    proto = [r for r in engine.rules_for(domain) if r.kind == "protocol"]
    for label, rs in (("HARD", hard), ("SOFT (cost only)", soft)):
        if rs:
            out.append(f"{label}:")
            for r in rs:
                cite = f" [{r.source}]" if r.source else ""
                out.append(f"- {r.id}: {' '.join(r.text.split())}{_fmt_params(r)}{cite}{_derivation(r)}")
    if proto:
        out.append("PROTOCOL:")
        for r in proto:
            out.append(f"- {r.id}: {r.text}" + (f" [{r.source}]" if r.source else ""))
    out.append("")

    cs_list = [cs for cs in m.code_sets if cs.name in {s for r in engine.rules_for(domain) for s in r.subjects}
               or domain == "shared"]
    # Always include code sets whose column lives on a type this domain owns.
    owned = {t.name for t in engine.types_for(domain, include_shared=True)}
    for cs in m.code_sets:
        if cs not in cs_list and cs.column and cs.column.split(".")[0] in owned:
            cs_list.append(cs)
    if cs_list:
        out.append("### Coded values you will see")
        for cs in cs_list:
            out.append(f"- {cs.name}" + (f" ({cs.column})" if cs.column else "") + f": {cs.description}")
            for code, e in cs.entries.items():
                out.append(f"    {code} = {e.label}" + (f": {e.definition}" if e.definition else ""))
        out.append("")

    cited = {r.source for r in engine.rules_for(domain) if r.source}
    cited |= {cs.source for cs in cs_list if cs.source}
    cited |= {p.id for p in engine.passages_for(domain, include_shared=False)}
    if cited:
        out.append("### Source passages (quote these; do not rely on memory for numbers)")
        for pid in sorted(cited):
            p = engine.passage_by_id.get(pid)
            if p is None:
                continue
            text = p.text.strip().replace("\n", " ")
            if len(text) > EXCERPT:
                text = text[:EXCERPT].rsplit(" ", 1)[0] + " …"
            out.append(f"[{p.id}] {p.doc}, {p.title}: \"{text}\"")
        out.append("")

    # Operator knowledge: what the people who do this job told us, in their words, scoped to this role.
    op_passages = [p for p in m.passages if p.kind == "operator" and p.domain in (domain, "shared")]
    op_rules = [r for r in engine.rules_for(domain) if r.source.startswith("operator:")]
    op_evidence_rules = [r for r in engine.rules_for(domain)
                         if any(e.by == "operator" for e in r.evidence) and r not in op_rules]
    if op_passages or op_rules or op_evidence_rules:
        ops = {o.id: o for o in m.elicitation.operators}
        any_example = any(o.status == "example" for o in ops.values())
        out.append("### Operator knowledge (from the people who run this operation; cite like any other source)")
        if any_example:
            out.append("Items marked 'worked example' are illustrative personas written to exercise this stage, "
                       "not real interviews. Treat them as plausible local practice and say so when you rely on them.")
        for r in op_rules:
            out.append(f"- {r.id} ({'HARD' if r.hard else 'soft'}): {' '.join(r.text.split())}{_fmt_params(r)} [{r.source}]")
        for r in op_evidence_rules:
            refs = ", ".join(e.ref for e in r.evidence if e.by == "operator")
            out.append(f"- {r.id} parameters set by operator: {_fmt_params(r).strip()} [{refs}]")
        for p in op_passages:
            o = ops.get(p.by)
            who = f"{o.name}, {o.title}" if o and o.title else p.by
            text = " ".join(p.text.split())
            if len(text) > EXCERPT:
                text = text[:EXCERPT].rsplit(" ", 1)[0] + " …"
            out.append(f"[{p.id}] {who}: \"{text}\"")
        out.append("")

    synth = engine.synthetic_types()
    if synth:
        out.append("### Synthetic in every scenario (illustrative, not from the DOT data)")
        out.append(", ".join(f"{t.name} ({t.scenario_field})" if t.scenario_field else t.name for t in synth))
        out.append("Treat their values as the operating picture for this exercise, and say so if asked.")
    return "\n".join(out).rstrip() + "\n"
