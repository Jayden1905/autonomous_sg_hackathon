"""Elicitation is a build stage: the model must know what it does not know, ask, and fold answers in."""

from pathlib import Path

import pytest

from atc_negotiation.semantic import elicit
from atc_negotiation.semantic.model import Answer, Elicitation, Operator, SemanticModel

ROOT = Path(__file__).parent.parent


@pytest.fixture
def bare() -> SemanticModel:
    """The curated model with no operator knowledge: ledger neither applied nor attached."""
    m = SemanticModel.load(apply_operator_knowledge=False)
    m.elicitation = Elicitation()
    return m


def test_gaps_name_everything_the_documents_could_not_say(bare):
    g = elicit.gaps(bare)
    assert {t.name for t in g["synthetic_type"]} >= {"Runway", "Gate", "GroundCrew", "Connection", "Turnaround"}
    assert {r.id for r in g["default_param"]} >= {"pilot.connections", "ground.turnaround", "ground.crew_overtime"}
    assert any(c.name == "ArrivalSlot" for c in g["undescribed_concept"])


def test_questions_cover_every_role_and_lead_with_feasibility(bare):
    qs = elicit.questions(bare)
    # every agent role gets questions; 'shared' is legitimate for concepts/metrics no one agent owns
    assert {"atc", "pilot", "ground"} <= {q.role for q in qs} <= {"atc", "pilot", "ground", "shared"}
    assert qs[0].priority == 1
    assert all(q.text and q.id.startswith("q.") for q in qs)
    assert len({q.id for q in qs}) == len(qs)
    assert any(q.kind == "open" for q in qs)  # the model cannot only ask about what it already names


def test_coverage_is_red_until_priority_one_is_decided(bare):
    cov = elicit.coverage(bare)
    assert cov["status"] == "red" and cov["answered"] == 0


def _op():
    return Operator(id="dm_ord", name="A. Duty Manager", role="ground", title="Duty manager, ORD")


def _answer(qid, text, structured, confirmed=True):
    return Answer(question_id=qid, by="dm_ord", at="2026-10-31T10:00:00Z", text=text,
                  structured=structured, confirmed=confirmed)


def test_confirmed_answer_updates_rule_params_and_is_citable(bare):
    bare.elicitation = Elicitation(operators=[_op()], questions=elicit.questions(bare), answers=[
        _answer("q.ground.param.turnaround", "We plan 40 on the 737s here, 35 is the floor under disruption.",
                {"params": {"value": 40, "unit": "min", "floor_min": 35}})])
    log = elicit.apply_answers(bare)
    r = next(r for r in bare.rules if r.id == "ground.turnaround")
    assert r.params["value"] == 40 and r.params["floor_min"] == 35
    assert any(e.by == "operator" for e in r.evidence)
    p = next(p for p in bare.passages if p.kind == "operator")
    assert p.id.startswith("operator:dm_ord:") and p.by == "dm_ord"
    assert "We plan 40" in p.text
    assert bare.validate_references() == []
    assert any("ground.turnaround" in line for line in log)


def test_operator_cannot_weaken_a_protected_regulatory_rule(bare):
    bare.elicitation = Elicitation(operators=[_op()], questions=elicit.questions(bare) + [
        elicit.Question(id="q.pilot.frf_override", role="pilot", kind="unsourced_rule", target_kind="rule",
                        target="pilot.final_reserve_fuel", text="x", priority=1)], answers=[
        _answer("q.pilot.frf_override", "We routinely land with 20.", {"params": {"value": 20}})])
    before = next(r for r in bare.rules if r.id == "pilot.final_reserve_fuel").params["value"]
    log = elicit.apply_answers(bare)
    after = next(r for r in bare.rules if r.id == "pilot.final_reserve_fuel").params["value"]
    assert before == after == 30
    assert any(line.startswith("REFUSED pilot.final_reserve_fuel") for line in log)
    # the operator's words are still kept, as a passage, so the disagreement is visible
    assert any(p.kind == "operator" and "20" in p.text for p in bare.passages)


