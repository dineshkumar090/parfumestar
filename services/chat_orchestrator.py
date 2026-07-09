"""Main chat orchestrator — LangGraph pipeline entry point."""

from __future__ import annotations

import json
import time as _time
from typing import Any

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
from sqlalchemy.orm import Session

from app.graph.workflow import run_chat_graph, run_pre_generate_graph
from app.models.chat import ChatMessage
from app.models.chat_intent_log import ChatIntentLog
from app.rag.constants import DEFAULT_PINECONE_INDEX
from app.rag.embeddings import get_embeddings
from app.models.chatbot_config import ChatbotConfig
from app.services.store_service import get_store_config


_CLIENT_CACHE: dict = {}
_CACHE_TTL = 300


def _store_base_url(store) -> str:
    if hasattr(store, "store_url") and store.store_url:
        return store.store_url.rstrip("/") + "/products"
    domain = getattr(store, "shop_domain", "")
    return f"https://{domain}/products"


def _store_contact_url(store) -> str:
    if hasattr(store, "store_url") and store.store_url:
        return store.store_url.rstrip("/") + "/pages/contact"
    domain = getattr(store, "shop_domain", "")
    return f"https://{domain}/pages/contact"


def _get_clients(store):
    now = _time.monotonic()
    cached = _CLIENT_CACHE.get(store.shop_domain)
    if cached and cached["expires"] > now:
        return cached["embeddings"], cached["index"], cached["model"]

    model_name = store.openai_model or "gpt-4o-mini"
    embeddings = get_embeddings(store.openai_api_key)
    pc = Pinecone(api_key=store.pinecone_api_key)
    index_name = store.pinecone_index_name or DEFAULT_PINECONE_INDEX
    index = pc.Index(index_name)

    _CLIENT_CACHE[store.shop_domain] = {
        "embeddings": embeddings,
        "index": index,
        "model": model_name,
        "expires": now + _CACHE_TTL,
    }
    return embeddings, index, model_name


