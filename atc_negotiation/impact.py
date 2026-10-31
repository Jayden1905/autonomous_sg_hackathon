"""Impact: what the negotiated plan changes against the recorded 2015 outcome.

The DOT row for each scenario records what actually happened to that flight
(ARRIVAL_DELAY). The negotiation produces arrival_min for the same flight under a
disruption rebuilt from the same row. The difference is a measured before/after.

Two honesty constraints are built in and printed with every report:

* Floor. A flight cannot arrive before it departed late: earliest_arrival_min equals
  the recorded DEPARTURE_DELAY. The only delay the negotiation can remove is the part
  accrued after departure (sequencing, holding, gate waits). We report the recorded
  post-departure delay as the baseline, not the whole ARRIVAL_DELAY.
* Scope. Runways, gates, fuel and connections in the scenario are synthetic; the real
  controllers were sequencing hundreds of flights. The comparison is indicative.

Measured vs estimated is kept explicit in the output. Fuel and coordination time are
estimates from published figures and are labelled as such.
"""

from __future__ import annotations

import json
import statistics as st
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import data
from .schemas import NegotiationTrace, Scenario

# Estimates, with sources (see semantic/SOURCES.md § Impact). Not measured by us.
# A320-family holding fuel flow: 2,400 kg/h (40 kg/min) is the standard planning rule of thumb;
# actual low-altitude holding at landing weights is ~1,800-2,400 kg/h. We use the planning figure.
HOLDING_BURN_KG_PER_MIN = 40.0
# We found no published per-flight figure for human phone/radio coordination time during irregular
# operations, so it is reported qualitatively (the brief's own framing), not as a number.


@dataclass
class Row:
    scenario_id: str
    outcome: str
    turns: int
    duration_s: float
    recorded_arrival_delay: int      # DOT ARRIVAL_DELAY
    departure_delay: int             # DOT DEPARTURE_DELAY == earliest_arrival_min
    recorded_post_departure: int     # recorded_arrival_delay - departure_delay (the removable part)
    negotiated_arrival: int | None   # Proposal.arrival_min; None when no_legal_option
    negotiated_post_departure: int | None
    holding_min: int | None
    missed_pax: int | None
    total_pax: int
    fuel_hold_kg_est: float | None


