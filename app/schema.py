from typing import Literal

from pydantic import BaseModel, Field

Classification = Literal["rules", "ai", "hybrid"]
Confidence = Literal["clear", "unclear"]
Outcome = Literal["worked", "partial", "did_not_work"]
Scope = Literal["company", "general"]
QualityStatus = Literal["usable", "held", "discarded"]
Band = Literal["Low", "Medium", "High"]
DataShape = Literal["unknown", "structured", "unstructured", "mixed"]
JudgmentLevel = Literal["unknown", "rare", "frequent"]


class AssessRequest(BaseModel):
    process_text: str = Field(min_length=20, max_length=12000)
    industry: str | None = None
    volume_note: str | None = None
    tools_note: str | None = None
    data_shape: DataShape = "unknown"
    judgment_level: JudgmentLevel = "unknown"


class FeedbackRequest(BaseModel):
    assessment_id: int
    outcome: Outcome
    implemented_what: str = Field(min_length=1, max_length=4000)
    what_worked: str = ""
    what_failed: str = ""
    why: str = ""
    alternative: str = ""
    company_specific: bool = True


class AssessmentReport(BaseModel):
    problem_diagnosis: str
    automation_potential: str
    recommended_solution: str
    solution_architecture: str
    expected_business_impact: str
    implementation_complexity: str
    implementation_complexity_band: Band
    key_risks: list[str]
    recommended_mvp_scope: str
    next_implementation_steps: list[str]
    classification: Classification
    classification_rationale: str


class LessonSummary(BaseModel):
    id: int
    outcome: Outcome
    scope: Scope
    implemented_what: str
    what_worked: str
    what_failed: str
    why: str
    alternative: str
    relevance: float
    created_at: str


class MemoryMeta(BaseModel):
    used: bool
    lesson_count: int
    attribution: str | None = None
    conflict: bool = False
    conflict_note: str | None = None
    lessons: list[LessonSummary] = Field(default_factory=list)


class RubricResult(BaseModel):
    classification: Classification
    confidence: Confidence
    rules_score: float
    ai_score: float
    signals: dict[str, float]
    tags: list[str]
    veto_chatbot_for_rules: bool = False
