"""The semantic model is what the agents are grounded in; these keep it honest."""

from pathlib import Path

import pytest

from atc_negotiation import rules
from atc_negotiation.semantic import brief_for, default_engine, lookup
from atc_negotiation.semantic.model import SemanticModel
from atc_negotiation.schemas import AircraftCategory as Cat

ROOT = Path(__file__).parent.parent


def test_model_loads_and_every_reference_resolves():
    m = SemanticModel.load()
    assert m.validate_references() == []
    assert m.rules and m.passages and m.code_sets


def test_every_enforced_rule_cites_a_passage_or_is_structural():
    """A hard rule an agent is told about must point at where it comes from."""
    m = SemanticModel.load()
    uncited = [r.id for r in m.rules if r.hard and not r.source and r.kind != "constraint"]
    assert uncited == [], uncited


def test_brief_is_deterministic_and_role_specific():
    briefs = {r: brief_for(r) for r in ("atc", "pilot", "ground")}
    assert all(brief_for(r) == b for r, b in briefs.items())
    assert "atc.wake_separation" in briefs["atc"] and "atc.wake_separation" not in briefs["pilot"]
    assert "pilot.final_reserve_fuel" in briefs["pilot"] and "pilot.final_reserve_fuel" not in briefs["ground"]
    assert "ground.gate_available" in briefs["ground"]
    for b in briefs.values():
        assert "protocol.max_turns" in b  # shared protocol rules reach everyone
        assert "Synthetic in every scenario" in b
        assert "{'" not in b  # no raw dict dumps leaking into the prompt


def test_brief_cites_sources_it_quotes():
    b = brief_for("atc")
    assert "[icao:4444:5.8.2]" in b
    assert 'ICAO Doc 4444 PANS-ATM' in b and "2 minutes" in b


@pytest.mark.parametrize("term,expect", [
    ("tail number", "Aircraft"),
    ("FRF", "pilot.final_reserve_fuel"),
    ("pilot.final_reserve_fuel", "30 minutes"),
    ("WEATHER_DELAY", "Extreme Weather"),
    ("H", "Heavy"),
    ("icao:4444:5.8.2", "MEDIUM aircraft landing behind HEAVY"),
    ("stand", "Gate"),
    ("late inbound", "Late-arriving aircraft"),
])
def test_lookup_resolves_known_terms(term, expect):
    assert expect in lookup(term)


def test_lookup_returns_empty_for_unknown_so_the_tool_can_decline():
    assert lookup("unicorn") == ""
    assert lookup("") == ""


def test_rules_py_reads_wake_table_from_the_model():
    """One source of truth: rules.py constants == model.yaml params (organisers' workbook values)."""
    table = default_engine().rule_params("atc.wake_separation")["table"]
    assert rules.WAKE_SEPARATION_S[(Cat.HEAVY, Cat.MEDIUM)] == table["H>M"] == 120
    assert rules.WAKE_SEPARATION_S[(Cat.HEAVY, Cat.LIGHT)] == table["H>L"] == 120
    assert rules.WAKE_SEPARATION_S[(Cat.MEDIUM, Cat.LIGHT)] == table["M>L"] == 60
    assert rules.RADAR_MIN_S == table["default"] == 60
    assert rules.MISSED_PAX_COST == default_engine().rule_params("pilot.connections")["cost_per_pax"]


def test_rule_results_cite_rule_ids_when_schema_supports_it():
    from atc_negotiation.schemas import Proposal, RuleResult, Scenario
    s = Scenario.model_validate_json((ROOT / "scenarios" / "sample_weather.json").read_text())
    ev = rules.evaluate(s, Proposal(arrival_min=38, runway="27R", gate="B12", rationale=""))
    ids = {r.rule for r in ev.results}
    assert {"runway_open", "wake_separation", "final_reserve_fuel", "gate_available"} <= ids
    if "rule_id" in RuleResult.model_fields:
        cited = {r.rule_id for r in ev.results}
        assert all(c and c in default_engine().rule_by_id for c in cited), cited


def test_rules_py_and_model_agree_both_ways():
    """Every id rules.py emits is in the model, and every model rule enforced in rules.py is emitted.

    Agent citations are validated against the model, so an id missing there reads as a bad citation."""
    from atc_negotiation.schemas import Proposal, Scenario
    s = Scenario.model_validate_json((ROOT / "scenarios" / "sample_weather.json").read_text())
    emitted = set()
    for p in (Proposal(arrival_min=40, runway="27R", gate="B12", rationale=""),
              Proposal(arrival_min=40, runway="nope", gate="nope", rationale="")):
        emitted |= {r.rule_id for r in rules.evaluate(s, p).results}
    # Moves emit plan.* rules; exercise them on the scenario that has moves.
    sm = Scenario.model_validate_json((ROOT / "scenarios" / "demo_storm_aa1453_moves.json").read_text())
    emitted |= {r.rule_id for r in rules.evaluate(sm, Proposal(
        arrival_min=56, runway="27R", gate="A1", rationale="", moves=["ground.tow_a1"])).results}
    eng = default_engine()
    declared = {r.id for r in eng.model.rules if (r.enforced_by or "").startswith("rules.")}
    assert emitted - set(eng.rule_by_id) == set(), "emitted but not in model.yaml"
    assert declared - emitted == set(), "model.yaml says rules.py enforces these, but it never emits them"


def test_data_thresholds_come_from_the_model():
    from atc_negotiation import data
    eng = default_engine()
    f = eng.rule_params("data.disruption_filter")
    assert (data.WEATHER_DELAY_GT, data.LATE_AIRCRAFT_DELAY_GT) == (f["weather_delay_gt"], f["late_aircraft_delay_gt"])
    assert data.TURNAROUND_MIN == eng.rule_params("ground.turnaround")["value"]


def test_graph_is_connected_and_consistent():
    """The viewer draws this; a dangling edge or an orphan node means the model drifted."""
    from atc_negotiation.semantic.graph import build_graph
    g = build_graph()
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    touched = {e["source"] for e in g["edges"]} | {e["target"] for e in g["edges"]}
    assert ids <= touched, sorted(ids - touched)
    assert {n["layer"] for n in g["nodes"]} == {"ontology", "rules", "knowledge"}
    # every rule that cites a passage has a visible 'cites' edge to it
    cites = {(e["source"], e["target"]) for e in g["edges"] if e["rel"] == "cites"}
    for n in g["nodes"]:
        if n["kind"] == "rule" and n.get("source"):
            assert (n["id"], "passage:" + n["source"]) in cites, n["id"]


def test_schema_layer_is_generated_and_matches_data():
    m = SemanticModel.load()
    if not (ROOT / "data" / "flights.csv").exists():
        pytest.skip("run `make data` first")
    flights = next(t for t in m.tables if t.name == "flights")
    cols = {c.name for c in flights.columns}
    assert {"WEATHER_DELAY", "LATE_AIRCRAFT_DELAY", "TAIL_NUMBER", "SCHEDULED_ARRIVAL"} <= cols
    # the brief's filter columns are numeric in the profile
    assert next(c for c in flights.columns if c.name == "WEATHER_DELAY").type in ("int", "float")
