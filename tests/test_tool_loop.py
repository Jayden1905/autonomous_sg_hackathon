"""The agent tool loop, semantic grounding and the SQL guard, with a scripted fake client: no API calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from atc_negotiation.agents import (ActionContext, AgentError, Depth, LLMAgent, Resources, history_brief,
                                    make_agents)
from atc_negotiation.grounding import Grounder, Ledger
from atc_negotiation.metrics import MetricError, build_catalog
from atc_negotiation.orchestrator import negotiate
from atc_negotiation.rules import evaluate
from atc_negotiation.schemas import Evidence, Proposal, RunStats, Scenario, Verdict
from atc_negotiation.semantic import default_engine as semantic_engine
from atc_negotiation.semantic import lookup
from atc_negotiation.sqlengine import SqlEngine, SqlError, dataset_available
from atc_negotiation.tools import Toolbox

SAMPLE = Path(__file__).parent.parent / "scenarios" / "sample_weather.json"
needs_data = pytest.mark.skipif(not dataset_available(), reason="data/*.csv not present; run `make data`")


def load():
    return Scenario.model_validate_json(SAMPLE.read_text())


def tool_use(name, inp, id_):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id_)


def reply(*blocks):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)
    return SimpleNamespace(content=list(blocks), stop_reason="tool_use", usage=usage)


class FakeClient:
    """Replays scripted replies and keeps every request it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})  # the loop appends after the call
        return self.replies.pop(0)


def ctx(calls, history=()):
    return ActionContext(turn=1, history=list(history), record=calls.append, stats=RunStats())


def semantic_resources(**kw):
    return Resources(lookup=lookup, semantic=semantic_engine(), **kw)


def test_propose_runs_lookup_tools_then_submits():
    s = load()
    plan = {"arrival_min": 33, "runway": "27R", "gate": "B14", "rationale": "r [1]",
            "evidence": [{"claim": "plan passes the rule engine", "source": "check_proposal"},
                         {"claim": "final reserve is 30 min", "source": "rule:pilot.final_reserve_fuel"}]}
    client = FakeClient([
        reply(tool_use("check_proposal", {"arrival_min": 33, "runway": "27R", "gate": "B14"}, "t1"),
              tool_use("lookup_concept", {"term": "nonsense-term"}, "t2")),
        reply(tool_use("submit_proposal", plan, "t3")),
    ])
    agent = LLMAgent("atc", semantic_resources(), client=client, depth=Depth.none())
    calls = []
    p = agent.propose(s, None, ctx(calls))
    assert (p.arrival_min, p.runway, p.gate) == (33, "27R", "B14")
    assert all(e.grounded for e in p.evidence)
    assert [c.tool for c in calls] == ["check_proposal", "lookup_concept"]
    assert "Rule engine verdict" in calls[0].output
    assert any(r.startswith("rule:") for r in calls[0].model_refs)  # rule results carry model ids
    assert "not in the semantic model" in calls[1].output
    # the system prompt carries the semantic model's grounding for this role
    assert "Grounding for the ATC agent" in client.requests[0]["system"][0]["text"]
    # both results go back in ONE user message, matched by id
    results = client.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]


def test_counter_without_plan_is_rejected_and_retried():
    s = load()
    good = {"verdict": "accept", "objections": [], "counter": None, "evidence": []}
    client = FakeClient([
        reply(tool_use("submit_response", {"verdict": "counter", "objections": ["x"], "counter": None,
                                           "evidence": []}, "t1")),
        reply(tool_use("submit_response", good, "t2")),
    ])
    agent = LLMAgent("pilot", Resources(), client=client, depth=Depth.none())
    p = Proposal(arrival_min=33, runway="27R", gate="B14", rationale="")
    r = agent.respond(s, p, evaluate(s, p), ctx([]))
    assert r.verdict == Verdict.ACCEPT
    rejection = client.requests[1]["messages"][-1]["content"][0]
    assert rejection["is_error"] and "counter is null" in rejection["content"]


def test_step_budget_is_enforced():
    s = load()
    loop = reply(tool_use("check_proposal", {"arrival_min": 33, "runway": "27R", "gate": "B14"}, "t"))
    agent = LLMAgent("atc", Resources(), client=FakeClient([loop] * 3), max_steps=3, depth=Depth.none())
    with pytest.raises(AgentError, match="within 3 steps"):
        agent.propose(s, None, ctx([]))


def test_history_reaches_the_next_turn():
    s = load()
    tr = negotiate(s, make_agents(mock=True, resources=Resources()))
    text = history_brief(tr.turns)
    assert "Turn 1: atc proposed" in text
    assert "objection:" in text or "accept" in text


