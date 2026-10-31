"""Read-only SQL over the organisers' CSVs. Agents never send SQL here directly:
metrics.py compiles it from the semantic model for the `query_metric` tool.

DuckDB, in process: the three CSVs are loaded once into memory tables, then
the connection is locked so a query can read those tables and nothing else.
No file access (`read_csv('/etc/passwd')`, COPY, ATTACH all fail), no config
changes, one SELECT per call, a row cap and a timeout.

The data is a trimmed DOT 2015 set: every row is already a disrupted flight
(WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20), so averages describe
disrupted flights, not all flights. `overview()` says so to the agents.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TABLES = ("flights", "airports", "airlines")
MAX_ROWS = 50
TIMEOUT_S = 10.0

DATASET_NOTE = (
    "Dataset caveat: flights holds only disrupted 2015 US domestic flights "
    "(WEATHER_DELAY > 15 or LATE_AIRCRAFT_DELAY > 20); October is missing. "
    "Statistics describe disrupted flights, not all traffic. Times are HHMM strings "
    "(e.g. '1740'); delays are minutes."
)


class SqlError(ValueError):
    """The query was rejected or failed. The message is safe to show the agent."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool

    def as_text(self) -> str:
        if not self.rows:
            return "(0 rows)"
        lines = [" | ".join(self.columns)]
        lines += [" | ".join("NULL" if v is None else str(v) for v in r) for r in self.rows]
        if self.truncated:
            lines.append(f"... truncated at {len(self.rows)} rows; aggregate or add LIMIT")
        return "\n".join(lines)


class SqlEngine:
    def __init__(self, data_dir: Path = DATA_DIR):
        missing = [t for t in TABLES if not (data_dir / f"{t}.csv").exists()]
        if missing:
            raise FileNotFoundError(f"missing {', '.join(missing)}.csv under {data_dir}; run `make data`")
        self._con = duckdb.connect()
        for t in TABLES:
            self._con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto(?)", [str(data_dir / f"{t}.csv")])
        self._con.execute("SET enable_external_access = false")
        self._con.execute("SET lock_configuration = true")
        self._lock = threading.Lock()
        self._overview = self._build_overview()

    def overview(self) -> str:
        return self._overview

    def query(self, sql: str, max_rows: int = MAX_ROWS, params: list | None = None) -> QueryResult:
        try:
            stmts = duckdb.extract_statements(sql)
        except duckdb.Error as e:
            raise SqlError(f"could not parse SQL: {e}") from e
        if len(stmts) != 1:
            raise SqlError(f"send exactly one statement, got {len(stmts)}")
        if stmts[0].type != duckdb.StatementType.SELECT:
            raise SqlError(f"only SELECT is allowed, got {stmts[0].type.name}")

        with self._lock:  # one DuckDB connection; cursors share it, interrupt() targets it
            cur = self._con.cursor()
            timer = threading.Timer(TIMEOUT_S, cur.interrupt)
            timer.start()
            try:
                cur.execute(sql, params or [])
                rows = cur.fetchmany(max_rows + 1)
                columns = [d[0] for d in cur.description]
            except duckdb.InterruptException as e:
                raise SqlError(f"query exceeded {TIMEOUT_S:g}s; aggregate more or filter first") from e
            except duckdb.Error as e:
                raise SqlError(str(e).splitlines()[0]) from e
            finally:
                timer.cancel()
                cur.close()
        return QueryResult(columns=columns, rows=[[_plain(v) for v in r] for r in rows[:max_rows]],
                           truncated=len(rows) > max_rows)

    def _build_overview(self) -> str:
        parts = [DATASET_NOTE]
        for t in TABLES:
            n = self._con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            cols = ", ".join(f"{c} {ty}" for c, ty, *_ in self._con.execute(f"DESCRIBE {t}").fetchall())
            parts.append(f"{t} ({n} rows): {cols}")
        return "\n".join(parts)


def _plain(v):
    """DuckDB returns Decimal/date objects; the agent and the JSON trace want plain values."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


_engine: SqlEngine | None = None
_engine_lock = threading.Lock()


def default_engine() -> SqlEngine:
    """Shared engine, built on first use (about 1 s to load the CSVs)."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SqlEngine()
        return _engine


def dataset_available(data_dir: Path = DATA_DIR) -> bool:
    return all((data_dir / f"{t}.csv").exists() for t in TABLES)
