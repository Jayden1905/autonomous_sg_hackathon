import json
from pathlib import Path

from fastapi.testclient import TestClient

from atc_negotiation.api import app

SAMPLE = json.loads((Path(__file__).parent.parent / "scenarios" / "sample_weather.json").read_text())
client = TestClient(app)


def test_health_and_scenarios():
    assert client.get("/health").json()["status"] == "ok"
    ids = [s["scenario_id"] for s in client.get("/scenarios").json()]
    assert "sample-weather-ORD" in ids
    assert client.get("/scenarios/sample-weather-ORD").json()["flight"] == "UA1234"
    assert client.get("/scenarios/nope").status_code == 404


def test_evaluate_serialises_feasible_and_cost():
    body = {"scenario": SAMPLE, "proposal": {"arrival_min": 50, "runway": "27L", "gate": "B12", "rationale": ""}}
    ev = client.post("/evaluate", json=body).json()
    assert ev["feasible"] is False
    assert isinstance(ev["cost"], (int, float))
    assert any(r["rule"] == "runway_open" and not r["passed"] for r in ev["results"])


def test_fallback_endpoint():
    ev = client.post("/fallback", json=SAMPLE).json()["evaluation"]
    assert ev["feasible"] is True


def test_negotiate_mock_blocking():
    tr = client.post("/negotiate", json={"scenario": SAMPLE, "mock": True}).json()
    assert tr["outcome"] in ("consensus", "fallback")
    assert tr["final_evaluation"]["feasible"] is True


def test_negotiate_mock_stream_event_order():
    with client.stream("POST", "/negotiate/stream", json={"scenario": SAMPLE, "mock": True}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "started"
    assert events[-1] == "done"
    assert events[1:4] == ["thinking", "proposal", "evaluation"]
    assert "turn_complete" in events
    # every data line is valid JSON
    for line in body.splitlines():
        if line.startswith("data: "):
            json.loads(line[6:])


def test_openapi_includes_stream_event_schemas():
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("StreamEvents", "ThinkingEvent", "ProposalEvent", "EvaluationEvent",
                 "ResponseEvent", "NegotiationTrace", "TurnRecord", "ErrorEvent"):
        assert name in schemas, name
