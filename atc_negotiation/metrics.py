"""Grounded data retrieval: agents ask for a semantic-model metric, never write SQL.

The semantic model (semantic/model.yaml) names what can be measured. A metric
is queryable when its `inputs` is exactly one `flights.<COLUMN>` column and
it has no `formula` (formulas like on_time are derived, not a column); the
SQL is compiled here from the model, so the agent can only ask questions the
model defines, and every answer comes back labelled with the metric's
definition, unit and source:

    query_metric(metric="weather_delay_min",
                 filters={"destination": "ORD", "month": 6, "arrival_hour": [17, 19]},
                 group_by=[])
      -> SELECT count(*), avg(WEATHER_DELAY), median(...), quantile_cont(..., 0.9)
         FROM flights WHERE DESTINATION_AIRPORT = ? AND MONTH = ? AND ...

Dimensions are the Flight entity's columns (bound in the model) plus two
derived ones (`arrival_hour`, `departure_hour`) from the HHMM time columns the
profiler flags. Values are bound parameters, never interpolated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .sqlengine import DATASET_NOTE, QueryResult, SqlEngine

STATS = ("n", "avg", "median", "p90", "max")
_STAT_SQL = ("count({c})", "round(avg({c}), 1)", "median({c})", "round(quantile_cont({c}, 0.9), 1)", "max({c})")
MAX_GROUPS = 25


@dataclass(frozen=True)
class Dimension:
    name: str
    sql: str  # column or expression over flights
    kind: str  # "code" (exact match), "int" (exact or [lo, hi] range)
    model_ref: str  # what in the semantic model this dimension comes from
    description: str


# Dimension name -> flights column. Every column here must be bound to the Flight
# entity type in model.yaml; build_catalog() checks that and drops any that isn't.
_COLUMN_DIMS = {
    "destination": ("DESTINATION_AIRPORT", "code", "Airport IATA code the flight arrives at (relation ARRIVES)"),
    "origin": ("ORIGIN_AIRPORT", "code", "Airport IATA code the flight departs from (relation DEPARTS)"),
    "airline": ("AIRLINE", "code", "Carrier IATA code (relation OPERATED_BY)"),
    "month": ("MONTH", "int", "1-12"),
    "day_of_week": ("DAY_OF_WEEK", "int", "1 = Monday ... 7 = Sunday"),
}
_HOUR_DIMS = {
    "arrival_hour": ("SCHEDULED_ARRIVAL", "Scheduled arrival hour, 0-23, from HHMM"),
    "departure_hour": ("SCHEDULED_DEPARTURE", "Scheduled departure hour, 0-23, from HHMM"),
}


@dataclass(frozen=True)
class MetricDef:
    name: str
    column: str
    unit: str
    description: str
    domain: str
    sources: tuple[str, ...]  # passage ids linked to this metric in the model


class MetricError(ValueError):
    """Request is outside what the semantic model defines. Message is shown to the agent."""


class MetricCatalog:
    """Queryable metrics and dimensions, derived from the semantic model."""

    def __init__(self, metrics: dict[str, MetricDef], dims: dict[str, Dimension], table_columns: set[str]):
        self.metrics = metrics
        self.dims = dims
        self.table_columns = table_columns

    def describe(self) -> str:
        """For the system prompt: the only questions the data can answer."""
        lines = [DATASET_NOTE, "", "Queryable metrics (query_metric; stats: n, avg, median, p90, max):"]
        for m in self.metrics.values():
            lines.append(f"- {m.name} ({m.unit}, {m.domain}): {m.description}")
        lines.append("Dimensions for filters and group_by:")
        for d in self.dims.values():
            rng = " exact value or [lo, hi]" if d.kind == "int" else " exact code"
            lines.append(f"- {d.name}:{rng}. {d.description}")
        return "\n".join(lines)

    def compile(self, metric: str, filters: dict, group_by: list[str]) -> tuple[str, list]:
        m = self.metrics.get(metric)
        if m is None:
            raise MetricError(f"{metric!r} is not a queryable metric in the semantic model. "
                              f"Choose one of: {', '.join(self.metrics)}")
        unknown = [k for k in [*filters, *group_by] if k not in self.dims]
        if unknown:
            raise MetricError(f"unknown dimension(s) {unknown}. Choose from: {', '.join(self.dims)}")
        if len(group_by) > 2:
            raise MetricError("group_by takes at most 2 dimensions")

        where, params = [f"{m.column} IS NOT NULL"], []
        for k, v in filters.items():
            d = self.dims[k]
            if d.kind == "int" and isinstance(v, list):
                if len(v) != 2 or not all(isinstance(x, int) for x in v):
                    raise MetricError(f"{k}: a range is [lo, hi] with two integers")
                where.append(f"{d.sql} BETWEEN ? AND ?")
                params += v
            elif d.kind == "int":
                if not isinstance(v, int):
                    raise MetricError(f"{k}: expected an integer or [lo, hi]")
                where.append(f"{d.sql} = ?")
                params.append(v)
            else:
                if not isinstance(v, str):
                    raise MetricError(f"{k}: expected a code string, e.g. 'ORD'")
                where.append(f"{d.sql} = ?")
                params.append(v.upper())

        groups = [f"{self.dims[g].sql} AS {g}" for g in group_by]
        stats = [s.format(c=m.column) + f" AS {name}" for s, name in zip(_STAT_SQL, STATS)]
        sql = f"SELECT {', '.join([*groups, *stats])} FROM flights WHERE {' AND '.join(where)}"
        if group_by:
            sql += f" GROUP BY {', '.join(group_by)} ORDER BY n DESC LIMIT {MAX_GROUPS}"
        return sql, params

    def unmodelled_columns(self, sql: str) -> list[str]:
        """Upper-case identifiers in raw SQL that are not columns the model profiled."""
        idents = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", re.sub(r"'[^']*'", "", sql)))
        return sorted(i for i in idents if i not in self.table_columns and i not in _SQL_WORDS)


_SQL_WORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "GROUP", "ORDER", "LIMIT", "HAVING", "BETWEEN", "NULL",
    "COUNT", "AVG", "SUM", "MIN", "MAX", "MEDIAN", "ROUND", "CASE", "WHEN", "THEN", "ELSE", "END", "DESC",
    "ASC", "DISTINCT", "JOIN", "LEFT", "INNER", "WITH", "IS", "IN", "LIKE", "CAST", "INTEGER", "INT",
    "DOUBLE", "VARCHAR", "QUANTILE_CONT", "FILTER", "OVER", "PARTITION", "USING", "ON", "UNION", "ALL",
    "TRUE", "FALSE", "BIGINT", "FLOOR", "COALESCE", "NULLIF", "STDDEV", "LPAD", "SUBSTR",
}


def build_catalog(engine) -> MetricCatalog:
    """Read the semantic engine and keep only what is actually bound to the flights table."""
    model = engine.model
    flights = next((t for t in model.tables if t.name == "flights"), None)
    profiled = {c.name: c for c in flights.columns} if flights else {}
    all_columns = {c.name for t in model.tables for c in t.columns}
    flight_type = engine.type_by_name.get("Flight")
    bound = set()
    if flight_type is not None:
        bound = {c for c in [flight_type.id_column, *flight_type.attribute_columns] if c}

    metrics: dict[str, MetricDef] = {}
    for m in model.metrics:
        if m.formula or len(m.inputs) != 1 or not m.inputs[0].startswith("flights."):
            continue  # derived or scenario-level: the rule engine computes those, they aren't queried
        col = m.inputs[0].split(".", 1)[1]
        prof = profiled.get(col)
        if prof is None or prof.type not in ("int", "float") or prof.is_time:
            continue
        sources = tuple(p.id for p in engine.passages_about("metric", m.name))
        metrics[m.name] = MetricDef(name=m.name, column=col, unit=m.unit or "", domain=m.domain,
                                    description=m.description or m.formula, sources=sources)

    dims: dict[str, Dimension] = {}
    for name, (col, kind, desc) in _COLUMN_DIMS.items():
        if col in bound and col in profiled:
            dims[name] = Dimension(name, col, kind, f"type:Flight.{col}", desc)
    for name, (col, desc) in _HOUR_DIMS.items():
        prof = profiled.get(col)
        if col in bound and prof is not None and prof.is_time:
            dims[name] = Dimension(name, f"(TRY_CAST({col} AS INTEGER) // 100) % 24", "int",
                                   f"type:Flight.{col}", desc)
    return MetricCatalog(metrics, dims, all_columns)


def run_metric(catalog: MetricCatalog, sql_engine: SqlEngine, metric: str, filters: dict,
               group_by: list[str]) -> tuple[str, QueryResult, str]:
    """Returns (agent-facing text, rows, compiled SQL)."""
    sql, params = catalog.compile(metric, filters, group_by)
    result = sql_engine.query(sql, params=params, max_rows=MAX_GROUPS)
    m = catalog.metrics[metric]
    src = f" Sources: {', '.join('passage:' + s for s in m.sources)}." if m.sources else ""
    header = (f"metric:{m.name} ({m.unit}) = {m.description}{src}\n"
              f"filters={filters or 'none'} group_by={group_by or 'none'}. Cite as source 'metric:{m.name}'.")
    if result.rows and not group_by and result.rows[0][0] == 0:
        return header + "\nNo flights match these filters; widen them.", result, sql
    return f"{header}\n{result.as_text()}", result, sql
