import sys

from config import get_settings
from exceptions import ConfigurationError, LessonAgentError
from llm.groq_provider import GroqProvider
from logging_config import configure_logging, new_run_id
from memory.store import MemoryStore
from pipeline.graph import build_graph


def main() -> None:
    topic = input("Enter a topic to generate a lesson for: ").strip()
    if not topic:
        sys.exit('Provide a topic, e.g. "RAG (Retrieval-Augmented Generation)"')

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        sys.exit(str(exc))

    configure_logging(settings.log_level)
    new_run_id()

    generate_llm = GroqProvider(
        api_key=settings.resolved_generate_key(), models=settings.resolved_generate_models()
    )
    evaluate_llm = GroqProvider(
        api_key=settings.resolved_evaluate_key(), models=settings.resolved_evaluate_models()
    )

    store = MemoryStore(settings.memory_db_path)
    graph = build_graph(
        generate_llm, evaluate_llm, store,
        max_retries=settings.max_retries,
        max_tokens_generate=settings.max_tokens_generate,
        max_tokens_evaluate=settings.max_tokens_evaluate,
        output_dir=settings.output_dir,
    )

    initial_state = {
        "run_id": new_run_id(),
        "topic": topic,
        "lesson": "",
        "checks": [],
        "all_passed": False,
        "rejection_log": [],
        "attempt_history": [],
        "common_pitfalls": store.get_common_pitfalls(),
    }

    try:
        final_state = graph.invoke(initial_state)
    except LessonAgentError as exc:
        sys.exit(f"Pipeline failed: {exc}")

    final_checks = final_state.get("checks", [])
    passed = [c for c in final_checks if c["verdict"] == "PASS"]
    failed = [c for c in final_checks if c["verdict"] == "FAIL"]
    total_attempts = len(final_state.get("attempt_history", []))
    out_path = final_state.get("output_path", settings.output_dir)

    # ── clean terminal summary ──────────────────────────────────────────────
    sep = "─" * 60
    if final_state["all_passed"]:
        print(f"\n{sep}")
        print(f"  ✅  LESSON PASSED  ({total_attempts} attempt{'s' if total_attempts != 1 else ''})")
        print(sep)
        print(f"  Topic   : {topic}")
        print(f"  Checks  : {len(passed)}/{len(final_checks)} passed")
        print(f"  Output  : {out_path}\\lesson_final.md")
        print(f"  Log     : {out_path}\\rejection_log.json")
        print(f"  Details : run.log")
        print(sep)
    else:
        # status = "PASSED" if final_state["all_passed"] else "MAX RETRIES REACHED"  # original single-line print
        # print(f"\n[{status}] see {final_state['output_path']}/lesson_final.md and rejection_log.json")
        print(f"\n{sep}")
        print(f"  ⚠️   MAX RETRIES REACHED  (shipped best of {total_attempts} attempts)")
        print(sep)
        print(f"  Topic   : {topic}")
        print(f"  Checks  : {len(passed)}/{len(final_checks)} passed")
        if failed:
            print(f"  Failed  :")
            for c in failed:
                print(f"    ✗ {c['name']}: {c['reason']}")
        print(f"  Output  : {out_path}\\lesson_final.md")
        print(f"  Log     : {out_path}\\rejection_log.json")
        print(f"  Details : run.log")
        print(sep)


if __name__ == "__main__":
    main()
