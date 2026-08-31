from app.examples import EXAMPLES
from app.main import _enforce_rubric
from app.rubric import evaluate_rubric
from app.schema import AssessRequest, AssessmentReport, RubricResult


def _req_from_example(ex_id: str, **overrides) -> AssessRequest:
    ex = next(e for e in EXAMPLES if e["id"] == ex_id)
    data = {**ex, **overrides}
    return AssessRequest(
        process_text=data["process_text"],
        industry=data.get("industry"),
        volume_note=data.get("volume_note"),
        tools_note=data.get("tools_note"),
        data_shape=data.get("data_shape", "unknown"),
        judgment_level=data.get("judgment_level", "unknown"),
    )


def test_ap_invoices_are_rules():
    result = evaluate_rubric(_req_from_example("ap-invoices"))
    assert result.classification == "rules"
    assert result.confidence == "clear"
    assert result.rules_score > result.ai_score
    assert result.veto_chatbot_for_rules is True


def test_support_inbox_is_ai():
    result = evaluate_rubric(_req_from_example("support-inbox"))
    assert result.classification == "ai"
    assert result.confidence == "clear"
    assert result.ai_score > result.rules_score
    assert result.veto_chatbot_for_rules is False


def test_claims_are_hybrid():
    result = evaluate_rubric(_req_from_example("insurance-claims"))
    assert result.classification == "hybrid"


def test_password_reset_is_rules_not_ai():
    result = evaluate_rubric(_req_from_example("password-reset"))
    assert result.classification == "rules"
    assert result.confidence == "clear"
    assert result.veto_chatbot_for_rules is True


def test_text_only_structured_keywords_still_lean_rules():
    req = AssessRequest(
        process_text=(
            "If the purchase order three-way match succeeds and the amount is under $1000, "
            "the ERP workflow always posts. Manager approval uses a checklist. Spreadsheet "
            "form fields are copied into SAP. Exceptions are rare."
        )
    )
    result = evaluate_rubric(req)
    assert result.classification in {"rules", "hybrid"}
    assert result.rules_score >= result.ai_score


def test_rubric_override_replaces_llm_classification_when_clear():
    rubric = RubricResult(
        classification="rules",
        confidence="clear",
        rules_score=0.9,
        ai_score=0.1,
        signals={},
        tags=["rules"],
        veto_chatbot_for_rules=True,
    )
    report = AssessmentReport(
        problem_diagnosis="d",
        automation_potential="a",
        recommended_solution="r",
        solution_architecture="s",
        expected_business_impact="i",
        implementation_complexity="c",
        implementation_complexity_band="Low",
        key_risks=["k"],
        recommended_mvp_scope="m",
        next_implementation_steps=["n"],
        classification="ai",
        classification_rationale="The model preferred a chatbot.",
    )
    fixed = _enforce_rubric(report, rubric)
    assert fixed.classification == "rules"
    assert "Rubric override" in fixed.classification_rationale
