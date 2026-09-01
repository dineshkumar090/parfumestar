"""LangChain structured intent classification."""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.rag.constants import ChatIntent

logger = logging.getLogger("uvicorn.error")


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
    gender_preference: str = Field(
        default="",
        description=(
            "'femme' if the customer wants a women's/ladies perfume, 'homme' if "
            "men's, 'mixte' if explicitly unisex, or '' if no gender was implied"
        ),
    )
    max_price: float | None = Field(
        default=None, description="Upper price bound in euros if the customer gave a budget"
    )
    min_price: float | None = Field(
        default=None, description="Lower price bound in euros, only if the customer gave a range"
    )
    compare_products: list[str] = Field(
        default_factory=list,
        description="If the customer wants to compare perfumes, the 2 product/brand names being compared",
    )
    needs_ingredient_info: bool = Field(
        default=False,
        description="True for allergy, ingredient, sensitive-skin, or composition questions",
    )
    is_newest_query: bool = Field(
        default=False,
        description="True if the customer explicitly asks for the newest/latest arrivals",
    )
    skip_product_search: bool = Field(
        default=False,
        description=(
            "True ONLY if this question is about a product already shown/discussed earlier "
            "in this conversation (asking about ITS usage, longevity, season suitability, "
            "EDT vs EDP, ingredients, etc.) rather than asking to find/recommend a product. "
            "False (default) for anything that should trigger a new product search."
        ),
    )
    order_id: str | None = Field(default=None)
    needs_escalation: bool = Field(default=False)
    escalation_reason: str = Field(default="")


