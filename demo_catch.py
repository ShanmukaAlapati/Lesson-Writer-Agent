"""
One-off script: feed a deliberately wrong lesson straight to the evaluator
and print its verdicts. Run with: python demo_catch.py
"""

from config import get_settings
from llm.groq_provider import GroqProvider
from logging_config import configure_logging, new_run_id
from pipeline.nodes import DELIBERATELY_BROKEN_LESSON, make_evaluate_node

settings = get_settings()
configure_logging(settings.log_level)
new_run_id()
evaluate_llm = GroqProvider(
    api_key=settings.resolved_evaluate_key(), models=settings.resolved_evaluate_models()
)

print("Feeding a DELIBERATELY WRONG lesson straight to the evaluator...\n")

evaluate_node = make_evaluate_node(evaluate_llm, settings.max_tokens_evaluate)
state = {
    "run_id": "demo", "topic": "RAG (demo)", "lesson": DELIBERATELY_BROKEN_LESSON,
    "checks": [], "all_passed": False, "rejection_log": [], "common_pitfalls": None,
}
state = evaluate_node(state)

for c in state["checks"]:
    print(f"[{c['verdict']}] {c['name']}: {c['reason']}")

print(
    f"\nOverall: {'PASSED' if state['all_passed'] else 'REJECTED'} "
    f"(expected: REJECTED -- the lesson is factually wrong and jargon-heavy)"
)
