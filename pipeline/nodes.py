import json
import logging
import re

from exceptions import JudgeOutputParseError
from rubric import RUBRIC, RUBRIC_NAMES, validate_judge_output

logger = logging.getLogger(__name__)

_JUDGE_PARSE_ATTEMPTS = 2  # separate from content-regeneration retries


def _extract_json_array(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in judge output")
    return json.loads(match.group(0))


def make_generate_node(llm, max_tokens):
    def generate_node(state):
        attempt = len(state["rejection_log"])  # 0 = first draft, 1/2 = retries

        feedback_block = ""
        if attempt > 0:
            last_failed = state["rejection_log"][-1]["failed_checks"]
            feedback_block = (
                "\n\nYour previous attempt FAILED these checks -- fix them specifically:\n"
                + "\n".join(f"- {c['name']}: {c['reason']}" for c in last_failed)
            )

        pitfalls_block = ""
        if state.get("common_pitfalls") and attempt == 0:
            pitfalls_block = (
                "\n\nThis system has seen these recurring mistakes in past lessons "
                "on OTHER topics. Avoid repeating them:\n" + state["common_pitfalls"]
            )

        system = (
            "You create beginner learning content. Write for a 12th-grade graduate "
            "from India with limited English vocabulary, non-English-medium schooling, "
            "and zero background in AI or programming. Write only the lesson. Do not "
            "add meta-commentary."
        )

        user = (
            f"Create a standalone beginner lesson on: {state['topic']}\n\n"
            "Assume the learner starts from zero. Teach what it is, why it matters, "
            "and how it works. Use short sentences and simple words. Define each "
            "technical word in plain language when first used. Include at least one "
            "clear worked example. Keep a logical flow and end with a short recap."
            f"{feedback_block}{pitfalls_block}"
        )

        response = llm.complete(system, user, max_tokens)
        state["lesson"] = response["text"]
        logger.info(
            "generate_node run_id=%s attempt=%d topic=%r",
            state["run_id"], attempt, state["topic"],
        )
        return state

    return generate_node


def make_evaluate_node(llm, max_tokens):
    checklist_text = "\n".join(
        f'{i + 1}. id="{c["id"]}" name="{c["name"]}": {c["description"]}'
        for i, c in enumerate(RUBRIC)
    )
   
    system = (
        "You are a strict quality evaluator for beginner AI lessons. The learner "
        "is a 12th-grade graduate from India with limited English vocabulary, "
        "non-English-medium schooling, and zero AI or programming knowledge. "
        "Judge every checkpoint as PASS or FAIL. There is no partial credit. "
        "Return only valid JSON."
    )

    def evaluate_node(state):
        base_user = (
            f"CHECKLIST:\n{checklist_text}\n\nLESSON TO JUDGE:\n{state['lesson']}\n\n"
            "Return exactly this JSON array format:\n"
            '[{"id":"check_id","verdict":"PASS or FAIL","reason":"short clear reason"}]'
        )

        judge_output = None
        last_error = None
        user = base_user
        attempt_max_tokens = max_tokens
        for parse_attempt in range(_JUDGE_PARSE_ATTEMPTS):
            response = llm.complete(system, user, attempt_max_tokens)
            try:
                raw = _extract_json_array(response["text"])
                validate_judge_output(raw)
                judge_output = raw
                break
            except (ValueError, KeyError) as exc:
                last_error = exc
                raw_text = (response.get("text") or "")[:300]
                logger.warning(
                    "evaluate_node run_id=%s judge output failed validation (attempt %d): %s "
                    "-- raw response started with: %r",
                    state["run_id"], parse_attempt, exc, raw_text,
                )
                if response.get("finish_reason") == "length":
                    attempt_max_tokens = attempt_max_tokens * 2
                    user = base_user
                else:
                    user = (f"Topic: {state['topic']}\n\n"
                    "Evaluate this lesson against every checkpoint below. A lesson passes "
                    "only when every checkpoint passes.\n\n"
                    f"{checklist_text}\n\n"
                    "Lesson:\n"
                    f"{state['lesson']}\n\n"
                    "Return exactly this JSON array format:\n"
                    '[{"id":"check_id","verdict":"PASS or FAIL","reason":"short clear reason"}]'
                    )

        if judge_output is None:
            raise JudgeOutputParseError(
                f"Judge output did not validate after {_JUDGE_PARSE_ATTEMPTS} attempts: {last_error}"
            )

        checks = [
            {
                "id": v["id"],
                "name": RUBRIC_NAMES.get(v["id"], v["id"]),
                "verdict": v["verdict"],
                "reason": v["reason"],
            }
            for v in judge_output
        ]
        state["checks"] = checks
        state["all_passed"] = all(c["verdict"] == "PASS" for c in checks)

        pass_count = sum(1 for c in checks if c["verdict"] == "PASS")
        history = state.setdefault("attempt_history", [])
        history.append({
            "attempt": len(history),
            "lesson": state["lesson"],
            "checks": checks,
            "pass_count": pass_count,
        })

        if not state["all_passed"]:
            failed = [c for c in checks if c["verdict"] == "FAIL"]
            state["rejection_log"].append({
                "attempt": len(state["rejection_log"]),
                "failed_checks": failed,
            })

        failed_ids = [c["id"] for c in checks if c["verdict"] == "FAIL"]
        logger.info(
            "evaluate_node run_id=%s all_passed=%s failed=%d failed_checks=%s",
            state["run_id"], state["all_passed"],
            len(failed_ids), failed_ids,
        )
        return state

    return evaluate_node


def make_router(max_retries):
    def route(state):
        if state["all_passed"]:
            return "finalize"
        if len(state["rejection_log"]) > max_retries:
            return "finalize"  # loop must terminate even if still failing
        return "regenerate"

    return route

def make_finalize_node(memory, output_dir):
    import os
    import re
    import json

    def finalize_node(state):
        topic_slug = re.sub(r"[^a-z0-9]+", "_", state["topic"].lower()).strip("_") or "topic"
        run_output_dir = os.path.join(output_dir, topic_slug)
        os.makedirs(run_output_dir, exist_ok=True)

        # Pick the highest-scoring attempt, not just the last one -- on a
        # tie, prefer the later attempt.
        history = state.get("attempt_history", [])
        best = max(history, key=lambda a: (a["pass_count"], a["attempt"]))
        state["lesson"] = best["lesson"]
        state["checks"] = best["checks"]
        state["output_path"] = run_output_dir

        # FIXED: Added encoding="utf-8" to handle Unicode characters safely
        with open(os.path.join(run_output_dir, "lesson_final.md"), "w", encoding="utf-8") as f:
            f.write(best["lesson"])

        total_attempts = len(history)
        status = "PASSED" if state["all_passed"] else (
            f"MAX RETRIES REACHED -- shipping best attempt "
            f"(attempt {best['attempt']}, {best['pass_count']}/{len(best['checks'])} checks passed)"
        )

        # FIXED: Added encoding="utf-8" to handle Unicode character safe dumping
        with open(os.path.join(run_output_dir, "rejection_log.json"), "w", encoding="utf-8") as f:
            json.dump({
                "run_id": state["run_id"],
                "topic": state["topic"],
                "final_status": status,
                "total_attempts": total_attempts,
                "best_attempt": best["attempt"],
                "rejection_history": state["rejection_log"],
                "final_checks": best["checks"],
            }, f, indent=2, ensure_ascii=False) # Added ensure_ascii=False to keep logs clean and readable

        all_failed = [
            (c["id"], c["reason"]) for r in state["rejection_log"] for c in r["failed_checks"]
        ]
        if all_failed:
            memory.record_failures(state["run_id"], state["topic"], all_failed)

        memory.save_lesson(
            state["run_id"], state["topic"], best["lesson"], best["checks"],
            total_attempts, best["attempt"],
        )

        logger.info(
            "finalize_node run_id=%s status=%s total_attempts=%d best_attempt=%d",
            state["run_id"], status, total_attempts, best["attempt"],
        )
        return state

    return finalize_node

# ---------------------------------------------------------------------------
# Deliberate-error demo fixture (used by demo_catch.py)
# ---------------------------------------------------------------------------
DELIBERATELY_BROKEN_LESSON = """
# Introduction to RAG

RAG stands for Rapid Application Generation, a framework Google invented in 2019
to let neural networks compile themselves. It leverages stochastic backpropagation
across the latent manifold to instantiate emergent heuristics.

RAG is used everywhere. It is very good. You should use RAG.
"""
