Self-Evaluating Lesson Content Generator

An agentic system that generates a beginner lesson for a topic, judges it against a rubric it enforces on itself, and regenerates until the lesson clears the bar — or the retry budget runs out and it ships its best attempt with a full log of what it tried.

Built for: GenAI Engineer – Content Systems, take-home assessment. Submission topic: Introduction to RAG.

Architecture
                 ┌───────────┐
      input ───▶ │ GENERATE  │ ◀────────────────┐
                 └─────┬─────┘                   │
                       │                         │
                       │  (any check FAILED,     │
                       ▼   retries remain)        │
                 ┌───────────┐                   │
                 │ EVALUATE  │ ──────────────────┘
                 └─────┬─────┘
                       │
                       │  all PASSED, or
                       │  retries exhausted
                       ▼
                 ┌───────────┐
                 │ FINALIZE  │ ──▶ output/<topic>/lesson_final.md
                 └───────────┘ ──▶ output/<topic>/rejection_log.json
app.py                 entry point: wires config, logging, provider, memory, graph
config.py              typed, validated settings (pydantic-settings)
exceptions.py          typed error hierarchy
logging_config.py      plain-text logs with run-id correlation
rubric.py              the 7 pass/fail checkpoints + plain-dict judge output validation
demo_catch.py          one-off script: feeds the evaluator a deliberately broken lesson
llm/
├── openrouter_provider.py   OpenRouter (via OpenAI SDK) implementation [commented out]
└── groq_provider.py         Groq SDK implementation (active)
memory/
└── store.py             SQLite-backed cross-run memory
pipeline/
├── state.py              graph state type
├── nodes.py              generate / evaluate / finalize, as dependency-injected factories
└── graph.py              LangGraph assembly
Design decisions & trade-offs

This section answers "why this structure, these components, this evaluator, these trade-offs" — each choice below was a deliberate response to a specific failure mode in a simpler version of this system.

Hard pass/fail rubric, not a 1–10 score. A scored rubric lets a mediocre lesson "average out" to a passing grade, and gives no clean signal for when to stop retrying. Seven binary checkpoints make the loop's exit condition unambiguous: any single FAIL forces another attempt.

Judge output is checked before it's trusted, not just json.loads'd. json.loads succeeds on syntactically valid JSON that's still semantically wrong — a misspelled checkpoint id, a missing checkpoint, "Pass" instead of "PASS". Any of those would silently corrupt all_passed and ship bad content with nobody noticing. validate_judge_output() catches that and turns it into an explicit JudgeOutputParseError, and evaluate_node gets one bounded retry (2 attempts) specifically for a malformed judge response — a different failure mode from the lesson itself failing the rubric, so it isn't charged against the content's own retry budget.

That retry is adaptive, not a blind repeat of the same call: the provider returns finish_reason alongside the response text, so evaluate_node can tell why the previous attempt failed. If the judge response was cut off (finish_reason == "length"), the retry doubles max_tokens instead of resending the identical request that will just run out of room again. If the response finished but wasn't valid JSON (markdown fences, missing fields, commentary), the retry instead appends the specific validation error and an explicit "raw JSON only" instruction to the prompt. Two different failure modes, two different fixes, instead of hoping the same request succeeds on a second roll of the dice.

LLM calls go through a .complete(system, user, max_tokens) method, not scattered SDK calls. Every node depends only on that method, and the one class implementing it (llm/groq_provider.py, calling Groq directly through the Groq SDK) is the only place that imports groq. openrouter_provider.py is retained (commented out) for easy switching back.

Generation and evaluation use separate provider instances, with independent API keys. build_graph(generate_llm, evaluate_llm, ...) takes two providers, not one shared client. config.py resolves GROQ_GENERATE_API_KEY / GROQ_EVALUATE_API_KEY independently, each falling back to a shared GROQ_API_KEY if unset — so one key still works with zero extra config, but nothing stops the evaluator from running on a different account, rate limit, or even a different (stronger) model than the one that wrote the lesson. That independence matters here specifically: an evaluator sharing infrastructure with its own generator is a weaker check than one that doesn't.

Two separate feedback mechanisms, not one. Within a run, a failed attempt's specific reasons are fed straight back into the next generation prompt. Across runs, memory/store.py tracks which checkpoints fail most often across every topic ever generated, and warns the very first draft of a brand-new topic about the system's own recurring mistakes before it writes a word. The second mechanism is what makes the pipeline self-evolving rather than merely self-correcting within a single request.

