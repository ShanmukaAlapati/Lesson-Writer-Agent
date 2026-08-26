from langgraph.graph import END, StateGraph

from .nodes import make_evaluate_node, make_finalize_node, make_generate_node, make_router
from .state import LessonState


def build_graph(
    generate_llm,
    evaluate_llm,
    memory,
    *,
    max_retries,
    max_tokens_generate,
    max_tokens_evaluate,
    output_dir,
):
    g = StateGraph(LessonState)
    g.add_node("generate", make_generate_node(generate_llm, max_tokens_generate))
    g.add_node("evaluate", make_evaluate_node(evaluate_llm, max_tokens_evaluate))
    g.add_node("finalize", make_finalize_node(memory, output_dir))

    g.set_entry_point("generate")
    g.add_edge("generate", "evaluate")
    g.add_conditional_edges("evaluate", make_router(max_retries), {
        "regenerate": "generate",
        "finalize": "finalize",
    })
    g.add_edge("finalize", END)
    return g.compile()
