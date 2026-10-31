"""Deterministic CSV profiling → the schema layer. No LLM. Same input, same output.

`atc semantic profile` writes semantic/schema.yaml. Hand edits there are overwritten.
"""

from __future__ import annotations

import csv
import itertools
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from .model import Column, Evidence, Table

SAMPLE_ROWS = 200_000  # flights.csv is 358k rows; this is plenty for shape and ranges
SAMPLES_KEPT = 6
ID_HINTS = ("_NUMBER", "_CODE", "TAIL", "IATA")
CLOCK_HINTS = ("SCHEDULED_DEPARTURE", "DEPARTURE_TIME", "WHEELS_OFF", "WHEELS_ON",
               "SCHEDULED_ARRIVAL", "ARRIVAL_TIME")  # HHMM integers, not durations


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def profile_table(path: Path, sample_rows: int = SAMPLE_ROWS) -> Table:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        names = reader.fieldnames or []
        rows = list(itertools.islice(reader, sample_rows))
        total = len(rows) + sum(1 for _ in reader)

    cols: list[Column] = []
    for name in names:
        vals = [r[name] for r in rows]
        non_null = [v for v in vals if v not in ("", None)]
        counts = Counter(non_null)
        nums = [_num(v) for v in non_null[:5000]]
        all_num = bool(non_null) and all(n is not None for n in nums)
        all_int = all_num and all(float(n).is_integer() for n in nums if n is not None)
        kind = "empty" if not non_null else "int" if all_int else "float" if all_num else "str"
        mn = mx = None
        if all_num and non_null:
            full = [_num(v) for v in non_null]
            mn, mx = min(x for x in full if x is not None), max(x for x in full if x is not None)
        cols.append(Column(
            name=name, type=kind,
            nulls=round(1 - len(non_null) / len(vals), 4) if vals else 1.0,
            distinct=len(counts),
            samples=[k for k, _ in counts.most_common(SAMPLES_KEPT)],
            min=mn, max=mx,
            is_id=any(h in name.upper() for h in ID_HINTS),
            is_time=name.upper() in CLOCK_HINTS,
        ))

    return Table(
        name=path.stem, path=str(path), rows=total, columns=cols, profiled_rows=len(rows),
        evidence=[Evidence(by="profiler", what=f"profiled {len(rows)} of {total} rows on {date.today()}",
                           ref=str(path))],
    )


def profile_dir(data_dir: Path) -> list[Table]:
    return [profile_table(p) for p in sorted(data_dir.glob("*.csv"))]


def write_schema(tables: list[Table], out: Path) -> None:
    payload = {"_generated": "by atc_negotiation.semantic.profiler; do not edit",
               "tables": [t.model_dump(mode="json", exclude_none=True) for t in tables]}
    out.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
