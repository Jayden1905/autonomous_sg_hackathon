"""Operational constraints, as code. The LLM never gets to decide these.

Each domain exposes one function returning a list of RuleResult. Hard rules
make a proposal infeasible when they fail; soft rules only add cost, which
the orchestrator and the fallback solver use to rank feasible proposals.

Every number comes from the semantic model (semantic/model.yaml), read once at
import. Each RuleResult cites the rule id it enforces, so a trace line can be
followed back to the rule, its parameters and its source passage.
"""

from __future__ import annotations

from .schemas import AircraftCategory as Cat
from .schemas import Evaluation, Proposal, RuleResult, Scenario
from .semantic import default_engine

_eng = default_engine()
_p = _eng.rule_params

# ── parameters, from the model (one source of truth) ──
_wake = _p("atc.wake_separation")
_WAKE_TABLE: dict[str, int] = dict(_wake.get("table", {}))
RADAR_MIN_S: int = int(_WAKE_TABLE.pop("default", 72))
# "H>M" → (HEAVY, MEDIUM) → 120
WAKE_SEPARATION_S: dict[tuple[Cat, Cat], int] = {
    (Cat(k.split(">")[0]), Cat(k.split(">")[1])): int(v)
    for k, v in _WAKE_TABLE.items()
    if k.split(">")[0] in Cat._value2member_map_ and k.split(">")[1] in Cat._value2member_map_
}
DELAY_COST_PER_MIN: float = float(_p("atc.sector_delay").get("cost_per_min", 1.0))
MISSED_PAX_COST: float = float(_p("pilot.connections").get("cost_per_pax", 2.0))
OVERTIME_COST_PER_MIN: float = float(_p("ground.crew_overtime").get("cost_per_min", 1.5))
GATE_OVERRUN_COST_PER_MIN: float = float(_p("ground.gate_overrun").get("cost_per_min", 1.0))
FINAL_RESERVE_DEFAULT_MIN: int = int(_p("pilot.final_reserve_fuel").get("value", 30))

_HAS_RULE_ID = "rule_id" in RuleResult.model_fields

# ── operator knowledge the engine knows how to enforce ──
# An operator's hard rule only counts if code checks it. These are the parameter shapes we
# understand; anything else stays advisory and is reported by `unenforced_hard_rules()`.
_OPERATOR_RULES = [r for r in _eng.model.rules if r.id.startswith("operator.") and r.hard]
GATE_BOARD_BUFFER_MIN: int = next((int(r.params["board_buffer_min"]) for r in _OPERATOR_RULES
                                   if "board_buffer_min" in r.params), 0)
_GATE_BUFFER_RULE = next((r.id for r in _OPERATOR_RULES if "board_buffer_min" in r.params), None)
DIVERT_BUFFER_MIN: int = next((int(r.params["value"]) for r in _OPERATOR_RULES
                               if r.params.get("above") == "final_reserve" and "value" in r.params), 0)
_DIVERT_BUFFER_RULE = next((r.id for r in _OPERATOR_RULES
                            if r.params.get("above") == "final_reserve" and "value" in r.params), None)
# The ledger in semantic/elicitation.yaml is a labelled worked example, not real interviews.
OPERATOR_LABEL = "operator knowledge (worked example)"
_ENFORCED_OPERATOR_RULES = {x for x in (_GATE_BUFFER_RULE, _DIVERT_BUFFER_RULE) if x}


def unenforced_hard_rules() -> list[str]:
    """Hard rules the brief tells agents about that no code checks. Should be empty."""
    return sorted(r.id for r in _eng.model.rules if r.hard and r.kind != "protocol"
                  and not r.enforced_by and r.id not in _ENFORCED_OPERATOR_RULES)


def _rr(rule_id: str, *, domain: str, passed: bool, hard: bool, detail: str, cost: float = 0.0) -> RuleResult:
    """Build a RuleResult citing the semantic-model rule. `rule` stays the short name for the UI.
    Operator rules are `operator.<role>.<name>`; their short name keeps the `operator.` prefix visible."""
    short = rule_id.split(".", 1)[1] if not rule_id.startswith("operator.") else rule_id.split(".", 2)[2] + " (operator)"
    if rule_id.startswith("operator."):
        detail = f"{OPERATOR_LABEL}: {detail}"
    kw = dict(rule=short, domain=domain, passed=passed, hard=hard, detail=detail, cost=cost)
    if _HAS_RULE_ID:
        kw["rule_id"] = rule_id
    return RuleResult(**kw)