SQLite for cross-run memory, not a flat JSON file. A JSON file has a real correctness bug at any real scale: two runs finishing around the same time both read-modify-write the file, and one run's failures silently clobber the other's. SQLite gives atomic inserts for free with zero added operational burden — one file, no server — which is the right amount of "database" for the property actually being protected here.

Nodes are dependency-injected factories (make_generate_node(llm, ...)), not module-level functions using a global client. Each node takes its LLM/memory/config dependencies as arguments instead of reaching for a global client — the same reason a web handler takes a DB connection as an argument instead of importing one at module scope.

Max 2 retries, hard cap. The brief asks for a loop that always terminates. The cap also reflects a real cost/latency constraint: "keep trying forever" is not a shippable production pattern.

Log lines carry a run_id, not print(). If this pipeline generates 500 lessons overnight and one produces a bad result, grepping one run_id should surface its entire generate → evaluate → regenerate history, not just whatever happened to scroll past in a terminal.

Audience constraints are enforced at both ends. The target learner (12th-grade graduate, limited English vocabulary, non-English-medium schooling) is written directly into both the generator's system prompt and the "Beginner-Friendly Language" rubric checkpoint — so it's judged, not just requested.

What was deliberately left out, and why

A genuinely "enterprise" build of this system — service mesh, multi-tenant auth, a managed vector DB, Kubernetes manifests, a full observability stack — would be the wrong scope for a graded take-home evaluating judgment on a content-generation problem. The choices above (validated structured output, retry/backoff, real persistence, dependency injection enabling real tests, structured logs) are what a senior engineer adds when a prototype needs to become trustworthy; the rest would be infrastructure nobody asked for.

What I'd add with more time
Multiple judge passes with self-consistency voting on borderline verdicts (right now a single judge call is trusted as ground truth).
A held-out set of lessons with known injected errors, to measure the evaluator's own precision/recall rather than trusting it on faith.
Diff-aware regeneration (patch only the failing section instead of rewriting the whole lesson on every retry).
Memory schema (pitfalls.db)

Two tables, created automatically on first run by memory/store.py.

rubric_failures — every failed checkpoint from every attempt, across all topics. This is what get_common_pitfalls() aggregates to warn new generations about recurring mistakes.

id	run_id	topic	check_id	reason	created_at
1	62b49fb0014f	use of reranker in agentic rag	no_unexplained_jargon	Uses "cross-encoder" and "cosine similarity" without defining them	2026-08-26 18:59:29
2	18c2125e9835	use of reranker in agentic rag	topic_specificity	Lesson stays generic about RAG and never explains reranking specifically	2026-08-26 19:06:45

lessons — every shipped lesson (the best attempt of each run), with its final grading result. Not read by anything yet — groundwork for a future "has a similar topic already been generated?" lookup.

id	run_id	topic	lesson (truncated)	all_passed	pass_count	total_checks	failed_checks (JSON)	total_attempts	best_attempt
1	e2808632f723	use of reranker in agentic rag	"# Reranking in Agentic RAG\n\n..."	1	7	7	[]	2	1
2	27a65aecf589	Explain Embeddings	"# What Are Embeddings?\n\n..."	1	7	7	[]	2	1
Setup
bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # then fill in GROQ_GENERATE_API_KEY and GROQ_EVALUATE_API_KEY
Run

Generate a lesson interactively:

bash
python app.py

You will be prompted to enter the topic:

Enter a topic to generate a lesson for: RAG (Retrieval-Augmented Generation)

Outputs land in output/<topic>/lesson_final.md (the best-scoring lesson — the passing one, or the highest-scoring attempt if retries ran out) and output/<topic>/rejection_log.json (what failed, why, what changed on retry, and which attempt was shipped). Each topic gets its own subfolder, so generating a second topic doesn't overwrite the first.

Cross-run memory accumulates in pitfalls.db (repo root) — both the recurring-pitfall stats used by the generator, and a full record of every shipped lesson (topic, lesson text, pass count, failed checks) for future topic-lookup/reuse.

Run the evaluator-catches-an-error demo:

bash
python demo_catch.py

This feeds the evaluator a lesson with a deliberately wrong definition of RAG and undefined jargon, and prints each checkpoint's verdict — a reliable, reproducible way to show the evaluator rejecting bad content, independent of live-generation randomness.
