"""Impact must compare like with like and label every estimate."""

import json
from pathlib import Path

import pytest

from atc_negotiation import impact

ROOT = Path(__file__).parent.parent
FLIGHTS = ROOT / "data" / "flights.csv"
needs_data = pytest.mark.skipif(not FLIGHTS.exists(), reason="run `make data` first")


def _fake_trace(scenario_id, arrival_min, outcome="consensus", model="mock"):
    return {
        "scenario_id": scenario_id, "model": model, "started_at": "2026-10-31T00:00:00Z", "duration_s": 0.2,
        "turns": [], "outcome": outcome,
        "final": {"arrival_min": arrival_min, "runway": "27R", "gate": "A1", "rationale": ""},
        "final_evaluation": {"proposal": {"arrival_min": arrival_min, "runway": "27R", "gate": "A1", "rationale": ""},
                             "results": []},
        "fallback_reason": None,
    }


@needs_data
def test_floor_is_departure_delay_and_only_post_departure_is_compared(tmp_path):
    from atc_negotiation import data
    row = next(data.qualifying_rows(FLIGHTS, limit=1)); s = data.scenario_from_row(row)
    rec = int(float(s.source["ARRIVAL_DELAY"])); dep = s.earliest_arrival_min
    traces = tmp_path / "t.jsonl"
    traces.write_text(json.dumps(_fake_trace(s.scenario_id, dep + 3)) + "\n")
    rep = impact.build(traces, FLIGHTS)
    r = rep.rows[0]
    assert r.departure_delay == dep
    assert r.recorded_post_departure == max(0, rec - dep)
    assert r.negotiated_post_departure == 3 and r.holding_min == 3
    assert r.fuel_hold_kg_est == 3 * impact.HOLDING_BURN_KG_PER_MIN


@needs_data
def test_no_legal_option_is_counted_but_not_compared(tmp_path):
    from atc_negotiation import data
    rows = list(data.qualifying_rows(FLIGHTS, limit=2)); ss = [data.scenario_from_row(r) for r in rows]
    traces = tmp_path / "t.jsonl"
    traces.write_text(json.dumps(_fake_trace(ss[0].scenario_id, ss[0].earliest_arrival_min + 1)) + "\n"
                      + json.dumps(_fake_trace(ss[1].scenario_id, ss[1].earliest_arrival_min, outcome="no_legal_option")) + "\n")
    s = impact.build(traces, FLIGHTS).summary()
    assert s["n"] == 2 and s["compared"] == 1
    assert s["outcomes"]["no_legal_option"] == 1 and s["measured"]["declined_no_legal_option"] == 1


@needs_data
def test_summary_labels_measured_and_estimated_separately_and_carries_caveats(tmp_path):
    from atc_negotiation import data
    row = next(data.qualifying_rows(FLIGHTS, limit=1)); s = data.scenario_from_row(row)
    traces = tmp_path / "t.jsonl"
    traces.write_text(json.dumps(_fake_trace(s.scenario_id, s.earliest_arrival_min + 5)) + "\n")
    summary = impact.build(traces, FLIGHTS).summary()
    assert set(summary) >= {"measured", "estimated", "caveats"}
    assert summary["estimated"]["human_coordination"]["value"] is None  # we found no number; we do not invent one
    assert "basis" in summary["estimated"]["fuel_in_hold_kg_per_flight"]
    assert any("synthetic" in c for c in summary["caveats"])
    text = impact.render(summary)
    assert "MEASURED" in text and "ESTIMATED" in text and "CAVEATS" in text
    assert "not quantified" in text


@needs_data
def test_real_batch_file_if_present_reports_without_error():
    p = ROOT / "traces" / "batch_mock_200_operator.jsonl"
    if not p.exists():
        pytest.skip("no batch traces")
    rep = impact.build(p, FLIGHTS)
    assert rep.n == 200 and len(rep.compared) >= 190
    s = rep.summary()
    assert s["measured"]["reduction_min"]["median"] is not None