def test_ungrounded_evidence_gets_one_repair_round():
    s = load()
    invented = {"arrival_min": 33, "runway": "27R", "gate": "B14", "rationale": "r [1]",
                "evidence": [{"claim": "ORD taxi-in median 9 min", "source": "metric:taxi_in"},
                             {"claim": "ICAO says so", "source": "passage:made-up"}]}
    fixed = {**invented, "evidence": [{"claim": "wake rule applies", "source": "rule:atc.wake_separation"}]}
    client = FakeClient([reply(tool_use("submit_proposal", invented, "t1")),
                         reply(tool_use("submit_proposal", fixed, "t2"))])
    agent = LLMAgent("atc", semantic_resources(), client=client, depth=Depth.none())
    p = agent.propose(s, None, ctx([]))
    rejection = client.requests[1]["messages"][-1]["content"][0]
    assert rejection["is_error"]
    assert "was not queried this action" in rejection["content"]  # cited a metric it never retrieved
    assert "passage 'made-up' is not in the semantic model" in rejection["content"]
    assert [e.source for e in p.evidence] == ["rule:atc.wake_separation"] and p.evidence[0].grounded


def test_still_ungrounded_after_repair_is_kept_but_flagged():
    s = load()
    bad = {"arrival_min": 33, "runway": "27R", "gate": "B14", "rationale": "r [1]",
           "evidence": [{"claim": "made up", "source": "metric:taxi_in"}]}
    client = FakeClient([reply(tool_use("submit_proposal", bad, "t1")), reply(tool_use("submit_proposal", bad, "t2"))])
    p = LLMAgent("atc", semantic_resources(), client=client, depth=Depth(min_metrics=0, min_lookups=0,
                 check_submitted_plan=False, max_repairs=1)).propose(s, None, ctx([]))
    assert p.evidence[0].grounded is False  # the UI shows it as unverified


def test_grounder_resolves_model_references():
    g, led = Grounder(semantic_engine(), load()), Ledger(metrics_queried={"taxi_in"})
    ok = ["metric:taxi_in", "rule:atc.wake_separation", "code:DelayCause.WEATHER_DELAY", "scenario:fuel_endurance_min"]
    for src in ok:
        assert g.check(Evidence(claim="x", source=src), led) is None, src
    for src in ["metric:arrival_delay", "metric:nope", "rule:nope", "code:DelayCause.NOPE", "scenario:nope",
                "check_proposal", "run_sql", "my memory"]:
        assert g.check(Evidence(claim="x", source=src), led) is not None, src


def test_unavailable_data_is_a_tool_error_not_a_crash():
    out = Toolbox(scenario=load(), sql=None, lookup=None).run("query_metric", {"metric": "taxi_in"})
    assert out.is_error and "not loaded" in out.output


@needs_data
def test_sql_engine_is_read_only():
    eng = SqlEngine()
    assert eng.query("SELECT count(*) FROM airlines").rows[0][0] > 0
    for bad in ("DROP TABLE flights", "SELECT 1; SELECT 2", "SELECT * FROM read_csv('/etc/passwd')",
                "COPY airlines TO '/tmp/x.csv'"):
        with pytest.raises(SqlError):
            eng.query(bad)
    big = eng.query("SELECT * FROM flights", max_rows=5)
    assert len(big.rows) == 5 and big.truncated


@needs_data
def test_query_metric_only_answers_what_the_model_defines():
    cat = build_catalog(semantic_engine())
    assert {"taxi_in", "weather_delay_min", "arrival_delay"} <= set(cat.metrics)
    assert "on_time" not in cat.metrics  # derived by formula, not a column
    sql, params = cat.compile("taxi_in", {"destination": "ord", "arrival_hour": [17, 19]}, [])
    assert "TAXI_IN" in sql and params == ["ORD", 17, 19]  # values bound, never interpolated
    for bad in [("fuel_burn", {}, []), ("taxi_in", {"gate": "B1"}, []), ("taxi_in", {"month": "jan"}, []),
                ("taxi_in", {"destination": "x' OR 1=1 --"}, [])]:
        try:
            sql, params = cat.compile(*bad)
        except MetricError:
            continue
        assert "OR 1=1" not in sql  # an injected code only ever lands in params
    tb = Toolbox(scenario=load(), sql=SqlEngine(), lookup=None, catalog=cat)
    out = tb.run("query_metric", {"metric": "taxi_in", "filters": {"destination": "ORD", "month": None},
                                  "group_by": []})
    assert not out.is_error and "metric:taxi_in" in out.output and out.sql_result.rows[0][0] > 0
    assert out.model_refs[0] == "metric:taxi_in" and "type:Flight.DESTINATION_AIRPORT" in out.model_refs
    assert tb.ledger.metrics_queried == {"taxi_in"}


