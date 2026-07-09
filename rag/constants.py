"""Intent types and RAG configuration constants."""

from enum import Enum


DEFAULT_PINECONE_INDEX = "perfumestar"
EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHAT_MODEL = "gpt-4o-mini"


class ChatIntent(str, Enum):
    REFERENCE_SEARCH = "reference_search"
    RECOMMENDATION_SEARCH = "recommendation_search"
    PRODUCT_KNOWLEDGE = "product_knowledge_query"
    OWN_PRODUCT = "own_product_query"
    OUT_OF_SCOPE = "out_of_scope"
    STORE_DETAILS = "store_details"
    PAYMENT_METHODS = "payment_methods"
    STORE_INFORMATION = "store_information"
    SHIPPING_POLICY = "shipping_policy"
    CONTACT_INFORMATION = "contact_information"
    OFFERS_REWARDS = "offers_and_rewards"
    ORDERS = "orders"
    ORDER_MANAGEMENT = "order_management"
    RETURNS = "returns_information"
    REFUND_POLICY = "refund_policy"
    CANCELLATION = "cancellation"
    GREETING = "greeting"
    GENERAL = "general"


INTENT_LABELS: dict[str, str] = {
    ChatIntent.REFERENCE_SEARCH.value: "Reference Search",
    ChatIntent.RECOMMENDATION_SEARCH.value: "Recommendation Search",
    ChatIntent.PRODUCT_KNOWLEDGE.value: "Product Knowledge",
    ChatIntent.OWN_PRODUCT.value: "Own Product Inquiry",
    ChatIntent.OUT_OF_SCOPE.value: "Out of Scope",
    ChatIntent.STORE_DETAILS.value: "Store Details",
    ChatIntent.PAYMENT_METHODS.value: "Payment Methods",
    ChatIntent.STORE_INFORMATION.value: "Store Information",
    ChatIntent.SHIPPING_POLICY.value: "Shipping Policy",
    ChatIntent.CONTACT_INFORMATION.value: "Contact Information",
    ChatIntent.OFFERS_REWARDS.value: "Offers & Rewards",
    ChatIntent.ORDERS.value: "Order Tracking",
    ChatIntent.ORDER_MANAGEMENT.value: "Order Management",
    ChatIntent.RETURNS.value: "Returns",
    ChatIntent.REFUND_POLICY.value: "Refund Policy",
    ChatIntent.CANCELLATION.value: "Cancellation",
    ChatIntent.GREETING.value: "Greeting",
    ChatIntent.GENERAL.value: "General Inquiry",
}

POLICY_INTENTS = {
    ChatIntent.STORE_DETAILS.value,
    ChatIntent.PAYMENT_METHODS.value,
    ChatIntent.STORE_INFORMATION.value,
    ChatIntent.SHIPPING_POLICY.value,
    ChatIntent.CONTACT_INFORMATION.value,
    ChatIntent.OFFERS_REWARDS.value,
    ChatIntent.RETURNS.value,
    ChatIntent.REFUND_POLICY.value,
    ChatIntent.CANCELLATION.value,
}

SOURCE_INTERNATIONAL = "international"
SOURCE_SHOPIFY = "shopify"