INTENT_SYSTEM_PROMPT = """Tu es un classificateur d'intentions pour Parfums Star, boutique de parfums.
Classifie le message client en UNE SEULE intention. Le client parle généralement en français.

Intents:
- reference_search: parfum de marque internationale (Chanel, Dior, Carolina Herrera CH…) pour trouver un dupe Star
- recommendation_search: recommandations de parfums de notre boutique (humeur, occasion, notes, genre, budget, saison, cadeau)
- product_knowledge_query: questions sur ingrédients, allergies, notes, tenue, utilisation, comparaison entre parfums
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
- gender_preference: si le client demande un parfum "femme"/"pour elle"/"ladies"/"women"/"her"/"féminin" → "femme".
  Si "homme"/"pour lui"/"men"/"his"/"masculin" → "homme". Si "mixte"/"unisexe"/"unisex" → "mixte".
  Sinon (aucune préférence exprimée) → chaîne vide "".
- max_price/min_price: extrais tout budget mentionné ("moins de 50€" → max_price=50, "entre 20 et 40€" →
  min_price=20, max_price=40, "budget serré" sans chiffre → laisse vide). Toujours en euros.
- compare_products: si le client compare explicitement 2 parfums ("X ou Y ?", "différence entre X et Y"),
  liste les 2 noms. Sinon liste vide.
- needs_ingredient_info=true pour toute question sur allergies, ingrédients, composition, peau sensible.
- is_newest_query=true pour "nouveautés", "derniers parfums sortis", "dernières sorties", "nouveaux produits".
- skip_product_search=true UNIQUEMENT si le client pose une question de suivi sur un parfum DÉJÀ montré/mentionné
  plus haut dans la conversation (regarde "Products currently shown" et l'historique) — ex: "comment l'appliquer ?",
  "combien de temps ça tient ?", "c'est bien pour l'été ?", "quelle est la différence entre EDT et EDP ?",
  "il contient quoi ?" en référence à un produit déjà discuté. Dans ce cas, intent=product_knowledge_query et
  skip_product_search=true — ce n'est PAS une nouvelle recherche de produit. Si le client demande de nouveaux
  produits, une comparaison avec un produit non montré, ou toute recommandation, skip_product_search=false.

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

    result: IntentClassification | None = None
    method = None
    try:
        structured_result = structured.invoke([
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ])
        if isinstance(structured_result, IntentClassification):
            result = structured_result
            method = "structured_output(function_call)"
    except Exception as e:
        logger.warning("[INTENT] structured output failed, falling back: %s", e)

    if result is None:
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
            result = IntentClassification(**data)
            method = "raw_json_fallback"
        except Exception:
            pass

    if result is None:
        # Heuristic fallback
        method = "heuristic_fallback"
        q = query.lower()
        gender = _heuristic_gender(q)
        min_price, max_price = _heuristic_price_range(q)
        if any(w in q for w in ("order", "tracking", "shipment", "delivery")):
            result = IntentClassification(intent=ChatIntent.ORDERS.value, confidence=0.6)
        elif "star n" in q or "star no" in q or "star n°" in q:
            result = IntentClassification(
                intent=ChatIntent.OWN_PRODUCT.value,
                is_own_product=True,
                gender_preference=gender,
                min_price=min_price, max_price=max_price,
                confidence=0.7,
            )
        elif any(brand in q for brand in ("carolina herrera", "chanel", "dior", "ysl", "gucci", "tom ford")):
            result = IntentClassification(
                intent=ChatIntent.REFERENCE_SEARCH.value,
                is_international_reference=True,
                gender_preference=gender,
                min_price=min_price, max_price=max_price,
                confidence=0.7,
            )
        else:
            result = IntentClassification(
                intent=ChatIntent.GENERAL.value, gender_preference=gender,
                min_price=min_price, max_price=max_price, confidence=0.5,
            )

    # Belt-and-suspenders: a regex catches explicit price mentions the LLM
    # sometimes drops (especially with unusual phrasing), and flags obvious
    # "newest arrivals" queries even if the model didn't set the flag.
    q_lower = query.lower()
    if result.max_price is None and result.min_price is None:
        min_p, max_p = _heuristic_price_range(q_lower)
        result.min_price, result.max_price = min_p, max_p
    if not result.is_newest_query and _heuristic_is_newest(q_lower):
        result.is_newest_query = True
    if not result.gender_preference:
        # The LLM classifier occasionally leaves gender blank even on an
        # explicit "men's perfume" / "pour homme" style CURRENT message
        # (seen in production on gender-switch follow-ups) — a blank gender
        # skips the Pinecone gender filter entirely, letting mismatched
        # products through. Checked on the current message only (not
        # history) so an earlier turn's gender never leaks into this one.
        result.gender_preference = _heuristic_gender(q_lower)
    if result.skip_product_search and WANTS_DIFFERENT_PRODUCT_RE.search(query):
        logger.info(
            "[INTENT] override: skip_product_search forced False — query requests a new/different product: %r",
            query,
        )
        result.skip_product_search = False

    logger.info(
        "[INTENT] classify_intent(query=%r) via %s -> intent=%s conf=%s intl_ref=%s own=%s gender=%r "
        "price=[%s,%s] compare=%s newest=%s skip_product_search=%s",
        query, method, result.intent, result.confidence, result.is_international_reference,
        result.is_own_product, result.gender_preference, result.min_price, result.max_price,
        result.compare_products, result.is_newest_query, result.skip_product_search,
    )
    return result


_FEMME_WORDS = ("femme", "pour elle", "ladies", "lady", "women", "woman", "her ", "féminin", "feminin")
_HOMME_WORDS = ("homme", "pour lui", "men's", " men", "man ", "his ", "masculin")
_MIXTE_WORDS = ("mixte", "unisexe", "unisex")


def _heuristic_gender(q: str) -> str:
    if any(w in q for w in _MIXTE_WORDS):
        return "mixte"
    if any(w in q for w in _FEMME_WORDS):
        return "femme"
    if any(w in q for w in _HOMME_WORDS):
        return "homme"
    return ""


_PRICE_NUM = r"(\d+(?:[.,]\d+)?)"
_PRICE_UNIT = r"(?:€|eur(?:os?)?)"
_PRICE_RANGE_RE = re.compile(
    rf"entre\s+{_PRICE_NUM}\s*(?:{_PRICE_UNIT})?\s+et\s+{_PRICE_NUM}\s*{_PRICE_UNIT}?", re.IGNORECASE
)
_PRICE_MAX_RE = re.compile(
    rf"(?:moins de|max(?:imum)?|sous|budget(?: de)?|jusqu'?\s*[aà]|en dessous de|inf[ée]rieur[e]?\s*[aà])\s*{_PRICE_NUM}\s*{_PRICE_UNIT}?",
    re.IGNORECASE,
)
_PRICE_MIN_RE = re.compile(
    rf"(?:plus de|min(?:imum)?|au-?dessus de|sup[ée]rieur[e]?\s*[aà])\s*{_PRICE_NUM}\s*{_PRICE_UNIT}?",
    re.IGNORECASE,
)


def _heuristic_price_range(q: str) -> tuple[float | None, float | None]:
    m = _PRICE_RANGE_RE.search(q)
    if m:
        a, b = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        return (min(a, b), max(a, b))
    max_m = _PRICE_MAX_RE.search(q)
    max_price = float(max_m.group(1).replace(",", ".")) if max_m else None
    min_m = _PRICE_MIN_RE.search(q)
    min_price = float(min_m.group(1).replace(",", ".")) if min_m else None
    return (min_price, max_price)


_NEWEST_WORDS = ("nouveaut", "nouveau parfum", "nouveaux parfum", "dernière sortie",
                  "dernieres sorties", "derniers arrivages", "vient de sortir", "new arrival", "latest")


def _heuristic_is_newest(q: str) -> bool:
    return any(w in q for w in _NEWEST_WORDS)


# A request verb followed (within a short window) by "another/different" —
# "recommend me another mist", "montre-moi une autre brume" — always means a
# FRESH product search, never a follow-up question about what's already on
# screen. Requiring the verb avoids false-triggering on unrelated uses of
# "autre" (e.g. "the other one you showed" comparing already-shown products,
# which legitimately IS a follow-up).
WANTS_DIFFERENT_PRODUCT_RE = re.compile(
    r"\b(?:recommand\w*|montre\w*|donne\w*|propose\w*|trouve\w*|cherch\w*|"
    r"show|recommend|suggest|find|give)\b[^.?!]{0,25}\b"
    r"(?:un\s+autre|une\s+autre|d'autres?|autres?|quelque\s+chose\s+d'autre|"
    r"another|a\s+different|something\s+else|other\s+options?)\b",
    re.IGNORECASE,
)


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