def atc_rules(s: Scenario, p: Proposal) -> list[RuleResult]:
    out: list[RuleResult] = []
    rwy = next((r for r in s.runways if r.name == p.runway), None)

    if rwy is None:
        out.append(_rr("atc.runway_exists", domain="atc", passed=False, hard=True,
                       detail=f"runway {p.runway!r} is not at {s.destination}"))
        return out

    out.append(_rr("atc.runway_open", domain="atc", passed=rwy.open, hard=True,
                   detail=f"{rwy.name} is {'open' if rwy.open else 'closed'}"))
    out.append(_rr("atc.taxiway_clear", domain="atc", passed=not rwy.taxiway_blocked, hard=True,
                   detail=f"taxiway from {rwy.name} is {'blocked' if rwy.taxiway_blocked else 'clear'}"))

    # Wake separation against every aircraft already on that runway, both directions.
    worst_gap, worst_need, worst_other = None, 0, None
    for other in rwy.arrivals:
        gap_s = abs(p.arrival_min - other.time_min) * 60
        if other.time_min <= p.arrival_min:
            need = WAKE_SEPARATION_S.get((other.category, s.aircraft_category), RADAR_MIN_S)
        else:
            need = WAKE_SEPARATION_S.get((s.aircraft_category, other.category), RADAR_MIN_S)
        if worst_gap is None or gap_s - need < worst_gap - worst_need:
            worst_gap, worst_need, worst_other = gap_s, need, other
    if worst_other is None:
        out.append(_rr("atc.wake_separation", domain="atc", passed=True, hard=True,
                       detail=f"no other traffic on {rwy.name}"))
    else:
        ok = worst_gap >= worst_need
        out.append(_rr(
            "atc.wake_separation", domain="atc", passed=ok, hard=True,
            detail=(f"{worst_gap}s to {worst_other.category.name.lower()} at t={worst_other.time_min}; "
                    f"need {worst_need}s"),
        ))

    within = s.earliest_arrival_min <= p.arrival_min <= s.max_arrival_min
    out.append(_rr(
        "atc.slot_window", domain="atc", passed=within, hard=True,
        detail=f"arrival t={p.arrival_min} must lie in [{s.earliest_arrival_min}, {s.max_arrival_min}]",
    ))
    delay = max(0, p.arrival_min)
    out.append(_rr("atc.sector_delay", domain="atc", passed=True, hard=False,
                   detail=f"{delay} min of sector delay", cost=delay * DELAY_COST_PER_MIN))
    return out


def pilot_rules(s: Scenario, p: Proposal) -> list[RuleResult]:
    out: list[RuleResult] = []
    hold = max(0, p.arrival_min - s.earliest_arrival_min)
    remaining = s.fuel_endurance_min - hold
    out.append(_rr(
        "pilot.final_reserve_fuel", domain="pilot", passed=remaining >= s.final_reserve_min, hard=True,
        detail=f"{hold} min hold leaves {remaining} min fuel; final reserve is {s.final_reserve_min} min",
    ))
    if _DIVERT_BUFFER_RULE:
        # Operator rule: the divert decision is made with a buffer above final reserve, not at it.
        margin = remaining - s.final_reserve_min
        out.append(_rr(
            _DIVERT_BUFFER_RULE, domain="pilot", passed=margin >= DIVERT_BUFFER_MIN, hard=True,
            detail=f"{margin} min above final reserve at landing; operator requires {DIVERT_BUFFER_MIN}",
        ))

    missed = sum(c.passengers for c in s.connections
                 if p.arrival_min + c.min_connect_min > c.departs_min)
    out.append(_rr("pilot.connections", domain="pilot", passed=True, hard=False,
                   detail=f"{missed} passengers miss onward flights", cost=missed * MISSED_PAX_COST))
    return out


def ground_rules(s: Scenario, p: Proposal) -> list[RuleResult]:
    out: list[RuleResult] = []
    gate = next((g for g in s.gates if g.name == p.gate), None)
    if gate is None:
        out.append(_rr("ground.gate_exists", domain="ground", passed=False, hard=True,
                       detail=f"gate {p.gate!r} is not at {s.destination}"))
        return out

    free = gate.free_from_min <= p.arrival_min <= gate.free_until_min
    out.append(_rr(
        "ground.gate_available", domain="ground", passed=free, hard=True,
        detail=f"gate {gate.name} free t=[{gate.free_from_min}, {gate.free_until_min}], arrival t={p.arrival_min}",
    ))

    # The turnaround keeps the gate busy; running past its window pushes the gate's next flight.
    on_block_until = p.arrival_min + s.turnaround_min
    overrun = max(0, on_block_until - gate.free_until_min)
    out.append(_rr("ground.gate_overrun", domain="ground", passed=True, hard=False,
                   detail=f"turnaround holds {gate.name} to t={on_block_until}; gate is next needed at "
                          f"t={gate.free_until_min}, {overrun} min overrun",
                   cost=overrun * GATE_OVERRUN_COST_PER_MIN))
    if _GATE_BUFFER_RULE:
        # Operator rule: the board is optimistic; a gate is free only from board time + buffer.
        really_free_from = gate.free_from_min + GATE_BOARD_BUFFER_MIN
        out.append(_rr(
            _GATE_BUFFER_RULE, domain="ground", passed=p.arrival_min >= really_free_from, hard=True,
            detail=f"board says free from t={gate.free_from_min}; operator buffer {GATE_BOARD_BUFFER_MIN} min "
                   f"makes it t={really_free_from}, arrival t={p.arrival_min}",
        ))

    overtime = max(0, p.arrival_min + s.turnaround_min - s.crew_shift_ends_min)
    out.append(_rr("ground.crew_overtime", domain="ground", passed=True, hard=False,
                   detail=f"{overtime} min of ground-crew overtime",
                   cost=overtime * OVERTIME_COST_PER_MIN))
    return out