@dataclass
class Report:
    n: int
    agents: str
    rows: list[Row] = field(default_factory=list)

    # ---- measured ----
    @property
    def compared(self) -> list[Row]:
        return [r for r in self.rows if r.negotiated_post_departure is not None]

    def _med(self, xs: Iterable[float]) -> float | None:
        xs = list(xs)
        return round(st.median(xs), 1) if xs else None

    def _mean(self, xs: Iterable[float]) -> float | None:
        xs = list(xs)
        return round(st.mean(xs), 1) if xs else None

    def summary(self) -> dict[str, Any]:
        c = self.compared
        rec = [r.recorded_post_departure for r in c]
        neg = [r.negotiated_post_departure for r in c]
        diff = [a - b for a, b in zip(rec, neg)]
        improved = sum(1 for d in diff if d > 0)
        worse = sum(1 for d in diff if d < 0)
        hold = [r.holding_min for r in c if r.holding_min is not None]
        pax_total = sum(r.total_pax for r in c)
        pax_missed = sum(r.missed_pax or 0 for r in c)
        outcomes = {k: sum(1 for r in self.rows if r.outcome == k) for k in ("consensus", "fallback", "no_legal_option")}
        # How often had the real system already absorbed the disruption before arrival? When the recorded
        # post-departure delay is 0, there is nothing left for a negotiation to remove, and any holding
        # we add shows up as "worse". This number tells the reader whether the delay comparison can mean anything.
        baseline_zero = sum(1 for x in rec if x <= 0)
        return {
            "n": self.n, "agents": self.agents, "compared": len(c), "outcomes": outcomes,
            "measured": {
                "recorded_post_departure_delay_min": {"median": self._med(rec), "mean": self._mean(rec)},
                "negotiated_post_departure_delay_min": {"median": self._med(neg), "mean": self._mean(neg)},
                "reduction_min": {"median": self._med(diff), "mean": self._mean(diff),
                                  "improved": improved, "worse": worse, "unchanged": len(diff) - improved - worse},
                "reduction_pct_of_recorded": (round(100 * sum(diff) / sum(rec), 1) if sum(rec) else None),
                "baseline_already_zero": {"count": baseline_zero, "pct": round(100 * baseline_zero / len(rec), 1) if rec else None},
                "holding_min": {"median": self._med(hold), "mean": self._mean(hold)},
                "passengers": {"total": pax_total, "missed_connection": pax_missed,
                               "kept_pct": round(100 * (1 - pax_missed / pax_total), 1) if pax_total else None},
                "turns_mean": self._mean(r.turns for r in self.rows),
                "decision_time_s_mean": self._mean(r.duration_s for r in self.rows),
                "declined_no_legal_option": outcomes["no_legal_option"],
            },
            "estimated": {
                "fuel_in_hold_kg_per_flight": {"median": self._med(r.fuel_hold_kg_est for r in c if r.fuel_hold_kg_est is not None),
                                               "basis": f"{HOLDING_BURN_KG_PER_MIN:g} kg/min A320-family holding burn"},
                "human_coordination": {"value": None,
                                       "basis": "today this is phone calls and manual updates across three organisations (brief); "
                                                "no published per-flight minutes figure found, so not quantified"},
            },
            "caveats": [
                "Baseline is the recorded 2015 outcome for the same flight, not a controlled comparison.",
                "Only post-departure delay is comparable: a flight cannot arrive before its recorded departure delay.",
                f"In {baseline_zero} of {len(rec)} rows the real system had already absorbed the disruption before arrival "
                "(recorded post-departure delay 0), so any holding our synthetic runway imposes reads as 'worse'. "
                "The delay comparison therefore says more about the synthetic congestion than about the negotiation.",
                "Runways, gates, fuel, connections and crew in each scenario are synthetic (listed per scenario in synthetic_fields).",
                "Real controllers sequenced hundreds of flights; the negotiation optimises one.",
                "Fuel is an estimate from a published planning figure; coordination time is not quantified.",
            ],
        }


def _scenarios_for(csv_path: Path, traces: list[NegotiationTrace]) -> list[Scenario | None]:
    """Rebuild each trace's scenario from the same CSV (deterministic per row), in trace order.

    Ids carry the route (data.scenario_id) and are unique. Traces written before that carry the
    legacy flight-date id, which several legs can share. `atc batch` walks qualifying rows in file
    order, so the k-th trace with a legacy id came from the k-th row with that id; match by that
    occurrence. A legacy id with more traces than rows stays unmatched (None) rather than being
    joined to another flight's recorded outcome."""
    wanted = {t.scenario_id for t in traces}
    by_id: dict[str, Scenario] = {}
    legacy: dict[str, list[dict]] = {}
    for row in data.qualifying_rows(csv_path):
        sid = data.scenario_id(row)
        if sid in wanted:
            by_id[sid] = data.scenario_from_row(row)
        old = data.legacy_scenario_id(row)
        if old in wanted:
            legacy.setdefault(old, []).append(row)
    seen: dict[str, int] = {}
    out: list[Scenario | None] = []
    for t in traces:
        if t.scenario_id in by_id:
            out.append(by_id[t.scenario_id])
            continue
        k = seen.get(t.scenario_id, 0)
        seen[t.scenario_id] = k + 1
        rows = legacy.get(t.scenario_id, [])
        out.append(data.scenario_from_row(rows[k]) if k < len(rows) else None)
    return out


