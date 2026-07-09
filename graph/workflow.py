"""LangGraph workflow compilation and runner."""

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    classify_node,
    generate_node,
    greeting_node,
    orders_node,
    out_of_scope_node,
    policy_node,
    preprocess_node,
    product_search_node,
    route_after_classify,
)
from app.graph.state import ChatGraphState


def build_chat_graph():
    graph = StateGraph(ChatGraphState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("classify", classify_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("out_of_scope", out_of_scope_node)
    graph.add_node("orders", orders_node)
    graph.add_node("policy", policy_node)
    graph.add_node("product_search", product_search_node)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "classify")

    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "greeting": "greeting",
            "out_of_scope": "out_of_scope",
            "orders": "orders",
            "policy": "policy",
            "product_search": "product_search",
        },
    )

    for node in ("greeting", "out_of_scope", "orders"):
        graph.add_edge(node, END)

    graph.add_edge("policy", "generate")
    graph.add_edge("product_search", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


def build_pre_generate_graph():
    """Same graph, minus the final `generate` LLM call — policy/product_search
    end at the graph boundary instead of feeding into generate. Used by the
    streaming chat endpoint so the (fast) retrieval/classification work runs
    normally and only the final answer text is streamed token-by-token,
    outside the graph, by the caller."""
    graph = StateGraph(ChatGraphState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("classify", classify_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("out_of_scope", out_of_scope_node)
    graph.add_node("orders", orders_node)
    graph.add_node("policy", policy_node)
    graph.add_node("product_search", product_search_node)

    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "classify")

    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "greeting": "greeting",
            "out_of_scope": "out_of_scope",
            "orders": "orders",
            "policy": "policy",
            "product_search": "product_search",
        },
    )

    for node in ("greeting", "out_of_scope", "orders", "policy", "product_search"):
        graph.add_edge(node, END)

    return graph.compile()


_compiled_graph = None
_compiled_pre_generate_graph = None


def get_chat_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_chat_graph()
    return _compiled_graph


def get_pre_generate_graph():
    global _compiled_pre_generate_graph
    if _compiled_pre_generate_graph is None:
        _compiled_pre_generate_graph = build_pre_generate_graph()
    return _compiled_pre_generate_graph


def run_chat_graph(initial_state: ChatGraphState) -> ChatGraphState:
    return get_chat_graph().invoke(initial_state)


def run_pre_generate_graph(initial_state: ChatGraphState) -> ChatGraphState:
    """Runs everything except the final answer-generation LLM call.
    If the result already has an `answer` (greeting/orders/out_of_scope),
    that's the complete, final answer. Otherwise the caller is responsible
    for streaming the final LLM response via build_generate_chain_inputs/
    finalize_answer from app.graph.nodes."""
    return get_pre_generate_graph().invoke(initial_state)