def _load_history(db: Session, thread_id: int | None) -> tuple[list[dict], list[dict]]:
    history: list[dict] = []
    last_shown: list[dict] = []
    if not thread_id:
        return history, last_shown

    recent = (
        db.query(ChatMessage)
        .filter_by(thread_id=thread_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(12)
        .all()
    )
    recent.reverse()
    for m in recent:
        history.append({
            "role": "user" if m.role == "user" else "assistant",
            "content": m.content,
        })
        if m.role == "assistant" and m.response_data:
            prods = m.response_data.get("products", [])
            if prods:
                last_shown = prods
    return history, last_shown


def _log_intent(
    db: Session,
    thread_id: int | None,
    message_id: int | None,
    shop: str,
    intent_detail: dict,
    pipeline_path: str,
):
    try:
        log = ChatIntentLog(
            thread_id=thread_id,
            message_id=message_id,
            shop=shop,
            intent=intent_detail.get("intent", "general"),
            confidence=intent_detail.get("confidence", 0.0),
            is_international_reference=1 if intent_detail.get("is_international_reference") else 0,
            is_own_product=1 if intent_detail.get("is_own_product") else 0,
            product_name=intent_detail.get("product_name"),
            pipeline_path=pipeline_path,
            metadata_json=json.dumps(intent_detail)[:2000],
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[INTENT_LOG] failed: {e}")
        db.rollback()


class ChatOrchestrator:
    """Production chat handler using LangGraph + LangChain RAG."""

    def _prepare(
        self,
        query: str,
        shop: str,
        db: Session,
        customer_id: str | None,
        customer_email: str | None,
        thread_id: int | None,
    ):
        """Shared setup for both run() and stream(). Returns (store, initial_state)
        or (None, fallback_answer_dict) if the store isn't configured yet."""
        store = get_store_config(db, shop)
        if not store or not store.openai_api_key:
            return None, {
                "type": "general",
                "message": "Sorry, I'm having trouble connecting right now. Please try again.",
                "products": [],
                "show_products": False,
                "show_contact": False,
                "escalation_note": "",
                "contact_url": "",
            }

        if not store.pinecone_api_key:
            return None, {
                "type": "general",
                "message": (
                    "The AI assistant is not fully configured yet. "
                    "Please contact the store administrator."
                ),
                "products": [],
                "show_products": False,
                "show_contact": True,
                "escalation_note": "",
                "contact_url": _store_contact_url(store),
            }

        bot_cfg = db.query(ChatbotConfig).filter_by(shop=shop).first()
        tone = (bot_cfg.tone if bot_cfg else None) or "professional"
        brand_name = (bot_cfg.brand_name if bot_cfg else None) or "Assistant"
        store_name = getattr(store, "store_name", None) or shop

        embeddings, index, model_name = _get_clients(store)
        history, last_shown = _load_history(db, thread_id)

        initial_state = {
            "query": query,
            "shop": shop,
            "thread_id": thread_id,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "store": store,
            "bot_cfg": bot_cfg,
            "oai_api_key": store.openai_api_key,
            "model_name": model_name,
            "index": index,
            "embeddings": embeddings,
            "store_base_url": _store_base_url(store),
            "contact_url": _store_contact_url(store),
            "brand_name": brand_name,
            "tone": tone,
            "store_name": store_name,
            "history": history,
            "last_shown_products": last_shown,
            "_db": db,
        }
        return store, initial_state

    def run(
        self,
        query: str,
        shop: str,
        db: Session,
        customer_id: str | None = None,
        customer_email: str | None = None,
        thread_id: int | None = None,
    ) -> dict[str, Any]:
        store, prepared = self._prepare(query, shop, db, customer_id, customer_email, thread_id)
        if store is None:
            return prepared
        initial_state = prepared

        try:
            result = run_chat_graph(initial_state)
            answer = result.get("answer") or {}
            intent_detail = result.get("intent_detail") or {}
            _log_intent(
                db, thread_id, None, shop,
                intent_detail,
                result.get("pipeline_path", ""),
            )
            return answer
        except Exception as e:
            print(f"[ORCHESTRATOR] error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "type": "redirect",
                "message": "I'm having trouble answering that. Our team can help you directly!",
                "products": [],
                "show_products": False,
                "show_contact": True,
                "escalation_note": "",
                "contact_url": _store_contact_url(store),
            }

    def stream(
        self,
        query: str,
        shop: str,
        db: Session,
        customer_id: str | None = None,
        customer_email: str | None = None,
        thread_id: int | None = None,
    ):
        """Generator yielding {"delta": text} chunks as the final answer is
        generated token-by-token, followed by a single {"final": answer_dict}.
        Retrieval/classification (fast, non-streaming) runs first via the
        pre-generate graph; only the customer-facing LLM message streams."""
        from app.graph.nodes import build_generate_chain_inputs, finalize_answer
        from app.rag.prompts import PERFUME_ASSISTANT_PROMPT
        from langchain_openai import ChatOpenAI

        store, prepared = self._prepare(query, shop, db, customer_id, customer_email, thread_id)
        if store is None:
            yield {"final": prepared}
            return
        initial_state = prepared

        try:
            result = run_pre_generate_graph(initial_state)
            intent_detail = result.get("intent_detail") or {}
            _log_intent(
                db, thread_id, None, shop,
                intent_detail,
                result.get("pipeline_path", ""),
            )

            existing_answer = result.get("answer")
            if existing_answer:
                # greeting / orders / out_of_scope — already complete, instant.
                yield {"delta": existing_answer.get("message", "")}
                yield {"final": existing_answer}
                return

            llm = ChatOpenAI(
                model=result.get("model_name", "gpt-4o-mini"),
                api_key=result["oai_api_key"],
                temperature=0.4,
                streaming=True,
            )
            chain = PERFUME_ASSISTANT_PROMPT | llm
            chain_inputs = build_generate_chain_inputs(result)

            full_text = ""
            for chunk in chain.stream(chain_inputs):
                piece = chunk.content or ""
                if piece:
                    full_text += piece
                    yield {"delta": piece}

            answer = finalize_answer(result, full_text)
            yield {"final": answer}
        except Exception as e:
            print(f"[ORCHESTRATOR] stream error: {e}")
            import traceback
            traceback.print_exc()
            yield {"final": {
                "type": "redirect",
                "message": "I'm having trouble answering that. Our team can help you directly!",
                "products": [],
                "show_products": False,
                "show_contact": True,
                "escalation_note": "",
                "contact_url": _store_contact_url(store),
            }}


_orchestrator: ChatOrchestrator | None = None


def get_chat_orchestrator() -> ChatOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ChatOrchestrator()
    return _orchestrator
