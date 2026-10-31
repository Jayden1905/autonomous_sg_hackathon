"""Read-only HTTP surface for the semantic model, plus the live viewer.

Mounted from api.py with one line:  app.include_router(semantic_router)
Everything here is static per process (the model loads once), so it's cheap to call often.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .semantic import brief_for, default_engine, lookup
from .semantic.graph import default_graph
from .semantic.model import SEMANTIC_DIR, SemanticModel

semantic_router = APIRouter(prefix="/semantic", tags=["semantic model"])
_VIEWER = Path(__file__).resolve().parent.parent / "semantic" / "viewer.html"
_LEDGER = SEMANTIC_DIR / "elicitation.yaml"


@semantic_router.get("/", response_class=HTMLResponse, include_in_schema=False)
def viewer() -> HTMLResponse:
    """The ontology viewer. Open http://localhost:8000/semantic/ in a browser."""
    if not _VIEWER.exists():
        raise HTTPException(404, "viewer.html missing")
    return HTMLResponse(_VIEWER.read_text())


@semantic_router.get("/graph")
def graph() -> dict:
    """Nodes and edges of the whole model, with per-node detail for a hover/click panel."""
    return default_graph()


@semantic_router.get("/model", response_model=SemanticModel)
def model() -> SemanticModel:
    """The full curated+profiled model, as loaded."""
    return default_engine().model


@semantic_router.get("/brief/{role}")
def brief(role: Literal["atc", "pilot", "ground"]) -> dict:
    """The grounding text this agent receives in its system prompt."""
    return {"role": role, "brief": brief_for(role)}


@semantic_router.get("/lookup")
def lookup_term(term: str) -> dict:
    """What a term means in the model; `found` false when the model has no entry."""
    text = lookup(term)
    return {"term": term, "found": bool(text), "text": text or "not in the semantic model"}


@semantic_router.get("/check")
def check() -> dict:
    problems = default_engine().model.validate_references()
    return {"ok": not problems, "problems": problems}


# ── elicitation: the interview the FE can host ──

class AnswerIn(BaseModel):
    question_id: str
    by: str = Field(description="Operator id from the operators list")
    text: str = Field(description="The operator's words, verbatim")
    structured: dict | None = Field(default=None, description="Typed reading: params / new_rule / range_lo / aliases / vocabulary")
    confirmed: bool = Field(default=False, description="Operator confirmed the structured reading; only then it applies")
    action: Literal["answer", "confirm_default", "skip", "not_applicable"] = "answer"


@semantic_router.get("/elicitation")
def elicitation() -> dict:
    """Questions the documents left open, per role, with coverage and answers so far."""
    from .semantic import elicit
    m = default_engine().model
    e = elicit.load_ledger(_LEDGER)
    qs = e.questions or elicit.questions(m)
    return {"coverage": elicit.coverage(m), "operators": [o.model_dump() for o in e.operators],
            "questions": [q.model_dump() for q in qs], "answers": [a.model_dump() for a in e.answers],
            "protected_rules": sorted(elicit.protected_rules())}


@semantic_router.post("/elicitation/answer")
def answer(body: AnswerIn) -> dict:
    """Append an answer to the ledger. Confirmed structured answers apply on the next model load."""
    from .semantic import elicit
    from .semantic.engine import default_engine as _de
    m = SemanticModel.load(apply_operator_knowledge=False)
    try:
        a = elicit.record_answer(_LEDGER, m, body.question_id, body.by, body.text, structured=body.structured,
                                 confirmed=body.confirmed, action=body.action, via="api")
    except KeyError as ex:
        raise HTTPException(400, str(ex))
    _de.cache_clear()  # next brief / graph / rules read reflects the new knowledge
    return {"recorded": a.model_dump(), "coverage": elicit.coverage(SemanticModel.load())}
