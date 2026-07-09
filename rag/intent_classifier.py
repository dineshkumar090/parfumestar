"""LangChain structured intent classification."""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.rag.constants import ChatIntent


class IntentClassification(BaseModel):
    intent: str = Field(description="Primary intent type")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    product_name: str | None = Field(default=None, description="Detected product or brand name")
    is_international_reference: bool = Field(
        default=False,
        description="True if user asks about a well-known international perfume brand",
    )
    is_own_product: bool = Field(
        default=False,
        description="True if user asks about a Parfums Star / Star n° product",
    )
    order_id: str | None = Field(default=None)
    needs_escalation: bool = Field(default=False)
    escalation_reason: str = Field(default="")


INTENT_SYSTEM_PROMPT = """Tu es un classificateur d'intentions pour Parfums Star, boutique de parfums.
Classifie le message client en UNE SEULE intention. Le client parle généralement en français.

Intents:
- reference_search: parfum de marque internationale (Chanel, Dior, Carolina Herrera CH…) pour trouver un dupe Star
- recommendation_search: recommandations de parfums de notre boutique (humeur, occasion, notes, genre)
- product_knowledge_query: questions sur ingrédients, notes, tenue, utilisation
- own_product_query: produit Parfums Star spécifique (Star n°, STAR n°)
- store_details, payment_methods, store_information, shipping_policy, contact_information
- offers_and_rewards, orders, order_management, returns_information, refund_policy, cancellation
- greeting: bonjour, salut
- out_of_scope: sujets hors parfumerie
- general: autres questions shopping

Règles:
- "CH Carolina Herrera" ou marque de luxe → reference_search + is_international_reference=true
- "Star n° 002" → own_product_query + is_own_product=true
- Ne jamais classer une recherche produit comme out_of_scope

Réponds en JSON valide uniquement."""


def classify_intent(
    query: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    history: list[dict] | None = None,
    last_shown_titles: list[str] | None = None,
) -> IntentClassification:
    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    structured = llm.with_structured_output(IntentClassification)

    history_text = ""
    if history:
        for m in history[-6:]:
            role = "Customer" if m.get("role") == "user" else "Assistant"
            history_text += f"{role}: {m.get('content', '')[:300]}\n"

    shown = ""
    if last_shown_titles:
        shown = f"\nProducts currently shown: {', '.join(last_shown_titles[:5])}\n"

    user_msg = f"{history_text}{shown}\nCurrent message: {query}"

    try:
        result = structured.invoke([
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ])
        if isinstance(result, IntentClassification):
            return result
    except Exception as e:
        print(f"[INTENT] structured output failed: {e}")

    # Fallback: raw JSON parse
    try:
        resp = llm.invoke([
            SystemMessage(content=INTENT_SYSTEM_PROMPT + "\nReturn JSON only."),
            HumanMessage(content=user_msg),
        ])
        raw = resp.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        data = json.loads(raw)
        return IntentClassification(**data)
    except Exception:
        pass

    # Heuristic fallback
    q = query.lower()
    if any(w in q for w in ("order", "tracking", "shipment", "delivery")):
        return IntentClassification(intent=ChatIntent.ORDERS.value, confidence=0.6)
    if "star n" in q or "star no" in q or "star n°" in q:
        return IntentClassification(
            intent=ChatIntent.OWN_PRODUCT.value,
            is_own_product=True,
            confidence=0.7,
        )
    if any(brand in q for brand in ("carolina herrera", "chanel", "dior", "ysl", "gucci", "tom ford")):
        return IntentClassification(
            intent=ChatIntent.REFERENCE_SEARCH.value,
            is_international_reference=True,
            confidence=0.7,
        )
    return IntentClassification(intent=ChatIntent.GENERAL.value, confidence=0.5)


def intent_to_response_type(intent: str) -> str:
    mapping = {
        ChatIntent.ORDERS.value: "order",
        ChatIntent.ORDER_MANAGEMENT.value: "order",
        ChatIntent.REFERENCE_SEARCH.value: "products",
        ChatIntent.RECOMMENDATION_SEARCH.value: "products",
        ChatIntent.OWN_PRODUCT.value: "products",
        ChatIntent.PRODUCT_KNOWLEDGE.value: "products",
    }
    return mapping.get(intent, "general")
