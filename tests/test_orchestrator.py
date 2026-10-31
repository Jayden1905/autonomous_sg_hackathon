from pathlib import Path

from atc_negotiation.agents import MockAgent, make_agents
from atc_negotiation.orchestrator import negotiate
from atc_negotiation.schemas import AgentResponse, Proposal, Scenario, Verdict

SAMPLE = Path(__file__).parent.parent / "scenarios" / "sample_weather.json"
NO_OPTION = Path(__file__).parent.parent / "scenarios" / "sample_no_legal_option.json"


def load(path=SAMPLE):
    return Scenario.model_validate_json(path.read_text())


def test_no_legal_option_is_reported_not_invented():
    tr = negotiate(load(NO_OPTION), make_agents(mock=True))
    assert tr.outcome == "no_legal_option"
    assert not tr.final_evaluation.feasible
    assert tr.final_evaluation.hard_failures
    assert "human decision" in tr.fallback_reason


def test_mock_negotiation_converges_within_three_turns():
    tr = negotiate(load(), make_agents(mock=True))
    assert len(tr.turns) <= 3
    assert tr.final_evaluation.feasible


class YesMan(MockAgent):
    """Accepts anything. Must not be able to push an illegal plan through."""

    def respond(self, s, p, ev, ctx):
        return AgentResponse(verdict=Verdict.ACCEPT)


class StubbornATC(MockAgent):
    def propose(self, s, feedback, ctx):
        return Proposal(arrival_min=22, runway="27L", gate="B14", rationale="closed runway")


def test_unanimous_accept_on_infeasible_plan_is_vetoed():
    agents = {"atc": StubbornATC("atc"), "pilot": YesMan("pilot"), "ground": YesMan("ground")}
    tr = negotiate(load(), agents)
    assert tr.outcome == "fallback"
    assert all(t.vetoed_accepts == ["pilot", "ground"] for t in tr.turns)
    assert tr.final_evaluation.feasible
    assert tr.final.runway != "27L"
