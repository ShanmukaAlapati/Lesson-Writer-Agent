"""
Cross-run memory: the self-evolving piece of the pipeline, distinct from
the within-run regenerate loop.

Rationale for SQLite over a flat JSON file: a JSON file has a real
correctness bug at any real scale -- two runs finishing around the same
time both read-modify-write the file and one run's failures silently
clobber the other's. SQLite gives atomic inserts for free with zero
added operational burden (it's one file, no server to run), which is
the right amount of "database" for what's being tested here: a real
correctness property, not premature infrastructure.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from typing import Iterable, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rubric_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    check_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    lesson TEXT NOT NULL,
    all_passed INTEGER NOT NULL,
    pass_count INTEGER NOT NULL,
    total_checks INTEGER NOT NULL,
    failed_checks TEXT NOT NULL,
    total_attempts INTEGER NOT NULL,
    best_attempt INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class MemoryStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path, timeout=10)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record_failures(self, run_id: str, topic: str, failed_checks: Iterable[Tuple[str, str]]) -> None:
        """failed_checks: iterable of (check_id, reason)."""
        rows = [(run_id, topic, check_id, reason) for check_id, reason in failed_checks]
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO rubric_failures (run_id, topic, check_id, reason) VALUES (?, ?, ?, ?)",
                rows,
            )

    def save_lesson(self, run_id: str, topic: str, lesson: str, checks: list,
                     total_attempts: int, best_attempt: int) -> None:
        """
        Persist the shipped lesson plus its full grading result. Not read
        by anything yet -- this is groundwork for a future "has a similar
        topic already been generated?" lookup, so it stores everything
        that lookup would need: the topic, the lesson text itself, how
        well it scored, and exactly which checks failed and why.
        """
        all_passed = all(c["verdict"] == "PASS" for c in checks)
        pass_count = sum(1 for c in checks if c["verdict"] == "PASS")
        failed_checks = [
            {"id": c["id"], "name": c["name"], "reason": c["reason"]}
            for c in checks if c["verdict"] == "FAIL"
        ]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO lessons (run_id, topic, lesson, all_passed, pass_count, "
                "total_checks, failed_checks, total_attempts, best_attempt) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, topic, lesson, int(all_passed), pass_count, len(checks),
                 json.dumps(failed_checks), total_attempts, best_attempt),
            )

    def get_common_pitfalls(self, min_occurrences: int = 2, top_n: int = 3) -> Optional[str]:
        """
        Surface checkpoints that have failed often across ALL past runs and
        topics, with one representative reason each, formatted for direct
        injection into the generator's system prompt on a brand-new topic.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT check_id, COUNT(*) as n FROM rubric_failures "
                "GROUP BY check_id HAVING n >= ? ORDER BY n DESC LIMIT ?",
                (min_occurrences, top_n),
            ).fetchall()
            if not rows:
                return None

            lines = []
            for check_id, n in rows:
                reason_row = conn.execute(
                    "SELECT reason FROM rubric_failures WHERE check_id = ? ORDER BY id DESC LIMIT 1",
                    (check_id,),
                ).fetchone()
                reason = reason_row[0] if reason_row else "repeated failure"
                lines.append(f"- {check_id} (failed {n}x historically): '{reason}' -- do not repeat this.")
            return "\n".join(lines)
