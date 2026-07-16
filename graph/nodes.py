"""LangGraph node implementations — dual DB, SQL note matching, French responses."""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from app.rag.constants import POLICY_INTENTS, ChatIntent
from app.rag.intent_classifier import classify_intent, intent_to_response_type
from app.rag.preprocess import preprocess_query
from app.rag.prompts import OUT_OF_SCOPE_PROMPT, PERFUME_ASSISTANT_PROMPT
from app.rag.vector_store import search_knowledge_base, search_shopify_products
from app.graph.state import ChatGraphState
from app.services.recommendation_pipeline import resolve_products_for_query

logger = logging.getLogger("uvicorn.error")


def preprocess_node(state: ChatGraphState) -> ChatGraphState:
    raw = state.get("query", "")
    state["query"] = preprocess_query(raw)
    logger.info("[GRAPH] preprocess | raw=%r -> clean=%r", raw, state["query"])
    state["pipeline_path"] = "preprocess"
    return state


def classify_node(state: ChatGraphState) -> ChatGraphState:
    titles = [p.get("title", "") for p in state.get("last_shown_products", []) if p.get("title")]
    clf = classify_intent(
        state["query"],
        state["oai_api_key"],
        model=state.get("model_name", "gpt-4o-mini"),
        history=state.get("history"),
        last_shown_titles=titles,
    )
    state["intent"] = clf.intent
    state["intent_detail"] = clf.model_dump()
    state["pipeline_path"] = f"classify:{clf.intent}"
    logger.info(
        "[GRAPH] classify | intent=%s confidence=%s intl_ref=%s own=%s gender=%s price=[%s,%s] compare=%s newest=%s",
        clf.intent, clf.confidence, clf.is_international_reference, clf.is_own_product,
        clf.gender_preference, clf.min_price, clf.max_price, clf.compare_products, clf.is_newest_query,
    )
    return state


def route_after_classify(state: ChatGraphState) -> str:
    intent = state.get("intent", ChatIntent.GENERAL.value)
    if intent == ChatIntent.GREETING.value:
        return "greeting"
    if intent == ChatIntent.OUT_OF_SCOPE.value:
        return "out_of_scope"
    if intent in (ChatIntent.ORDERS.value, ChatIntent.ORDER_MANAGEMENT.value):
        return "orders"
    if intent in POLICY_INTENTS:
        return "policy"
    return "product_search"


def greeting_node(state: ChatGraphState) -> ChatGraphState:
    brand = state.get("brand_name", "Assistant")
    state["answer"] = {
        "type": "general",
        "message": (
            f"Bonjour ! Je suis {brand}, votre assistant Parfums Star. "
            "Comment puis-je vous aider à trouver votre parfum idéal aujourd'hui ?"
        ),
        "products": [],
        "show_products": False,
        "show_contact": False,
        "escalation_note": "",
        "contact_url": state.get("contact_url", ""),
        "detected_intent": ChatIntent.GREETING.value,
    }
    state["pipeline_path"] = "greeting"
    return state


def out_of_scope_node(state: ChatGraphState) -> ChatGraphState:
    llm = ChatOpenAI(model=state["model_name"], api_key=state["oai_api_key"], temperature=0.3)
    chain = OUT_OF_SCOPE_PROMPT | llm
    resp = chain.invoke({"query": state["query"]})
    state["answer"] = {
        "type": "general",
        "message": resp.content,
        "products": [],
        "show_products": False,
        "show_contact": False,
        "escalation_note": "",
        "contact_url": state.get("contact_url", ""),
        "detected_intent": ChatIntent.OUT_OF_SCOPE.value,
    }
    state["pipeline_path"] = "out_of_scope"
    return state


def orders_node(state: ChatGraphState) -> ChatGraphState:
    from app.services.chat_legacy import handle_order_intent

    answer = handle_order_intent(
        query=state["query"],
        store=state["store"],
        db=state.get("_db"),
        customer_id=state.get("customer_id"),
        customer_email=state.get("customer_email"),
        thread_id=state.get("thread_id"),
        contact_url=state.get("contact_url", ""),
        intent_detail=state.get("intent_detail", {}),
    )
    if answer.get("message"):
        answer["message"] = _ensure_french_prefix(answer["message"])
    answer["detected_intent"] = state.get("intent", ChatIntent.ORDERS.value)
    state["answer"] = answer
    state["pipeline_path"] = "orders"
    return state


def policy_node(state: ChatGraphState) -> ChatGraphState:
    hits = search_knowledge_base(
        state["index"],
        state["embeddings"],
        state["query"],
        state["store_base_url"],
        top_k=5,
    )
    ctx_parts = []
    for h in hits[:5]:
        ctx_parts.append(f"[{h.get('namespace', 'info')}] {h.get('title', '')}: {h.get('description', '')[:400]}")
    state["knowledge_context"] = "\n".join(ctx_parts)
    state["shopify_products"] = []
    state["pipeline_path"] = f"policy:{state.get('intent')}"
    return state