# ── agent moves: actions an agent can offer beyond choosing slot, runway and gate ──
# A move changes the situation (frees a gate early, extends a shift, re-sequences an arrival,
# reopens a runway, absorbs delay en route so less is burned holding). evaluate() applies the plan's moves to a copy
# of the scenario and then runs every rule above unchanged: a move can create room, it can
# never relax a safety rule. Each move costs what its owner says it costs.
MOVE_KINDS = ("gate_free_from", "crew_shift_ends_min", "fuel_gain_min", "arrival_moved", "runway_opens")


def _field(obj, name, default=None):
    """Read a field from a pydantic model or a dict, so moves work before and after schema fields exist."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def apply_moves(s: Scenario, move_ids: list[str]) -> tuple[Scenario, list[RuleResult], dict[str, int]]:
    """The scenario as it would be after the moves, one result per move (known? what it costs), and
    the reopening time of any runway a move reopened."""
    catalogue = {_field(m, "id"): m for m in (_field(s, "moves", None) or [])}
    s2 = s.model_copy(deep=True)
    results: list[RuleResult] = []
    reopens: dict[str, int] = {}
    for mid in move_ids:
        m = catalogue.get(mid)
        if m is None:
            # Charge it to the role its id names (moves are '<role>.<name>'); ATC owns the plan otherwise.
            role = mid.split(".", 1)[0] if mid.split(".", 1)[0] in ("atc", "pilot", "ground") else "atc"
            results.append(_rr("plan.move_known", domain=role, passed=False, hard=True,
                               detail=f"move {mid!r} is not available in this situation"))
            continue
        owner, label = _field(m, "owner", "shared"), _field(m, "label", mid)
        e = _field(m, "effect", {}) or {}
        note = _apply_effect(s2, e, reopens)
        results.append(_rr("plan.move_known", domain=owner, passed=True, hard=True,
                           detail=f"{owner} move {mid}: {label}"))
        results.append(_rr("plan.move_cost", domain=owner, passed=True, hard=False,
                           detail=f"{owner} move {mid}: {label}; {note}",
                           cost=float(_field(m, "cost", 0.0) or 0.0)))
    return s2, results, reopens


def _apply_effect(s: Scenario, e, reopens: dict[str, int]) -> str:
    if (g := _field(e, "gate_free_from")) is not None:
        gate = next((x for x in s.gates if x.name == g["gate"]), None)
        if gate is not None:
            gate.free_from_min = int(g["free_from_min"])
            return f"gate {gate.name} free from t={gate.free_from_min}"
    if (t := _field(e, "crew_shift_ends_min")) is not None:
        s.crew_shift_ends_min = int(t)
        return f"crew shift extended to t={s.crew_shift_ends_min}"
    if (f := _field(e, "fuel_gain_min")) is not None:
        # Absorbing delay en route at reduced speed burns less than holding: more endurance at arrival.
        s.fuel_endurance_min += max(0, int(f))
        return f"delay absorbed en route at reduced speed: +{max(0, int(f))} min endurance (final reserve unchanged)"
    if (a := _field(e, "arrival_moved")) is not None:
        rwy = next((r for r in s.runways if r.name == a["runway"]), None)
        hit = rwy and next((x for x in rwy.arrivals if x.time_min == int(a["from_min"])), None)
        if hit:
            hit.time_min = int(a["to_min"])
            return f"{hit.category.name.lower()} on {rwy.name} re-sequenced from t={a['from_min']} to t={a['to_min']}"
    if (o := _field(e, "runway_opens")) is not None:
        rwy = next((r for r in s.runways if r.name == o["runway"]), None)
        if rwy is not None:
            reopens[rwy.name] = int(o["open_from_min"])
            rwy.open = True
            return f"runway {rwy.name} reopened from t={o['open_from_min']}"
    return "no effect"


def _runway_reopen_rules(p: Proposal, reopens: dict[str, int]) -> list[RuleResult]:
    """A reopened runway is only usable from its reopening time."""
    t = reopens.get(p.runway)
    if t is None:
        return []
    return [_rr("atc.runway_open", domain="atc", passed=p.arrival_min >= t, hard=True,
                detail=f"{p.runway} reopens at t={t}, arrival t={p.arrival_min}")]


def evaluate(s: Scenario, p: Proposal) -> Evaluation:
    move_ids = list(_field(p, "moves", None) or [])
    move_results: list[RuleResult] = []
    reopens: dict[str, int] = {}
    if move_ids:
        s, move_results, reopens = apply_moves(s, move_ids)
    return Evaluation(proposal=p, results=move_results + atc_rules(s, p) + _runway_reopen_rules(p, reopens)
                      + pilot_rules(s, p) + ground_rules(s, p))
