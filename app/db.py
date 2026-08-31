from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "consultant.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    process_text TEXT NOT NULL,
    industry TEXT,
    volume_note TEXT,
    tools_note TEXT,
    data_shape TEXT,
    judgment_level TEXT,
    rubric_class TEXT NOT NULL,
    rubric_confidence TEXT NOT NULL,
    rubric_json TEXT NOT NULL,
    assessment_json TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    memory_lesson_ids_json TEXT NOT NULL,
    memory_conflict INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    implemented_what TEXT NOT NULL,
    what_worked TEXT NOT NULL DEFAULT '',
    what_failed TEXT NOT NULL DEFAULT '',
    why TEXT NOT NULL DEFAULT '',
    alternative TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    process_text TEXT NOT NULL,
    recommended_pattern TEXT,
    weight REAL NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def insert_assessment(
    conn: sqlite3.Connection,
    *,
    process_text: str,
    industry: str | None,
    volume_note: str | None,
    tools_note: str | None,
    data_shape: str,
    judgment_level: str,
    rubric_class: str,
    rubric_confidence: str,
    rubric_json: dict,
    assessment_json: dict,
    tags: list[str],
    memory_lesson_ids: list[int],
    memory_conflict: bool,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO assessments (
            created_at, process_text, industry, volume_note, tools_note,
            data_shape, judgment_level, rubric_class, rubric_confidence,
            rubric_json, assessment_json, tags_json, memory_lesson_ids_json,
            memory_conflict
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now(),
            process_text,
            industry,
            volume_note,
            tools_note,
            data_shape,
            judgment_level,
            rubric_class,
            rubric_confidence,
            json.dumps(rubric_json),
            json.dumps(assessment_json),
            json.dumps(tags),
            json.dumps(memory_lesson_ids),
            1 if memory_conflict else 0,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_assessment(conn: sqlite3.Connection, assessment_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
    ).fetchone()


def list_usable_lessons(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM lessons WHERE quality_status = 'usable' ORDER BY created_at DESC"
    ).fetchall()


def upsert_lesson(
    conn: sqlite3.Connection,
    *,
    assessment_id: int,
    outcome: str,
    implemented_what: str,
    what_worked: str,
    what_failed: str,
    why: str,
    alternative: str,
    scope: str,
    quality_status: str,
    tags: list[str],
    process_text: str,
    recommended_pattern: str | None,
    weight: float,
) -> int:
    existing = conn.execute(
        "SELECT id FROM lessons WHERE assessment_id = ?", (assessment_id,)
    ).fetchone()
    now = utc_now()
    if existing:
        conn.execute(
            """
            UPDATE lessons SET
                created_at = ?, outcome = ?, implemented_what = ?,
                what_worked = ?, what_failed = ?, why = ?, alternative = ?,
                scope = ?, quality_status = ?, tags_json = ?, process_text = ?,
                recommended_pattern = ?, weight = ?
            WHERE assessment_id = ?
            """,
            (
                now,
                outcome,
                implemented_what,
                what_worked,
                what_failed,
                why,
                alternative,
                scope,
                quality_status,
                json.dumps(tags),
                process_text,
                recommended_pattern,
                weight,
                assessment_id,
            ),
        )
        conn.commit()
        return int(existing["id"])
    cur = conn.execute(
        """
        INSERT INTO lessons (
            assessment_id, created_at, outcome, implemented_what, what_worked,
            what_failed, why, alternative, scope, quality_status, tags_json,
            process_text, recommended_pattern, weight
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            now,
            outcome,
            implemented_what,
            what_worked,
            what_failed,
            why,
            alternative,
            scope,
            quality_status,
            json.dumps(tags),
            process_text,
            recommended_pattern,
            weight,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def set_lesson_discarded(conn: sqlite3.Connection, lesson_id: int) -> bool:
    cur = conn.execute(
        "UPDATE lessons SET quality_status = 'discarded' WHERE id = ?",
        (lesson_id,),
    )
    conn.commit()
    return cur.rowcount > 0
