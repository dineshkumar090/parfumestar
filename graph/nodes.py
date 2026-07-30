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
from app.services.product_grouping import (
    enrich_missing_variants,
    filter_promotional_products,
    group_same_perfume_products,
)
from app.services.recommendation_pipeline import resolve_products_for_query

logger = logging.getLogger("uvicorn.error")


def preprocess_node(state: ChatGraphState) -> ChatGraphState:
    raw = state.get("query", "")
    state["query"] = preprocess_query(raw)
    logger.info("[GRAPH] preprocess | raw=%r -> clean=%r", raw, state["query"])
    state["pipeline_path"] = "preprocess"
    return state


def classify_node(state: ChatGraphState) -> ChatGraphState:
    logger.info("[GRAPH] node=classify | query=%r", state.get("query"))
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
        route = "greeting"
    elif intent == ChatIntent.OUT_OF_SCOPE.value:
        route = "out_of_scope"
    elif intent in (ChatIntent.ORDERS.value, ChatIntent.ORDER_MANAGEMENT.value):
        route = "orders"
    elif intent in POLICY_INTENTS:
        route = "policy"
    else:
        route = "product_search"
    logger.info("[GRAPH] route_after_classify | intent=%s -> node=%s", intent, route)
    return route


def greeting_node(state: ChatGraphState) -> ChatGraphState:
    logger.info("[GRAPH] node=greeting")
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
    logger.info("[GRAPH] node=out_of_scope | query=%r", state.get("query"))
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
    logger.info("[GRAPH] node=orders | query=%r", state.get("query"))
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
    logger.info("[GRAPH] node=policy | intent=%s query=%r", state.get("intent"), state.get("query"))
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
    logger.info("[GRAPH] policy | knowledge_base hits=%s", len(hits))
    return state


# A "clarifying question" style message ("Is the perfume for a man or a
# woman?", "Day or evening wedding?") reads short in intent even though it
# can run 8-10 words once written as a full question — 12 comfortably
# covers that phrasing without also swallowing genuinely detailed requests.
_CURRENT_QUERY_MAX_WORDS = 12
# The PRIOR message must clearly be the substantial, topic-setting request
# (not just another short back-and-forth reply) to be worth blending in.
_PRIOR_MESSAGE_MIN_WORDS = 6


def _build_context_aware_search_query(state: ChatGraphState, intent: str, intent_detail: dict) -> str | None:
    """Returns a history-enriched query for SEMANTIC SEARCH ONLY, or None if
    no enrichment applies. A short message ("for a woman", "evening",
    "indoor", or a clarifying question like "Is the perfume for a man or a
    woman?") is very likely a refinement/answer continuing an earlier
    product-search thread, not a stand-alone request — embedding it alone
    can drift entirely away from what the customer is still discussing
    (e.g. "wedding perfume" ... "is it for a man or a woman?" searched in
    isolation matches whatever's semantically closest to gender-neutral
    phrasing, losing the wedding context entirely and returning unrelated
    products).

    Never applied to a specific product-name lookup (own_product_query /
    reference_search) — blending unrelated prior context into "Star n°016"
    would corrupt an otherwise clean, self-contained lookup."""
    query = state["query"]
    if len(query.split()) > _CURRENT_QUERY_MAX_WORDS:
        return None
    if intent_detail.get("is_own_product") or intent == "own_product_query":
        return None
    if intent_detail.get("is_international_reference") or intent == "reference_search":
        return None
    for m in reversed(state.get("history") or []):
        content = (m.get("content") or "").strip()
        if m.get("role") != "user" or content == query:
            continue
        if len(content.split()) > _PRIOR_MESSAGE_MIN_WORDS:
            return f"{content} {query}"
    return None


