# Rubric: hard pass/fail checkpoints for judging a lesson.
# Audience for every checkpoint: a 12th-grade graduate in India, with
# limited English vocabulary, from a non-English-medium schooling
# background, with zero prior exposure to AI/tech.

RUBRIC = [
    {
        "id": "accurate_grounded",
        "name": "Accurate & Grounded",
        "description": (
            "PASS only if all important factual claims are correct and the "
            "worked example is technically correct. FAIL if the lesson contains "
            "any incorrect, invented, or misleading claim."
        ),
    },
    {
        "id": "beginner_language",
        "name": "Beginner-Friendly Language",
        "description": (
            "PASS only if the lesson uses simple everyday English, mostly short "
            "sentences, and is understandable to a learner with limited English "
            "and no AI background. FAIL if it is dense, academic, or difficult."
        ),
    },
    {
        "id": "teaches_by_example",
        "name": "Teaches by Example",
        "description": (
            "PASS only if the lesson includes at least one concrete, worked "
            "example related directly to the requested topic. FAIL if it gives "
            "only definitions or an unrelated example."
        ),
    },
    {
        "id": "no_unexplained_jargon",
        "name": "No Unexplained Jargon",
        "description": (
            "PASS only if every technical term is explained in simple words "
            "when first used. Acronyms must be expanded and their important "
            "words must also be explained. FAIL if any important technical term "
            "is used without explanation."
        ),
    },
    {
        "id": "covers_key_points",
        "name": "Covers Key Points",
        "description": (
            "PASS only if the lesson clearly explains: what the topic is, why "
            "it matters or what problem it solves, and how it works step by step. "
            "FAIL if any one of these is missing."
        ),
    },
    {
        "id": "topic_specificity",
        "name": "Teaches the Exact Topic",
        "description": (
            "PASS only if the lesson teaches the exact requested topic. If the "
            "topic contains multiple concepts, it must explain each important "
            "concept and how they work together. FAIL if it mainly teaches only "
            "a broader related topic."
        ),
    },
    {
        "id": "coherent_flow",
        "name": "Coherent Teaching Flow",
        "description": (
            "PASS only if ideas appear in a logical order: why the topic matters, "
            "what it is, how it works, worked example, and recap. FAIL if the "
            "lesson jumps between ideas or leaves an important idea unfinished."
        ),
    },
]
RUBRIC_IDS = {c["id"] for c in RUBRIC}
RUBRIC_NAMES = {c["id"]: c["name"] for c in RUBRIC}


def validate_judge_output(verdicts):
    """Sanity-check the judge's parsed JSON. Raises ValueError if something's wrong."""
    if not isinstance(verdicts, list):
        raise ValueError("Judge output is not a list")

    seen_ids = set()
    for v in verdicts:
        if "id" not in v or "verdict" not in v or "reason" not in v:
            raise ValueError(f"Judge verdict missing a field: {v}")
        if v["id"] not in RUBRIC_IDS:
            raise ValueError(f"Unknown rubric checkpoint id: {v['id']}")
        if v["verdict"] not in ("PASS", "FAIL"):
            raise ValueError(f"Invalid verdict: {v['verdict']}")
        seen_ids.add(v["id"])

    missing = RUBRIC_IDS - seen_ids
    if missing:
        raise ValueError(f"Judge output missing checkpoints: {missing}")

    return verdicts
