from app import db
from app.memory import (
    evidence_weight,
    quality_status_for_feedback,
    relevance_score,
    retrieve_lessons,
)
from app.rubric import extract_tags, tokenize


def _seed_lesson(
    conn,
    *,
    process_text: str,
    outcome: str,
    quality_status: str = "usable",
    weight: float = 0.9,
    scope: str = "company",
    pattern: str = "rules",
    implemented: str = "Posted invoices with a three-way match workflow in the ERP.",
    why: str = "The deterministic match rate was high enough that a chatbot added no value.",
):
    tags = extract_tags(process_text, extra=[pattern, "invoice"])
    aid = db.insert_assessment(
        conn,
        process_text=process_text,
        industry="Manufacturing",
        volume_note=None,
        tools_note=None,
        data_shape="structured",
        judgment_level="rare",
        rubric_class=pattern,
        rubric_confidence="clear",
        rubric_json={"classification": pattern},
        assessment_json={"classification": pattern},
        tags=tags,
        memory_lesson_ids=[],
        memory_conflict=False,
    )
    db.upsert_lesson(
        conn,
        assessment_id=aid,
        outcome=outcome,
        implemented_what=implemented,
        what_worked="Match rate improved." if outcome == "worked" else "",
        what_failed="Vendors still emailed PDFs." if outcome == "did_not_work" else "",
        why=why,
        alternative="",
        scope=scope,
        quality_status=quality_status,
        tags=tags,
        process_text=process_text,
        recommended_pattern=pattern,
        weight=weight,
    )
    return aid


INVOICE = (
    "Supplier invoices post into SAP when the purchase order three-way match succeeds. "
    "Amounts under a threshold go to a checklist manager approval. Spreadsheet form fields."
)

EMAIL = (
    "Agents read unstructured customer emails, interpret intent, and classify tickets. "
    "Natural language, PDFs, and ambiguous requests fill the inbox."
)


def test_relevance_ignores_outcome(tmp_path):
    text = INVOICE
    tags = set(extract_tags(text, extra=["rules", "invoice"]))
    tokens = tokenize(text)
    worked = relevance_score(tags, tokens, tags, text, "company")
    failed = relevance_score(tags, tokens, tags, text, "company")
    assert worked == failed
    assert worked > 0.5


def test_held_and_discarded_are_not_retrieved(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_lesson(conn, process_text=INVOICE, outcome="worked", quality_status="held")
    _seed_lesson(conn, process_text=INVOICE, outcome="did_not_work", quality_status="discarded")
    memory = retrieve_lessons(conn, process_text=INVOICE, tags=["rules", "invoice"])
    assert memory.used is False
    assert memory.lesson_count == 0
    conn.close()


def test_low_weight_is_excluded(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_lesson(conn, process_text=INVOICE, outcome="worked", weight=0.2)
    memory = retrieve_lessons(conn, process_text=INVOICE, tags=["rules", "invoice"])
    assert memory.lesson_count == 0
    conn.close()


def test_unrelated_text_not_retrieved(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_lesson(conn, process_text=EMAIL, outcome="worked", pattern="ai")
    memory = retrieve_lessons(conn, process_text=INVOICE, tags=["rules", "invoice"])
    assert memory.lesson_count == 0
    conn.close()


def test_retrieval_caps_at_three_and_mixes_outcomes(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for i in range(3):
        _seed_lesson(
            conn,
            process_text=INVOICE + f" Clerk team {i} uses SAP purchase order matching.",
            outcome="worked",
            implemented=f"Rules engine rollout {i} for three-way match and threshold approval.",
        )
    _seed_lesson(
        conn,
        process_text=INVOICE + " Same SAP purchase order match with manager checklist.",
        outcome="did_not_work",
        implemented="Tried an LLM to post invoices; it hallucinated PO numbers.",
        why="Unstructured model guesses failed against structured ERP form fields and policy.",
    )
    memory = retrieve_lessons(conn, process_text=INVOICE, tags=["rules", "invoice", "sap"])
    assert 1 <= memory.lesson_count <= 3
    outcomes = {lesson.outcome for lesson in memory.lessons}
    assert "worked" in outcomes
    assert "did_not_work" in outcomes
    assert memory.conflict is True
    assert memory.attribution is not None
    assert "similar previous" in memory.attribution
    conn.close()


def test_short_feedback_is_held():
    assert quality_status_for_feedback("x", "", "", "no") == "held"
    assert (
        quality_status_for_feedback(
            "Implemented the SAP three-way match workflow",
            "Match rate rose for PO invoices",
            "",
            "The deterministic rules already encoded policy.",
        )
        == "usable"
    )


def test_weight_depends_on_substance_not_outcome():
    kwargs = dict(
        implemented_what="Rolled out a rules engine for invoice matching against PO and amount.",
        what_worked="Straight-through posting increased for exact matches.",
        what_failed="Manual handling remained for missing POs.",
        why="Structured ERP fields already contained the decision data.",
        alternative="",
    )
    assert evidence_weight(**kwargs) == evidence_weight(**kwargs)
    thin = evidence_weight("Did a thing here ok", "", "", "Too brief actually", "")
    assert evidence_weight(**kwargs) > thin


def test_llm_cannot_write_lessons_schema_is_feedback_only(tmp_path):
    """Lessons are only created via upsert_lesson (feedback path), not from assessment JSON."""
    conn = db.connect(tmp_path / "t.db")
    db.insert_assessment(
        conn,
        process_text=INVOICE,
        industry=None,
        volume_note=None,
        tools_note=None,
        data_shape="structured",
        judgment_level="rare",
        rubric_class="rules",
        rubric_confidence="clear",
        rubric_json={},
        assessment_json={"classification": "rules", "please_save_lesson": True},
        tags=["rules"],
        memory_lesson_ids=[],
        memory_conflict=False,
    )
    rows = conn.execute("SELECT COUNT(*) AS n FROM lessons").fetchone()
    assert rows["n"] == 0
    conn.close()
