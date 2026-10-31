"""Human approval: nothing executes without an operator, and approval re-checks the rules."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atc_negotiation import decisions
from atc_negotiation.agents import make_agents
from atc_negotiation.api import app
from atc_negotiation.orchestrator import negotiate
from atc_negotiation.schemas import Scenario

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"
client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "LOG", tmp_path / "decisions.jsonl")
    monkeypatch.setattr(decisions, "_decisions", {})


def _create(name: str) -> tuple[dict, dict]:
    s = Scenario.model_validate_json((SCENARIOS / f"{name}.json").read_text())
    trace = negotiate(s, make_agents(mock=True))
    body = {"scenario": json.loads(s.model_dump_json()), "trace": json.loads(trace.model_dump_json())}
    r = client.post("/decisions", json=body)
    assert r.status_code == 201, r.text
    return r.json(), body


def test_consensus_waits_for_approval_and_nothing_is_executed_yet():
    d, _ = _create("demo_storm_ua599")
    assert d["status"] == "pending_approval"
    assert d["allowed_actions"] == ["approve", "reject"]
    assert d["executed"] == []
    assert [e["event"] for e in d["audit"]] == ["created"]


def test_approve_rechecks_then_executes_with_audit():
    d, _ = _create("demo_storm_ua599")
    r = client.post(f"/decisions/{d['decision_id']}/decide",
                    json={"action": "approve", "operator": "J. Tan (ORD tower)", "note": "agree, B6"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "executed" and d["simulated"] is True
    kinds = [a["kind"] for a in d["executed"]]
    assert kinds[0] == "slot_assigned" and "gate_assigned" in kinds
    assert d["audit"][-1] == {**d["audit"][-1], "by": "J. Tan (ORD tower)", "event": "approve"}
    assert d["allowed_actions"] == []
    # Closed: a second approval is refused.
    again = client.post(f"/decisions/{d['decision_id']}/decide", json={"action": "approve", "operator": "x"})
    assert again.status_code == 409


def test_approve_is_refused_when_the_situation_changed():
    d, body = _create("demo_storm_ua599")
    changed = body["scenario"]
    for rwy in changed["runways"]:
        if rwy["name"] == d["plan"]["runway"]:
            rwy["open"] = False  # the agreed runway closed after consensus
    r = client.post(f"/decisions/{d['decision_id']}/decide",
                    json={"action": "approve", "operator": "J. Tan", "scenario": changed})
    assert r.status_code == 409
    err = r.json()["detail"]
    assert "runway_open" in err["detail"] and err["evaluation"]["feasible"] is False
    after = client.get(f"/decisions/{d['decision_id']}").json()
    assert after["status"] == "pending_approval" and after["executed"] == []
    assert after["audit"][-1]["event"] == "approve_refused"


def test_no_legal_option_cannot_be_approved_only_diverted():
    d, _ = _create("demo_storm_vx204_divert")
    assert d["outcome"] == "no_legal_option" and d["status"] == "needs_human_decision"
    assert d["allowed_actions"] == ["divert", "reject"]
    assert client.post(f"/decisions/{d['decision_id']}/decide",
                       json={"action": "approve", "operator": "J. Tan"}).status_code == 409
    r = client.post(f"/decisions/{d['decision_id']}/decide",
                    json={"action": "divert", "operator": "J. Tan", "note": "divert to MDW"})
    assert r.json()["status"] == "diverted"
    assert r.json()["executed"][0]["kind"] == "divert_issued"


def test_reject_and_queue_filter():
    a, _ = _create("demo_storm_ua599")
    b, _ = _create("demo_storm_ua599")
    client.post(f"/decisions/{a['decision_id']}/decide", json={"action": "reject", "operator": "J. Tan"})
    queue = client.get("/decisions", params={"status": "pending_approval"}).json()
    assert [d["decision_id"] for d in queue] == [b["decision_id"]]
    assert client.get("/decisions/nope").status_code == 404


def test_operator_is_required():
    d, _ = _create("demo_storm_ua599")
    r = client.post(f"/decisions/{d['decision_id']}/decide", json={"action": "approve", "operator": ""})
    assert r.status_code == 422


def test_decisions_survive_a_reload():
    d, _ = _create("demo_storm_ua599")
    client.post(f"/decisions/{d['decision_id']}/decide", json={"action": "approve", "operator": "J. Tan"})
    decisions._decisions.clear()
    decisions._replay()
    assert decisions._decisions[d["decision_id"]].status == "executed"


def test_bad_trace_is_a_422():
    s = json.loads((SCENARIOS / "demo_storm_ua599.json").read_text())
    assert client.post("/decisions", json={"scenario": s, "trace": {"nope": 1}}).status_code == 422


def test_contract_type_names_unchanged():
    """Adding /decisions must not rename the FE's existing types to -Input/-Output."""
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("NegotiationTrace", "Evaluation", "TurnRecord", "AgentResponse", "Decision", "DecideRequest"):
        assert name in schemas, name
    # Proposal and Evidence were already split before /decisions existed (/evaluate takes a Proposal).
    split = {n for n in schemas if n.endswith(("-Input", "-Output"))}
    assert split <= {"Evidence-Input", "Proposal-Input", "Proposal-Output"}, split
