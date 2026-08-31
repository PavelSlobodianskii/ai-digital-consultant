from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.rubric import extract_tags, tokenize
from app.schema import LessonSummary, MemoryMeta

RELEVANCE_THRESHOLD = 0.12
MAX_LESSONS = 3
NEAR_TOP_DELTA = 0.12
MIN_EXPLAIN_CHARS = 40
MIN_IMPLEMENTED_CHARS = 8


@dataclass
class ScoredLesson:
    row: sqlite3.Row
    relevance: float
    tags: set[str]


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evidence_weight(
    implemented_what: str,
    what_worked: str,
    what_failed: str,
    why: str,
    alternative: str = "",
) -> float:
    """Quality of the write-up, independent of outcome."""
    impl = (implemented_what or "").strip()
    body = " ".join(
        [
            (what_worked or "").strip(),
            (what_failed or "").strip(),
            (why or "").strip(),
            (alternative or "").strip(),
        ]
    )
    weight = 0.35
    if len(impl) >= MIN_IMPLEMENTED_CHARS:
        weight += 0.2
    if len(body) >= MIN_EXPLAIN_CHARS:
        weight += 0.25
    if len(body) >= 120:
        weight += 0.1
    filled = sum(
        1
        for part in (what_worked, what_failed, why, alternative)
        if (part or "").strip()
    )
    weight += min(0.1, filled * 0.03)
    return round(min(1.0, weight), 3)


def quality_status_for_feedback(
    implemented_what: str,
    what_worked: str,
    what_failed: str,
    why: str,
) -> str:
    impl = (implemented_what or "").strip()
    explain = " ".join(
        [
            (what_worked or "").strip(),
            (what_failed or "").strip(),
            (why or "").strip(),
        ]
    )
    if len(impl) < MIN_IMPLEMENTED_CHARS or len(explain) < MIN_EXPLAIN_CHARS:
        return "held"
    return "usable"


def _row_tags(row: sqlite3.Row) -> set[str]:
    try:
        return set(json.loads(row["tags_json"] or "[]"))
    except json.JSONDecodeError:
        return set()


def relevance_score(
    query_tags: set[str],
    query_tokens: set[str],
    lesson_tags: set[str],
    lesson_text: str,
    scope: str,
) -> float:
    """Contextual similarity only. Outcome is not a factor."""
    lesson_tokens = tokenize(lesson_text)
    tag_s = jaccard(query_tags, lesson_tags)
    text_s = jaccard(query_tokens, lesson_tokens)
    score = 0.55 * tag_s + 0.45 * text_s
    if scope == "company":
        score += 0.02
    return round(min(1.0, score), 4)


def _select_diverse(candidates: list[ScoredLesson]) -> list[ScoredLesson]:
    if len(candidates) <= MAX_LESSONS:
        return candidates

    ranked = sorted(candidates, key=lambda c: (-c.relevance, -float(c.row["weight"])))
    top = ranked[0]
    high_band = [
        c
        for c in ranked
        if c.relevance >= top.relevance - NEAR_TOP_DELTA
        or c.relevance >= RELEVANCE_THRESHOLD
    ]

    selected: list[ScoredLesson] = []
    seen_outcomes: set[str] = set()
    selected_ids: set[int] = set()

    def take(item: ScoredLesson) -> None:
        item_id = int(item.row["id"])
        if item_id in selected_ids or len(selected) >= MAX_LESSONS:
            return
        selected.append(item)
        selected_ids.add(item_id)
        seen_outcomes.add(item.row["outcome"])

    take(top)

    # Prefer covering both successful and unsuccessful evidence among highly relevant items.
    success = {"worked", "partial"}
    failure = {"did_not_work"}
    for pool, needed in (
        (success, lambda: seen_outcomes.isdisjoint(success)),
        (failure, lambda: seen_outcomes.isdisjoint(failure)),
        ({"partial"}, lambda: "partial" not in seen_outcomes and len(selected) < MAX_LESSONS),
    ):
        if not needed():
            continue
        pick = next(
            (
                c
                for c in high_band
                if c.row["outcome"] in pool and int(c.row["id"]) not in selected_ids
            ),
            None,
        )
        if pick:
            take(pick)

    for c in ranked:
        if len(selected) >= MAX_LESSONS:
            break
        take(c)

    return selected[:MAX_LESSONS]


