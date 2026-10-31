"""Command line entry point.

  atc run scenarios/sample_weather.json [--mock] [--out trace.json]
  atc from-dot data/flights.csv --row 3 [--mock] [--out trace.json]
  atc batch data/flights.csv --n 50 [--mock] [--out results.jsonl]

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


def _run(s: Scenario, args) -> NegotiationTrace:
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


def cmd_batch(args) -> None:
    agents = make_agents(mock=args.mock, model=args.model)
    out = Path(args.out).open("w") if args.out else None
    stats = {"consensus": 0, "fallback": 0, "no_legal_option": 0, "vetoes": 0, "turns": 0}
    for row in data.qualifying_rows(Path(args.csv), limit=args.n):
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

    c = sub.add_parser("batch", parents=[common], help="run the first N qualifying rows and report convergence")
    c.add_argument("csv")
    c.add_argument("--n", type=int, default=20)
    c.set_defaults(fn=cmd_batch)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