def build(traces_path: Path, csv_path: Path) -> Report:
    traces = [NegotiationTrace.model_validate_json(l) for l in traces_path.read_text().splitlines() if l.strip()]
    scen = _scenarios_for(csv_path, traces)
    agents = traces[0].model if traces else "unknown"
    rep = Report(n=len(traces), agents="mock" if agents == "mock" else f"real ({agents})")
    for t, s in zip(traces, scen):
        if s is None:
            continue
        rec_arr = int(float(s.source.get("ARRIVAL_DELAY", 0) or 0))
        dep = s.earliest_arrival_min
        comparable = t.outcome != "no_legal_option"
        neg = t.final.arrival_min if comparable else None
        hold = max(0, neg - dep) if neg is not None else None
        missed = None
        if comparable:
            missed = sum(c.passengers for c in s.connections if neg + c.min_connect_min > c.departs_min)
        rep.rows.append(Row(
            scenario_id=t.scenario_id, outcome=t.outcome, turns=len(t.turns), duration_s=t.duration_s,
            recorded_arrival_delay=rec_arr, departure_delay=dep,
            recorded_post_departure=max(0, rec_arr - dep),
            negotiated_arrival=neg, negotiated_post_departure=(neg - dep) if neg is not None else None,
            holding_min=hold, missed_pax=missed, total_pax=sum(c.passengers for c in s.connections),
            fuel_hold_kg_est=(hold * HOLDING_BURN_KG_PER_MIN) if hold is not None else None,
        ))
    return rep


def render(summary: dict[str, Any]) -> str:
    m, e = summary["measured"], summary["estimated"]
    o = summary["outcomes"]
    L = []
    L.append(f"Impact: {summary['n']} scenarios, {summary['agents']} agents; {summary['compared']} comparable "
             f"({o['consensus']} consensus, {o['fallback']} fallback, {o['no_legal_option']} declined)")
    L.append("")
    L.append("MEASURED")
    L.append(f"  decision time                      mean {m['decision_time_s_mean']} s, {m['turns_mean']} turns per disruption")
    p = m["passengers"]
    L.append(f"  passengers kept on connections     {p['total'] - p['missed_connection']} of {p['total']}  ({p['kept_pct']}%)")
    L.append(f"  declined (no legal option)         {m['declined_no_legal_option']}  (the system refused rather than invent a plan)")
    L.append(f"  holding absorbed                   median {m['holding_min']['median']:>6} min per flight")
    L.append("")
    L.append("DELAY vs RECORDED 2015 OUTCOME (same flight, post-departure only)")
    L.append(f"  recorded                           median {m['recorded_post_departure_delay_min']['median']:>6} min   mean {m['recorded_post_departure_delay_min']['mean']}")
    L.append(f"  negotiated                         median {m['negotiated_post_departure_delay_min']['median']:>6} min   mean {m['negotiated_post_departure_delay_min']['mean']}")
    r = m["reduction_min"]; bz = m["baseline_already_zero"]
    L.append(f"  difference                         median {r['median']:>6} min   ({r['improved']} better, {r['worse']} worse, {r['unchanged']} same)")
    L.append(f"  baseline already 0                 {bz['count']} rows ({bz['pct']}%): real system had absorbed the disruption before arrival")
    L.append("  reading: on this dataset the recorded disruption is at departure; by arrival the real system had usually")
    L.append("  recovered. Our synthetic runway adds holding the real day did not have. Delay minutes is not a measure")
    L.append("  this dataset can support in our favour, and we report it anyway.")
    L.append("")
    L.append("ESTIMATED (published figures, labelled)")
    f = e["fuel_in_hold_kg_per_flight"]
    L.append(f"  fuel burned in hold                median {f['median']} kg/flight   [{f['basis']}]")
    h = e["human_coordination"]
    L.append(f"  human coordination replaced        not quantified   [{h['basis']}]")
    L.append("")
    L.append("CAVEATS")
    L.extend(f"  - {c}" for c in summary["caveats"])
    return "\n".join(L)


def write_json(summary: dict[str, Any], out: Path) -> None:
    out.write_text(json.dumps(summary, indent=2))
