"""Each citation guardrail catches the failure it exists for, and a well-cited reply passes."""

from pathlib import Path

import pytest

from atc_negotiation.agents import Resources, make_agents
from atc_negotiation.grounding import Grounder, Ledger
from atc_negotiation.guardrails import Guardrails, numbers
from atc_negotiation.orchestrator import negotiate
from atc_negotiation.rules import evaluate
from atc_negotiation.schemas import AgentResponse, Evidence, Proposal, Scenario, Verdict
from atc_negotiation.semantic import default_engine, lookup
from atc_negotiation.tools import evaluation_brief

SAMPLE = Path(__file__).parent.parent / "scenarios" / "sample_weather.json"
METRIC_OUT = "metric:taxi_in (min)\nn | avg | median | p90 | max\n455 | 14.2 | 13.0 | 26.0 | 90"


def setup(metric_n=455):
    s = Scenario.model_validate_json(SAMPLE.read_text())
    g = Grounder(default_engine(), s)
    led = Ledger(metrics_queried={"taxi_in"}, checked_plan=True)
    led.saw("metric:taxi_in", METRIC_OUT.replace("455", str(metric_n)))
    led.metric_samples["taxi_in"] = [metric_n]
    plan = Proposal(arrival_min=38, runway="27R", gate="B12", rationale="")
    led.saw("check_proposal", evaluation_brief(evaluate(s, plan), default_engine()))
    return s, g, led


def run(rationale, evidence, metric_n=455):
    s, g, led = setup(metric_n)
    ev, _ = g.finalize([Evidence(claim=c, source=src) for c, src in evidence], led)
    p = Proposal(arrival_min=38, runway="27R", gate="B12", rationale=rationale, evidence=ev)
    return Guardrails(g, s).check(p, led)


def codes(report):
    return {v.code for v in report.violations}


GOOD = [("ORD taxi_in median 13, p90 26 min (n=455)", "metric:taxi_in"),
        ("Final reserve is 30 min for turbine aeroplanes", "rule:pilot.final_reserve_fuel")]


def test_well_cited_reply_passes():
    r = run("Taxi-in adds a median 13 min, so on-block is about t+51 [1]. Fuel stays above the 30 min "
            "final reserve [2].", GOOD)
    assert r.passed, r.violations


def test_g1_sentence_without_marker():
    r = run("Taxi-in adds 13 min [1]. Fuel stays above the 30 min final reserve.", GOOD)
    assert "G1" in codes(r)


def test_g2_marker_points_at_nothing():
    r = run("Taxi-in adds 13 min [1][7].", GOOD)
    assert "G2" in codes(r)


def test_g3_metric_cited_without_query():
    r = run("Arrival delay median is 76 min [1].", [("DEN-ORD arrival_delay median 76", "metric:arrival_delay")])
    assert "G3" in codes(r) and "not queried" in r.violations[0].message


def test_g4_invented_number_in_claim():
    r = run("Taxi-in p90 is 47 min [1].", [("ORD taxi_in p90 47 min", "metric:taxi_in")])
    assert "G4" in codes(r)


def test_g5_real_number_attributed_to_the_wrong_source_is_also_caught():
    # 41 is real (another arrival at t=41 in the scenario) but not a taxi_in statistic
    r = run("Taxi-in p90 is 41 min [1].", [("ORD taxi_in p90 41 min", "metric:taxi_in")])
    assert "G5" in codes(r) and not r.passed


def test_g5_number_from_the_wrong_source():
    # 455 is real (from the metric), but the claim cites the fuel rule
    r = run("455 flights back this [1].", [("455 flights were sampled", "rule:pilot.final_reserve_fuel")])
    assert "G5" in codes(r)


def test_g6_prose_number_not_in_cited_evidence():
    r = run("Fuel reserve is 30 min and taxi-in median is 13 min [2].", GOOD)
    assert "G6" in codes(r)


def test_g7_thin_sample():
    r = run("Taxi-in median 13 min [1].", [("ORD taxi_in median 13 (n=6)", "metric:taxi_in")], metric_n=6)
    assert "G7" in codes(r)


def test_arithmetic_on_observed_numbers_is_allowed():
    # 38 (scenario/plan) + 13 (taxi_in median) = 51
    r = run("On-block is about t+51 [1][2].", [("ORD taxi_in median 13", "metric:taxi_in"),
                                             ("Arrival is t+38", "check_proposal")])
    assert r.passed, r.violations


def test_identifiers_are_not_numbers():
    assert numbers("Land UA1234 on 27R at gate B12 by t+38 [3]") == {38.0}


def test_trust_levels():
    s, g, led = setup()
    guard = Guardrails(g, s)
    ev, _ = g.finalize([Evidence(claim="x", source=src) for src in
                        ["rule:pilot.final_reserve_fuel", "rule:ground.crew_overtime", "scenario:gates",
                         "metric:taxi_in", "check_proposal"]], led)
    assert [guard.trust(e, led) for e in ev] == ["high", "medium", "low", "high", "high"]


def test_blocked_accept_does_not_create_consensus():
    from atc_negotiation.agents import MockAgent
    from atc_negotiation.schemas import GuardrailReport, GuardrailViolation

    class Uncited(MockAgent):
        def respond(self, s, p, ev, ctx):
            v = GuardrailViolation(code="G1", kind="uncited_sentence", where="summary", message="no marker")
            return AgentResponse(verdict=Verdict.ACCEPT, summary="fine",
                                 guardrail=GuardrailReport(passed=False, violations=[v]))

    res = Resources(lookup=lookup, semantic=default_engine())
    agents = make_agents(mock=True, resources=res)
    agents["pilot"] = Uncited("pilot", res)
    tr = negotiate(Scenario.model_validate_json(SAMPLE.read_text()), agents)
    assert tr.outcome != "consensus" or all("pilot" not in t.guardrail_blocked for t in tr.turns[-1:])
    assert all("pilot" in t.guardrail_blocked for t in tr.turns)
    assert tr.outcome == "fallback"