def product_search_node(state: ChatGraphState) -> ChatGraphState:
    """Unified product search: Shopify direct OR international → SQL notes → Shopify only."""
    logger.info("[GRAPH] node=product_search | query=%r", state.get("query"))
    db = state.get("_db")
    intent = state.get("intent", "general")
    intent_detail = state.get("intent_detail", {})

    # Follow-up informational question about a product already shown/discussed
    # ("how long does it last?", "is it good for summer?") — the customer isn't
    # asking for new recommendations, so running the full retrieval pipeline
    # (embeddings + Pinecone + note-matching) is both wasted work and risks
    # replacing the product they're actually asking about with something else.
    # Reuse what was already shown as the answer context instead.
    last_shown = state.get("last_shown_products") or []
    if intent_detail.get("skip_product_search") and last_shown:
        logger.info(
            "[GRAPH] product_search SKIPPED — follow-up question about previously shown product(s): %s",
            [(p.get("title") or "")[:30] for p in last_shown[:5]],
        )
        state["shopify_products"] = last_shown
        state["international_context"] = ""
        state["international_match"] = None
        state["suppress_product_cards"] = True
        state["pipeline_path"] = "followup_no_search"
        return state

    embed_query_text = _build_context_aware_search_query(state, intent, intent_detail)
    if embed_query_text:
        logger.info(
            "[GRAPH] short/ambiguous query %r enriched with prior context for search: %r",
            state["query"], embed_query_text,
        )

    products, intl_ctx, path = resolve_products_for_query(
        db=db,
        query=state["query"],
        shop=state.get("shop", ""),
        index=state["index"],
        embeddings=state["embeddings"],
        store_base_url=state["store_base_url"],
        intent=intent,
        intent_detail=intent_detail,
        embed_query_text=embed_query_text,
    )

    # Drop BOGO/free-gift/zero-price listings, backfill size options from the
    # live DB for any product whose Pinecone metadata predates the
    # structured-variant fields, THEN collapse same-perfume/different-size
    # listings (e.g. "Star n°002 - ML" and "Star n°002 - 50ML" as separate
    # Shopify products rather than variant options on one) into a single card
    # with a merged size list — see product_grouping.py. All three are
    # no-ops for a catalog with no promo SKUs / native Shopify variants /
    # fresh Pinecone data.
    if products:
        products = filter_promotional_products(products)
        products = enrich_missing_variants(db, products)
        products = group_same_perfume_products(products)

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
    state["suppress_product_cards"] = False
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
    is_followup = bool(state.get("suppress_product_cards"))
    pipeline_path = state.get("pipeline_path", "")
    intent_detail = state.get("intent_detail") or {}
    # Expose gender to the LLM when the customer explicitly wants a
    # gender-filtered recommendation, OR when they're looking at ONE
    # specifically-named product (own_product / exact_title_match /
    # follow-up) — e.g. "Is Star n°016 for men and women?" needs the Genre
    # field to answer at all. For a generic multi-product recommendation
    # query, gender stays hidden so the model doesn't parrot it unprompted
    # (e.g. answering "best perfume" with "voici des parfums pour femme").
    gender_requested = (
        bool((intent_detail.get("gender_preference") or "").strip())
        or pipeline_path in ("own_product", "exact_title_match")
        or is_followup
    )

    products_ctx = ""
    for i, p in enumerate(products[:5], 1):
        note_info = ", ".join(filter(None, [
            p.get("top_note"), p.get("heart_note"), p.get("base_note"), p.get("olfactive"),
        ]))
        gender_line = ""
        if gender_requested and p.get("gender"):
            gender_line = f"   Genre: {p['gender']}\n"
        # Notes alone don't cover attribute questions (allergies, sensitive
        # skin, longevity, season/occasion, gift-worthiness, "what notes are
        # in this?") — those live in free-text description. A follow-up
        # question about ONE already-shown product can afford a much longer
        # snippet (little else competes for prompt space) than a multi-
        # product recommendation list, where brevity matters more.
        desc_len = 600 if is_followup else 220
        desc = (p.get("description") or "")[:desc_len]
        desc_line = f"   Description: {desc}\n" if desc else ""
        # NOTE: match/similarity percentage is deliberately NOT included here.
        # It's already shown on the product card in the widget, so repeating
        # it in the generated text would be redundant — see prompts.py rule.
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

    # Path-specific response-style guidance (pipeline_path computed above).
    if pipeline_path in ("intl_sql_match", "intl_pinecone_fallback"):
        response_mode_directive = (
            "Ces produits sont des correspondances de profil olfactif issues de notre collection "
            "(PAS le parfum international lui-même, qui n'est jamais en vente ici) — présente-les avec une "
            "formulation naturelle et varie ta phrase, par exemple dans l'esprit de : « Voici quelques parfums "
            "de notre collection qui correspondent bien au profil olfactif recherché. »"
        )
    elif state.get("suppress_product_cards"):
        response_mode_directive = (
            "Le client pose une question de suivi sur un parfum déjà présenté plus haut dans la conversation — "
            "ce n'est PAS une nouvelle recommandation. Réponds directement à sa question sans re-présenter ni "
            "relister les produits (leurs fiches ne seront pas réaffichées)."
        )
    else:
        response_mode_directive = ""

    inputs = {
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
        # Explicit directive injected into the prompt so the model knows whether
        # gender framing is allowed for THIS query.
        "gender_directive": (
            "Le client a précisé un genre — tu peux en tenir compte."
            if gender_requested else
            "Le client n'a PAS précisé de genre : ne catégorise PAS les parfums par genre "
            "(n'écris jamais « pour femme / pour homme / mixte »). Recommande-les simplement."
        ),
        "response_mode_directive": response_mode_directive,
    }
    logger.info(
        "[GRAPH] build_generate_chain_inputs | products=%s gender_requested=%s comparison=%s "
        "pipeline_path=%s suppress_cards=%s",
        len(products), gender_requested, is_comparison,
        pipeline_path, state.get("suppress_product_cards"),
    )
    return inputs


def finalize_answer(state: ChatGraphState, message_text: str) -> dict:
    """Assembles the final answer dict (text + product cards) once the LLM
    message is known. Cards and text never repeat the same info twice —
    the prompt instructs the LLM not to restate price/URL, since those are
    only ever rendered in the product cards below the message."""
    products = state.get("shopify_products") or []
    # Follow-up questions about an already-shown product reuse it as answer
    # context but must NOT re-render cards that are already on screen.
    show_products = (
        bool(products)
        and state.get("intent") not in POLICY_INTENTS
        and not state.get("suppress_product_cards")
    )
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
