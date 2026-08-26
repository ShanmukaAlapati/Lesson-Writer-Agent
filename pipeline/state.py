from typing import TypedDict


class LessonState(TypedDict):
    run_id: str
    topic: str
    lesson: str
    checks: list
    all_passed: bool
    rejection_log: list
    attempt_history: list
    common_pitfalls: str
    output_path: str