def product_search_node(state: ChatGraphState) -> ChatGraphState:
    """Unified product search: Shopify direct OR international → SQL notes → Shopify only."""
    db = state.get("_db")
    intent = state.get("intent", "general")
    intent_detail = state.get("intent_detail", {})

    products, intl_ctx, path = resolve_products_for_query(
        db=db,
        query=state["query"],
        shop=state.get("shop", ""),
        index=state["index"],
        embeddings=state["embeddings"],
        store_base_url=state["store_base_url"],
        intent=intent,
        intent_detail=intent_detail,
    )

    # Policy / knowledge fallback — also covers product_knowledge_query, since
    # generic perfumery questions ("qu'est-ce que l'oud ?", ingredient/allergy
    # questions not tied to a specific product) previously got neither a
    # product match nor any store content and left the LLM with nothing.
    if intent in (
        ChatIntent.GENERAL.value,
        ChatIntent.RECOMMENDATION_SEARCH.value,
        ChatIntent.PRODUCT_KNOWLEDGE.value,
    ) and not products:
        kb = search_knowledge_base(
            state["index"], state["embeddings"],
            state["query"], state["store_base_url"], top_k=3,
        )
        state["knowledge_context"] = "\n".join(
            f"{h.get('title', '')}: {h.get('description', '')[:300]}" for h in kb[:3]
        )
        logger.info("[GRAPH] product_search | no products, used knowledge_base fallback (%s hits)", len(kb))

    state["shopify_products"] = products
    state["international_context"] = intl_ctx
    state["international_match"] = {"context_only": True} if intl_ctx else None
    state["pipeline_path"] = path
    logger.info(
        "[GRAPH] product_search done | path=%s shopify_products=%s titles=%s",
        path, len(products), [(p.get("title") or "")[:30] for p in products[:5]],
    )
    return state


def build_generate_chain_inputs(state: ChatGraphState) -> dict:
    """Builds the prompt-variable dict for the final answer LLM call.
    Shared by the synchronous graph node and the streaming chat endpoint
    so both produce identical prompts."""
    products = state.get("shopify_products") or []
    is_comparison = state.get("pipeline_path") == "comparison"
    products_ctx = ""
    for i, p in enumerate(products[:5], 1):
        note_info = ", ".join(filter(None, [
            p.get("top_note"), p.get("heart_note"), p.get("base_note"), p.get("olfactive"),
        ]))
        gender_line = f"   Genre: {p['gender']}\n" if p.get("gender") else ""
        # Notes alone don't cover attribute questions (allergies, sensitive
        # skin, longevity, season/occasion, gift-worthiness) — those live in
        # free-text description, which used to only appear when notes were
        # entirely missing. Always include a short snippet alongside notes.
        desc = (p.get("description") or "")[:220]
        desc_line = f"   Description: {desc}\n" if desc else ""
        label = f"Parfum {chr(64 + i)}" if is_comparison else str(i)
        products_ctx += (
            f"\n{label}. {p.get('title', '')} — {p.get('price', 0)}€\n"
            f"   Notes: {note_info or 'non précisées'}\n"
            f"{desc_line}"
            f"{gender_line}"
            f"   URL: {p.get('product_url', '')}\n"
        )

    history_text = ""
    for m in (state.get("history") or [])[-4:]:
        history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]}\n"

    return {
        "brand_name": state.get("brand_name", "Assistant"),
        "store_name": state.get("store_name", state.get("shop", "")),
        "tone": state.get("tone", "professional"),
        "contact_url": state.get("contact_url", ""),
        "query": state["query"],
        "intent": state.get("intent", "general"),
        "international_context": state.get("international_context", ""),
        "products_context": products_ctx or "Aucun produit spécifique trouvé.",
        "knowledge_context": state.get("knowledge_context", ""),
        "history": history_text,
    }


def finalize_answer(state: ChatGraphState, message_text: str) -> dict:
    """Assembles the final answer dict (text + product cards) once the LLM
    message is known. Cards and text never repeat the same info twice —
    the prompt instructs the LLM not to restate price/URL, since those are
    only ever rendered in the product cards below the message."""
    products = state.get("shopify_products") or []
    show_products = bool(products) and state.get("intent") not in POLICY_INTENTS
    resp_type = intent_to_response_type(state.get("intent", "general"))

    return {
        "type": resp_type,
        "message": message_text,
        "products": products if show_products else [],
        "show_products": show_products,
        "show_contact": state.get("intent_detail", {}).get("needs_escalation", False),
        "escalation_note": "",
        "contact_url": state.get("contact_url", ""),
        "detected_intent": state.get("intent"),
        "pipeline_path": state.get("pipeline_path"),
    }


def generate_node(state: ChatGraphState) -> ChatGraphState:
    if state.get("answer"):
        return state

    llm = ChatOpenAI(
        model=state.get("model_name", "gpt-4o-mini"),
        api_key=state["oai_api_key"],
        temperature=0.4,
    )
    chain = PERFUME_ASSISTANT_PROMPT | llm
    resp = chain.invoke(build_generate_chain_inputs(state))

    state["answer"] = finalize_answer(state, resp.content)
    return state


def _ensure_french_prefix(message: str) -> str:
    """Light touch — full French handled by prompts; orders use template text."""
    return message
