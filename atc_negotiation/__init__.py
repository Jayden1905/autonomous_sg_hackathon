"""Three-agent (ATC / Pilot / Ground) negotiation over a flight disruption.

Hard rules live in `rules.py` and are plain code. The LLM agents in `agents.py`
only propose and object; they never decide whether a proposal is legal.
"""