@needs_data
def test_mock_negotiation_is_grounded_end_to_end():
    tr = negotiate(load(), make_agents(mock=True))
    calls = [c for t in tr.turns for c in t.tool_calls]
    assert any(c.tool == "query_metric" and c.sql_result and not c.is_error for c in calls)
    assert tr.stats.tool_calls == len(calls)
    ev = tr.turns[0].proposal.evidence
    assert any(e.source.startswith("metric:") for e in ev) and all(e.grounded for e in ev)


def test_submit_without_the_required_work_is_sent_back():
    s = load()
    plan = {"arrival_min": 33, "runway": "27R", "gate": "B14", "rationale": "r [1]",
            "evidence": [{"claim": "wake rule applies", "source": "rule:atc.wake_separation"}]}
    client = FakeClient([
        reply(tool_use("submit_proposal", plan, "t1")),  # no lookup, plan never checked
        reply(tool_use("lookup_concept", {"term": "atc.wake_separation"}, "t2"),
              tool_use("check_proposal", {"arrival_min": 33, "runway": "27R", "gate": "B14"}, "t3")),
        reply(tool_use("submit_proposal", plan, "t4")),
    ])
    agent = LLMAgent("atc", semantic_resources(), client=client, depth=Depth(min_metrics=0, min_lookups=1))
    calls = []
    p = agent.propose(s, None, ctx(calls))
    rejection = client.requests[1]["messages"][-1]["content"][0]["content"]
    assert "lookup_concept at least 1" in rejection and "check_proposal the exact plan" in rejection
    assert [c.tool for c in calls] == ["lookup_concept", "check_proposal"] and p.arrival_min == 33


def test_counter_must_be_the_plan_that_was_checked():
    s = load()
    p = Proposal(arrival_min=33, runway="27R", gate="B14", rationale="")
    counter = {"arrival_min": 40, "runway": "27R", "gate": "B12", "rationale": "r [1]",
               "evidence": [{"claim": "checked", "source": "check_proposal"}]}
    resp = {"verdict": "counter", "summary": "s [1]", "objections": ["x [1]"], "counter": counter,
            "evidence": [{"claim": "verdict shown", "source": "check_proposal"}]}
    client = FakeClient([
        reply(tool_use("check_proposal", {"arrival_min": 39, "runway": "27R", "gate": "B12"}, "t1")),
        reply(tool_use("submit_response", resp, "t2")),  # checked t+39, submits t+40
        reply(tool_use("check_proposal", {"arrival_min": 40, "runway": "27R", "gate": "B12"}, "t3")),
        reply(tool_use("submit_response", resp, "t4")),
    ])
    agent = LLMAgent("pilot", semantic_resources(), client=client, depth=Depth(min_metrics=0, min_lookups=0))
    r = agent.respond(s, p, evaluate(s, p), ctx([]))
    assert "t+40" in client.requests[2]["messages"][-1]["content"][0]["content"]
    assert r.counter.arrival_min == 40


@needs_data
def test_depth_requires_distinct_metrics():
    s = load()
    q = lambda m, id_: tool_use("query_metric", {"metric": m, "filters": {"destination": "ORD"}, "group_by": []}, id_)
    plan = {"arrival_min": 33, "runway": "27R", "gate": "B14", "rationale": "r [1]",
            "evidence": [{"claim": "checked", "source": "check_proposal"}]}
    client = FakeClient([
        reply(q("taxi_in", "a"), q("taxi_in", "b"),
              tool_use("check_proposal", {"arrival_min": 33, "runway": "27R", "gate": "B14"}, "c")),
        reply(tool_use("submit_proposal", plan, "d")),  # same metric twice is still one metric
        reply(q("arrival_delay", "e")),
        reply(tool_use("submit_proposal", plan, "f")),
    ])
    res = semantic_resources(sql=SqlEngine(), catalog=build_catalog(semantic_engine()))
    LLMAgent("ground", res, client=client, depth=Depth(min_metrics=2, min_lookups=0)).propose(s, None, ctx([]))
    assert "at least 2 different metrics (so far: taxi_in)" in client.requests[2]["messages"][-1]["content"][0]["content"]
    assert len(client.requests) == 4


