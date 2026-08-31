from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import db as dbmod
from app.examples import EXAMPLES
from app.llm import LlmError, generate_report, ollama_reachable
from app.memory import (
    evidence_weight,
    lesson_prompt_block,
    quality_status_for_feedback,
    retrieve_lessons,
)
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.rubric import evaluate_rubric, extract_tags
from app.schema import AssessRequest, AssessmentReport, FeedbackRequest

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="AI Digital Consultant", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@contextmanager
def get_conn():
    conn = dbmod.connect(os.environ.get("CONSULTANT_DB"))
    try:
        yield conn
    finally:
        conn.close()


def _enforce_rubric(report: AssessmentReport, rubric) -> AssessmentReport:
    if rubric.confidence == "clear" and report.classification != rubric.classification:
        report.classification = rubric.classification
        report.classification_rationale = (
            "(Rubric override) "
            + report.classification_rationale
            + f" Deterministic classification is {rubric.classification} "
            f"with {rubric.confidence} confidence and was not changed by the model or by memory."
        )
    else:
        report.classification = rubric.classification
    return report


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return ollama_reachable()


@app.get("/api/examples")
def examples():
    return EXAMPLES


@app.post("/api/assess")
def assess(req: AssessRequest):
    rubric = evaluate_rubric(req)
    with get_conn() as conn:
        memory = retrieve_lessons(conn, process_text=req.process_text, tags=rubric.tags)
        lesson_block = lesson_prompt_block(memory)
        try:
            report = generate_report(SYSTEM_PROMPT, build_user_prompt(req, rubric, lesson_block))
        except LlmError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        report = _enforce_rubric(report, rubric)
        payload = report.model_dump()
        assessment_id = dbmod.insert_assessment(
            conn,
            process_text=req.process_text,
            industry=req.industry,
            volume_note=req.volume_note,
            tools_note=req.tools_note,
            data_shape=req.data_shape,
            judgment_level=req.judgment_level,
            rubric_class=rubric.classification,
            rubric_confidence=rubric.confidence,
            rubric_json=rubric.model_dump(),
            assessment_json=payload,
            tags=rubric.tags,
            memory_lesson_ids=[lesson.id for lesson in memory.lessons],
            memory_conflict=memory.conflict,
        )
    return {
        "assessment_id": assessment_id,
        "report": payload,
        "rubric": {
            "classification": rubric.classification,
            "confidence": rubric.confidence,
            "rules_score": rubric.rules_score,
            "ai_score": rubric.ai_score,
            "authoritative": rubric.confidence == "clear",
        },
        "memory": memory.model_dump(),
        "disclaimer": (
            "This is retrieval-based organizational memory, not model fine-tuning. "
            "Impact figures are qualitative unless you provided volumes."
        ),
    }


@app.post("/api/feedback")
def feedback(body: FeedbackRequest):
    with get_conn() as conn:
        row = dbmod.get_assessment(conn, body.assessment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Assessment not found.")
        status = quality_status_for_feedback(
            body.implemented_what,
            body.what_worked,
            body.what_failed,
            body.why,
        )
        weight = evidence_weight(
            body.implemented_what,
            body.what_worked,
            body.what_failed,
            body.why,
            body.alternative,
        )
        extra_tags = extract_tags(
            " ".join(
                [
                    body.implemented_what,
                    body.what_worked,
                    body.what_failed,
                    body.why,
                    body.alternative,
                ]
            )
        )
        try:
            base_tags = json.loads(row["tags_json"] or "[]")
        except json.JSONDecodeError:
            base_tags = []
        tags = sorted(set(base_tags) | set(extra_tags))
        lesson_id = dbmod.upsert_lesson(
            conn,
            assessment_id=body.assessment_id,
            outcome=body.outcome,
            implemented_what=body.implemented_what.strip(),
            what_worked=body.what_worked.strip(),
            what_failed=body.what_failed.strip(),
            why=body.why.strip(),
            alternative=body.alternative.strip(),
            scope="company" if body.company_specific else "general",
            quality_status=status,
            tags=tags,
            process_text=row["process_text"],
            recommended_pattern=row["rubric_class"],
            weight=weight,
        )
    return {
        "lesson_id": lesson_id,
        "quality_status": status,
        "weight": weight,
        "stored": True,
        "message": (
            "Saved. This lesson will be retrieved for similar future cases."
            if status == "usable"
            else "Saved but held back from retrieval until the explanation is more complete "
            "(what you implemented, plus what worked / failed / why)."
        ),
    }


@app.post("/api/lessons/{lesson_id}/not-relevant")
def not_relevant(lesson_id: int):
    with get_conn() as conn:
        ok = dbmod.set_lesson_discarded(conn, lesson_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return {"discarded": True, "lesson_id": lesson_id}
