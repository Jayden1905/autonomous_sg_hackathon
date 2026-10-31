"""Command line entry point.

  atc run scenarios/sample_weather.json [--mock] [--out trace.json]
  atc from-dot data/flights.csv --row 3 [--mock] [--out trace.json]
  atc batch data/flights.csv --n 50 [--mock] [--out results.jsonl]
  atc batch data/flights.csv --n 20 --sample --seed 2026   spread across months and airports
  atc impact results.jsonl      negotiated vs recorded 2015 delay, per batch (measured + labelled estimates)
  atc semantic profile          regenerate semantic/schema.yaml from data/*.csv
  atc semantic check            validate model.yaml + schema.yaml cross-references
  atc semantic brief atc        print the grounding brief one agent gets
  atc semantic lookup "FRF"     resolve a term the way the lookup_concept tool does
  atc semantic elicit [--role]  the questions the documents left open, and answers so far
  atc semantic answer Q --by OP --text "..." [--structured JSON --confirm]
  atc semantic coverage         how much operator knowledge is in (red / amber / green)

Options --mock / --model / --max-turns / --out go after the subcommand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import data
from .agents import DEFAULT_MODEL, make_agents
from .orchestrator import negotiate
from .schemas import NegotiationTrace, Scenario


def _print_trace(tr: NegotiationTrace) -> None:
    print(f"\n=== {tr.scenario_id}  model={tr.model}  {tr.duration_s:.1f}s ===")
    for t in tr.turns:
        ev = t.evaluation
        print(f"\nTurn {t.turn}: {t.proposer} proposes t+{t.proposal.arrival_min} min, "
              f"rwy {t.proposal.runway}, gate {t.proposal.gate}")
        print(f"  rationale: {t.proposal.rationale}")
        print(f"  rule engine: {'FEASIBLE' if ev.feasible else 'INFEASIBLE'} cost={ev.cost:g}")
        for r in ev.hard_failures:
            print(f"    FAIL {r.domain}/{r.rule}: {r.detail}")
        for name, resp in t.responses.items():
            line = f"  {name}: {resp.verdict.value}"
            if resp.counter:
                c = resp.counter
                line += f" -> t+{c.arrival_min}, rwy {c.runway}, gate {c.gate}"
            print(line)
            for o in resp.objections:
                print(f"      - {o}")
        for v in t.vetoed_accepts:
            print(f"  ! {v} accepted an infeasible proposal; rule engine vetoed")
    f = tr.final
    if tr.outcome == "no_legal_option":
        print("\nOutcome: NO LEGAL OPTION. Human decision required. Last attempt and why it fails:")
        print(f"  t+{f.arrival_min} min, rwy {f.runway}, gate {f.gate}")
        for r in tr.final_evaluation.hard_failures:
            print(f"    FAIL {r.domain}/{r.rule}: {r.detail}")
    else:
        print(f"\nOutcome: {tr.outcome.upper()}  -> t+{f.arrival_min} min, rwy {f.runway}, gate {f.gate} "
              f"(cost {tr.final_evaluation.cost:g})")
    if tr.fallback_reason:
        print(f"  reason: {tr.fallback_reason}")


def _preflight_credentials(mock: bool) -> None:
    """Fail with one clear line instead of an SDK stack trace when no key is configured."""
    import os
    if mock or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return
    sys.exit("no Anthropic credentials: set ANTHROPIC_API_KEY in .env (cp .env.example .env), "
             "or add --mock to run scripted agents without an API key")


def _run(s: Scenario, args) -> NegotiationTrace:
    _preflight_credentials(args.mock)
    agents = make_agents(mock=args.mock, model=args.model)
    tr = negotiate(s, agents, max_turns=args.max_turns)
    _print_trace(tr)
    if args.out:
        Path(args.out).write_text(tr.model_dump_json(indent=2))
        print(f"\ntrace written to {args.out}")
    return tr


def cmd_run(args) -> None:
    s = Scenario.model_validate_json(Path(args.scenario).read_text())
    _run(s, args)


def cmd_from_dot(args) -> None:
    rows = list(data.qualifying_rows(Path(args.csv), limit=args.row + 1))
    if len(rows) <= args.row:
        sys.exit(f"only {len(rows)} qualifying rows found")
    _run(data.scenario_from_row(rows[args.row]), args)


def _sample_rows(csv: Path, n: int, seed: int) -> list[dict]:
    """Spread the sample across months and destination airports instead of taking the first N rows
    (which are all 1 January). Round-robin over (month, destination) buckets in a seeded order, so the
    draw is reproducible and no single hub or day dominates."""
    import random
    from collections import defaultdict
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in data.qualifying_rows(csv):
        buckets[(row["MONTH"], row["DESTINATION_AIRPORT"])].append(row)
    rng = random.Random(seed)
    keys = sorted(buckets)
    rng.shuffle(keys)
    for k in keys:
        rng.shuffle(buckets[k])
    picked: list[dict] = []
    while len(picked) < n and any(buckets.values()):
        for k in keys:
            if buckets[k] and len(picked) < n:
                picked.append(buckets[k].pop())
    return picked


def cmd_batch(args) -> None:
    _preflight_credentials(args.mock)
    agents = make_agents(mock=args.mock, model=args.model)
    out = Path(args.out).open("w") if args.out else None
    stats = {"consensus": 0, "fallback": 0, "no_legal_option": 0, "vetoes": 0, "turns": 0}
    if args.sample:
        rows = _sample_rows(Path(args.csv), args.n, args.seed)
        months = sorted({r["MONTH"] for r in rows}); dests = sorted({r["DESTINATION_AIRPORT"] for r in rows})
        print(f"sampled {len(rows)} rows (seed {args.seed}): months {months}, {len(dests)} destinations "
              f"{dests[:8]}{'…' if len(dests) > 8 else ''}\n")
    else:
        rows = data.qualifying_rows(Path(args.csv), limit=args.n)
    for row in rows:
        tr = negotiate(data.scenario_from_row(row), agents, max_turns=args.max_turns)
        stats[tr.outcome] += 1
        stats["turns"] += len(tr.turns)
        stats["vetoes"] += sum(len(t.vetoed_accepts) for t in tr.turns)
        print(f"{tr.scenario_id:>22}  {tr.outcome:<15} turns={len(tr.turns)} "
              f"final=t+{tr.final.arrival_min} cost={tr.final_evaluation.cost:g}")
        if out:
            out.write(tr.model_dump_json() + "\n")
    n = stats["consensus"] + stats["fallback"] + stats["no_legal_option"]
    if n:
        print(f"\n{n} scenarios: {stats['consensus']} consensus ({stats['consensus']/n:.0%}), "
              f"{stats['fallback']} fallback, {stats['no_legal_option']} no legal option, "
              f"{stats['turns']/n:.2f} turns avg, {stats['vetoes']} vetoed accepts")
    if out:
        out.close()


def cmd_semantic(args) -> None:
    from .semantic import brief_for, lookup
    from .semantic.model import SEMANTIC_DIR, SemanticModel

    if args.action == "profile":
        from .semantic.profiler import profile_dir, write_schema
        data_dir = Path(args.data_dir)
        if not any(data_dir.glob("*.csv")):
            sys.exit(f"no CSVs in {data_dir}; run `make data` first")
        tables = profile_dir(data_dir)
        write_schema(tables, SEMANTIC_DIR / "schema.yaml")
        for t in tables:
            print(f"  {t.name:<10} {t.rows:>8} rows  {len(t.columns):>2} cols  (profiled {t.profiled_rows})")
        print(f"wrote {SEMANTIC_DIR / 'schema.yaml'}")
    elif args.action == "check":
        m = SemanticModel.load()
        probs = m.validate_references()
        print(f"model v{m.version}: {len(m.tables)} tables, {len(m.concepts)} concepts, {len(m.entity_types)} types, "
              f"{len(m.relation_types)} relations, {len(m.metrics)} metrics, {len(m.rules)} rules, "
              f"{len(m.code_sets)} code sets, {len(m.passages)} passages, {len(m.knowledge_links)} links")
        for p in probs:
            print(f"  ! {p}")
        from . import rules as _rules
        unenforced = _rules.unenforced_hard_rules()
        for rid in unenforced:
            print(f"  ! hard rule {rid} is in the brief but no code enforces it")
        if probs or unenforced:
            sys.exit(f"{len(probs)} reference problem(s), {len(unenforced)} unenforced hard rule(s)")
        print("all references resolve; every hard rule has an enforcer")
    elif args.action == "brief":
        print(brief_for(args.role), end="")
    elif args.action == "lookup":
        print(lookup(args.term) or f"{args.term!r}: not in the semantic model")
    elif args.action == "elicit":
        from .semantic import elicit
        ledger = SEMANTIC_DIR / "elicitation.yaml"
        m = SemanticModel.load(apply_operator_knowledge=False)
        e = elicit.load_ledger(ledger)
        qs = e.questions or elicit.questions(m)
        decided = {a.question_id: a for a in e.answers}
        cov = elicit.coverage(SemanticModel.load())
        print(f"Elicitation coverage: {cov['status'].upper()}  {cov['answered']}/{cov['questions']} answered, "
              f"{cov['priority1_open']} priority-1 open")
        for role, d in cov["by_role"].items():
            print(f"  {role:<7} {d['answered']}/{d['questions']} answered, {d['p1_open']} p1 open")
        print()
        for q in qs:
            if args.role and q.role != args.role:
                continue
            mark = "✓" if q.id in decided and decided[q.id].confirmed else "·" if q.id in decided else " "
            print(f"[{mark}] P{q.priority} {q.id}  ({q.kind}, {q.role})")
            print(f"      {q.text}")
            if q.why:
                print(f"      currently: {q.why}")
            if q.id in decided:
                a = decided[q.id]
                print(f"      answered by {a.by} on {a.at[:10]}{' (confirmed)' if a.confirmed else ' (unconfirmed)'}: {a.text[:120]}")
            print()
    elif args.action == "answer":
        import json as _json
        from .semantic import elicit
        ledger = SEMANTIC_DIR / "elicitation.yaml"
        m = SemanticModel.load(apply_operator_knowledge=False)
        structured = _json.loads(args.structured) if args.structured else None
        a = elicit.record_answer(ledger, m, args.question_id, args.by, args.text,
                                 structured=structured, confirmed=bool(structured and args.confirm), via="cli")
        print(f"recorded {a.question_id} by {a.by} at {a.at}" + (" (confirmed, will apply on next load)" if a.confirmed
              else " (unconfirmed: add --structured ... --confirm to apply)"))
    elif args.action == "coverage":
        from .semantic import elicit
        cov = elicit.coverage(SemanticModel.load())
        import json as _json
        print(_json.dumps(cov, indent=1))
    elif args.action == "applied":
        from .semantic import elicit
        m = SemanticModel.load(apply_operator_knowledge=False)
        for line in elicit.apply_answers(m):
            print("  " + line)


def cmd_impact(args) -> None:
    from . import impact
    rep = impact.build(Path(args.traces), Path(args.csv))
    if not rep.rows:
        sys.exit("no traces matched rows in the CSV (were they produced by `atc batch` on this file?)")
    summary = rep.summary()
    print(impact.render(summary))
    if args.out:
        impact.write_json(summary, Path(args.out))
        print(f"\njson written to {args.out}")


def main(argv: list[str] | None = None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mock", action="store_true", help="scripted agents, no API calls")
    common.add_argument("--model", default=DEFAULT_MODEL)
    common.add_argument("--max-turns", type=int, default=3)
    common.add_argument("--out", help="write trace JSON (or JSONL for batch) here")

    p = argparse.ArgumentParser(prog="atc", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("run", parents=[common], help="negotiate one scenario file")
    a.add_argument("scenario")
    a.set_defaults(fn=cmd_run)

    b = sub.add_parser("from-dot", parents=[common], help="build a scenario from a DOT flights.csv row")
    b.add_argument("csv")
    b.add_argument("--row", type=int, default=0, help="index among qualifying rows")
    b.set_defaults(fn=cmd_from_dot)

    c = sub.add_parser("batch", parents=[common], help="run N qualifying rows and report convergence")
    c.add_argument("csv")
    c.add_argument("--n", type=int, default=20)
    c.add_argument("--sample", action="store_true",
                   help="spread the N rows across months and destination airports (seeded) instead of the first N in file order")
    c.add_argument("--seed", type=int, default=2026)
    c.set_defaults(fn=cmd_batch)

    i = sub.add_parser("impact", help="compare a batch's negotiated plans against the recorded 2015 outcomes")
    i.add_argument("traces", help="JSONL written by `atc batch --out`")
    i.add_argument("--csv", default="data/flights.csv")
    i.add_argument("--out", help="also write the summary JSON here")
    i.set_defaults(fn=cmd_impact)

    d = sub.add_parser("semantic", help="semantic model: profile | check | brief | lookup")
    ds = d.add_subparsers(dest="action", required=True)
    dp = ds.add_parser("profile", help="regenerate semantic/schema.yaml from CSVs")
    dp.add_argument("--data-dir", default="data")
    ds.add_parser("check", help="validate cross-references")
    db = ds.add_parser("brief", help="print one agent's grounding brief")
    db.add_argument("role", choices=["atc", "pilot", "ground"])
    dl = ds.add_parser("lookup", help="resolve a term")
    dl.add_argument("term")
    de = ds.add_parser("elicit", help="list what the documents could not say, per role, with answers so far")
    de.add_argument("--role", choices=["atc", "pilot", "ground"])
    da = ds.add_parser("answer", help="record an operator's answer to a question")
    da.add_argument("question_id")
    da.add_argument("--by", required=True, help="operator id from elicitation.yaml")
    da.add_argument("--text", required=True, help="their words, verbatim")
    da.add_argument("--structured", help="JSON: the typed reading (params / new_rule / range_lo / aliases / vocabulary)")
    da.add_argument("--confirm", action="store_true", help="operator has confirmed the structured reading")
    ds.add_parser("coverage", help="elicitation coverage as JSON")
    ds.add_parser("applied", help="show what operator answers changed in the model")
    d.set_defaults(fn=cmd_semantic)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