def detect_conflict(selected: list[ScoredLesson]) -> tuple[bool, str | None]:
    if len(selected) < 2:
        return False, None
    outcomes = {c.row["outcome"] for c in selected}
    patterns = {
        (c.row["recommended_pattern"] or "").strip()
        for c in selected
        if (c.row["recommended_pattern"] or "").strip()
    }
    has_success = bool(outcomes & {"worked", "partial"})
    has_fail = "did_not_work" in outcomes
    pattern_clash = len(patterns) > 1
    if has_success and has_fail:
        note = (
            "Similar past cases disagree: at least one succeeded and one failed. "
            "A single failure is not a universal negative rule."
        )
        return True, note
    if pattern_clash:
        return True, "Similar past cases recommended different solution patterns."
    return False, None


def retrieve_lessons(
    conn: sqlite3.Connection,
    *,
    process_text: str,
    tags: list[str],
) -> MemoryMeta:
    query_tags = set(tags) | set(extract_tags(process_text))
    query_tokens = tokenize(process_text)
    scored: list[ScoredLesson] = []
    for row in conn.execute(
        "SELECT * FROM lessons WHERE quality_status = 'usable'"
    ).fetchall():
        lesson_tags = _row_tags(row)
        rel = relevance_score(
            query_tags,
            query_tokens,
            lesson_tags,
            row["process_text"] or "",
            row["scope"] or "company",
        )
        quality = float(row["weight"] or 0)
        if rel < RELEVANCE_THRESHOLD:
            continue
        if quality < 0.4:
            continue
        scored.append(ScoredLesson(row=row, relevance=rel, tags=lesson_tags))

    selected = _select_diverse(scored)
    conflict, conflict_note = detect_conflict(selected)
    summaries = [
        LessonSummary(
            id=int(c.row["id"]),
            outcome=c.row["outcome"],
            scope=c.row["scope"],
            implemented_what=c.row["implemented_what"] or "",
            what_worked=c.row["what_worked"] or "",
            what_failed=c.row["what_failed"] or "",
            why=c.row["why"] or "",
            alternative=c.row["alternative"] or "",
            relevance=c.relevance,
            created_at=c.row["created_at"] or "",
        )
        for c in selected
    ]
    used = len(summaries) > 0
    n = len(summaries)
    attribution = None
    if used:
        attribution = (
            f"Based partly on lessons from {n} similar previous case"
            f"{'s' if n != 1 else ''}."
        )
    return MemoryMeta(
        used=used,
        lesson_count=n,
        attribution=attribution,
        conflict=conflict,
        conflict_note=conflict_note if conflict else None,
        lessons=summaries,
    )


def lesson_prompt_block(memory: MemoryMeta) -> str:
    if not memory.used:
        return "No prior organizational lessons were retrieved for this case."
    lines = [
        "Retrieved organizational lessons (retrieval-based memory, not model training).",
        "Use as context only. Do not treat any single outcome as a universal rule.",
        "A failed case is evidence about that attempt, not a ban on the pattern.",
        "A successful case is evidence about that attempt, not a mandate to copy it.",
    ]
    if memory.conflict and memory.conflict_note:
        lines.append(f"CONFLICT: {memory.conflict_note}")
    for i, lesson in enumerate(memory.lessons, 1):
        lines.append(
            f"\nLesson {i} (id={lesson.id}, outcome={lesson.outcome}, "
            f"scope={lesson.scope}, relevance={lesson.relevance:.2f}):"
        )
        lines.append(f"- Implemented: {lesson.implemented_what}")
        if lesson.what_worked:
            lines.append(f"- Worked: {lesson.what_worked}")
        if lesson.what_failed:
            lines.append(f"- Failed: {lesson.what_failed}")
        if lesson.why:
            lines.append(f"- Why: {lesson.why}")
        if lesson.alternative:
            lines.append(f"- Alternative suggested: {lesson.alternative}")
    return "\n".join(lines)
