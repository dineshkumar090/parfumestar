"""LangGraph state definition."""

from typing import Any, TypedDict


class ChatGraphState(TypedDict, total=False):
    query: str
    shop: str
    thread_id: int | None
    customer_id: str | None
    customer_email: str | None
    _db: Any  # SQLAlchemy Session, passed through for nodes that need direct DB access

    # Config
    store: Any
    bot_cfg: Any
    oai_api_key: str
    model_name: str
    index: Any
    embeddings: Any
    store_base_url: str
    contact_url: str
    brand_name: str
    tone: str
    store_name: str

    # Conversation
    history: list[dict]
    last_shown_products: list[dict]

    # Pipeline
    intent: str
    intent_detail: dict
    international_match: dict | None
    shopify_products: list[dict]
    knowledge_context: str
    international_context: str
    pipeline_path: str

    # Output
    answer: dict
    error: str | None