def test_replies_carry_resolved_citations():
    s = load()
    plan = {"arrival_min": 33, "runway": "27R", "gate": "B14",
            "rationale": "Fuel stays above final reserve [1], and the plan passes every hard rule [2].",
            "evidence": [{"claim": "final reserve is 30 min", "source": "rule:pilot.final_reserve_fuel"},
                         {"claim": "feasible", "source": "check_proposal"}]}
    client = FakeClient([reply(tool_use("check_proposal", {"arrival_min": 33, "runway": "27R", "gate": "B14"}, "a")),
                         reply(tool_use("submit_proposal", plan, "b"))])
    p = LLMAgent("pilot", semantic_resources(), client=client, depth=Depth(min_metrics=0, min_lookups=0)).propose(
        s, None, ctx([]))
    assert [e.id for e in p.evidence] == [1, 2]
    c = p.evidence[0].citation
    assert c.kind == "rule" and c.ref == "pilot.final_reserve_fuel" and "30 minutes" in c.text
    assert c.passage_id and c.url  # rule cites its regulation passage
    assert p.evidence[1].citation.kind == "rule_engine"


def test_prose_without_valid_markers_is_sent_back():
    s = load()
    p = Proposal(arrival_min=33, runway="27R", gate="B14", rationale="")
    ev = [{"claim": "feasible", "source": "check_proposal"}]
    uncited = {"verdict": "accept", "summary": "Looks fine.", "objections": [], "counter": None, "evidence": ev}
    dangling = {**uncited, "summary": "Looks fine [4]."}
    good = {**uncited, "summary": "Feasible at no cost to my domain [1]."}
    client = FakeClient([reply(tool_use("submit_response", x, str(i))) for i, x in enumerate([uncited, dangling, good])])
    agent = LLMAgent("ground", semantic_resources(), client=client, depth=Depth(min_metrics=0, min_lookups=0))
    r = agent.respond(s, p, evaluate(s, p), ctx([]))
    msgs = [client.requests[i]["messages"][-1]["content"][0]["content"] for i in (1, 2)]
    assert "summary has no [n] citation markers" in msgs[0]
    assert "summary cites [4] but evidence has items 1..1" in msgs[1]
    assert r.summary.endswith("[1].") and r.evidence[0].id == 1


def test_mock_replies_are_cited():
    from atc_negotiation.grounding import markers
    tr = negotiate(load(), make_agents(mock=True, resources=semantic_resources()))
    for t in tr.turns:
        assert markers(t.proposal.rationale) and all(e.citation for e in t.proposal.evidence)
        for r in t.responses.values():
            assert markers(r.summary) and all(e.citation and e.grounded for e in r.evidence)


MOVES = Path(__file__).parent.parent / "scenarios" / "demo_storm_aa1453_moves.json"


def test_each_agent_sees_only_its_own_moves_until_one_is_on_the_table():
    from atc_negotiation.agents import _scenario_brief
    s = Scenario.model_validate_json(MOVES.read_text())
    atc, ground = _scenario_brief(s, "atc"), _scenario_brief(s, "ground")
    assert "atc.resequence_heavy" in atc and "ground.tow_a1" not in atc and "pilot.absorb_en_route" not in atc
    assert "ground.tow_a1" in ground and "atc.resequence_heavy" not in ground
    tr = negotiate(s, make_agents(mock=True, resources=Resources()), max_turns=1)
    tabled = Proposal(arrival_min=55, runway="27R", gate="A1", moves=["ground.tow_a1"], rationale="")
    later = _scenario_brief(s, "atc", [tr.turns[0].model_copy(update={"proposal": tabled})])
    assert "Moves other agents have put on the table:\n- ground.tow_a1" in later


@pytest.mark.xfail(strict=True, reason="limit changed to organisers' workbook; scenario was tuned to the earlier ICAO wake table")
def test_scripted_agents_combine_moves_from_two_owners():
    s = Scenario.model_validate_json(MOVES.read_text())
    tr = negotiate(s, make_agents(mock=True, resources=Resources()))
    assert tr.outcome == "consensus" and tr.final_evaluation.feasible
    assert {m.split(".")[0] for m in tr.final.moves} >= {"ground", "atc"}
    assert "moves ground.tow_a1" in history_brief(tr.turns)


def test_a_plan_with_moves_must_be_checked_with_those_moves():
    s = Scenario.model_validate_json(MOVES.read_text())
    tb = Toolbox(scenario=s, sql=None, lookup=None)
    tb.run("check_proposal", {"arrival_min": 56, "runway": "27R", "gate": "A1", "moves": []})
    agent = LLMAgent("atc", Resources(), client=SimpleNamespace(), depth=Depth(min_metrics=0, min_lookups=0))
    plan = Proposal(arrival_min=56, runway="27R", gate="A1", moves=["ground.tow_a1", "atc.resequence_heavy"],
                    rationale="")
    assert any("check_proposal the exact plan" in g for g in agent._depth_gaps(plan, tb))
    tb.run("check_proposal", {"arrival_min": 56, "runway": "27R", "gate": "A1",
                              "moves": ["atc.resequence_heavy", "ground.tow_a1"]})
    assert agent._depth_gaps(plan, tb) == []