def test_unconfirmed_answers_are_recorded_but_not_applied(bare):
    bare.elicitation = Elicitation(operators=[_op()], questions=elicit.questions(bare), answers=[
        _answer("q.ground.param.turnaround", "maybe 40?", {"params": {"value": 40}}, confirmed=False)])
    elicit.apply_answers(bare)
    assert next(r for r in bare.rules if r.id == "ground.turnaround").params["value"] == 45


def test_new_local_rule_from_an_open_question(bare):
    bare.elicitation = Elicitation(operators=[_op()], questions=elicit.questions(bare), answers=[
        _answer("q.ground.open", "If the inbound to a gate is still airborne, treat that gate as not free.",
                {"new_rule": {"id": "operator.ground.gate_inbound_airborne", "kind": "constraint", "hard": True,
                              "text": "A gate whose inbound aircraft is still airborne is not free.",
                              "subjects": ["Gate"]}})])
    elicit.apply_answers(bare)
    r = next(r for r in bare.rules if r.id == "operator.ground.gate_inbound_airborne")
    assert r.hard and r.source.startswith("operator:") and r.status == "confirmed"
    assert bare.validate_references() == []


def test_last_confirmed_answer_wins(bare):
    bare.elicitation = Elicitation(operators=[_op()], questions=elicit.questions(bare), answers=[
        _answer("q.ground.param.turnaround", "40", {"params": {"value": 40}}),
        _answer("q.ground.param.turnaround", "no, 42 after the new catering contract", {"params": {"value": 42}})])
    elicit.apply_answers(bare)
    assert next(r for r in bare.rules if r.id == "ground.turnaround").params["value"] == 42


def test_operator_hard_rules_change_feasibility_not_just_the_prompt():
    """The shipped ledger's hard operator rules are enforced by rules.py on the loaded model."""
    from atc_negotiation import rules
    from atc_negotiation.schemas import Proposal, Scenario
    assert rules.unenforced_hard_rules() == [], rules.unenforced_hard_rules()
    s = Scenario.model_validate_json((ROOT / "scenarios" / "sample_weather.json").read_text())
    # B12 board says free from t=35; operator buffer 10 -> really free from 45. t=38 passes the
    # regulatory gate rule but fails the operator's.
    ev = rules.evaluate(s, Proposal(arrival_min=38, runway="27R", gate="B12", rationale=""))
    by = {r.rule_id: r for r in ev.results if getattr(r, "rule_id", None)}
    assert by["ground.gate_available"].passed is True
    assert by["operator.ground.gate_board_buffer"].passed is False
    assert not ev.feasible
    ev2 = rules.evaluate(s, Proposal(arrival_min=46, runway="27R", gate="B12", rationale=""))
    assert {r.rule_id: r.passed for r in ev2.results}["operator.ground.gate_board_buffer"] is True


def test_ledger_without_a_question_list_still_applies(bare):
    """A hand-written ledger that only has answers must work: questions are regenerated."""
    bare.elicitation = Elicitation(operators=[_op()], questions=[], answers=[
        _answer("q.ground.param.turnaround", "40", {"params": {"value": 40}})])
    elicit.apply_answers(bare)
    assert next(r for r in bare.rules if r.id == "ground.turnaround").params["value"] == 40


def test_brief_shows_operator_knowledge_section(bare):
    from atc_negotiation.semantic.briefing import render_brief
    from atc_negotiation.semantic.engine import SemanticEngine
    bare.elicitation = Elicitation(operators=[_op()], questions=elicit.questions(bare), answers=[
        _answer("q.ground.param.turnaround", "We plan 40 here.", {"params": {"value": 40}})])
    elicit.apply_answers(bare)
    b = render_brief(SemanticEngine(bare), "ground")
    assert "Operator knowledge" in b and "A. Duty Manager, Duty manager, ORD" in b and "We plan 40 here." in b
    assert "Operator knowledge" not in render_brief(SemanticEngine(bare), "atc")  # scoped to the role
