"""
app/models/chatbot_config.py
─────────────────────────────
SQLAlchemy model for the per-shop chatbot Control Panel configuration.

Place this file at:  app/models/chatbot_config.py
Then import it in your database setup so create_all() picks it up:
    from app.models import chatbot_config   # noqa – registers table

Run a migration (or call Base.metadata.create_all) to add the table.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

# ── adjust this import to match your project layout ──────────────────────────
from app.database.db import Base
# ─────────────────────────────────────────────────────────────────────────────


class ChatbotConfig(Base):
    """
    One row per Shopify shop. Stores every setting that the Chatbot Control
    Panel can configure.  Consumed by:
      - GET /api/chat/bot-config   (admin panel read)
      - POST /api/chat/bot-config  (admin panel write)
      - GET /api/chat/config       (storefront widget read)
      - _ai_response()             (tone injected into system prompt)
    """

    __tablename__ = "chatbot_configs"

    id   = Column(Integer, primary_key=True, index=True)
    shop = Column(String(255), unique=True, index=True, nullable=False)

    # ── Toggle ─────────────────────────────────────────────────────────────
    enabled = Column(Boolean, default=True, nullable=False)

    # ── Messaging ──────────────────────────────────────────────────────────
    greeting_message = Column(Text, nullable=True)
    tone             = Column(String(50),  default="friendly")   # professional | humorous | friendly | enthusiastic

    # ── Appearance ─────────────────────────────────────────────────────────
    window_color     = Column(String(20),  default="#008060")
    brand_name       = Column(String(100), default="AI Assistant")
    button_text = Column(String(200), default="Ask me anything!")
    cart_icon    = Column(String(50),  default="mdi:cart")
    cart_enabled = Column(Boolean,     default=True)
    header_icon = Column(String(50), default="🤖")


    # Stored as JSON arrays to mirror React ChoiceList state shape
    icon_style       = Column(JSON, default=lambda: ["iconLabel"])   # iconOnly | iconLabel
    icon_size        = Column(JSON, default=lambda: ["standard"])    # small | standard | large
    icon_shape       = Column(JSON, default=lambda: ["rounded"])     # rounded | square

    desktop_position = Column(String(50),  default="bottomRight")   # bottomRight | bottomLeft | centerRight
    transparent_bg   = Column(Boolean,     default=False)

    # Recommended-product card layout in the widget:
    #   list       — one per row, vertical card (image on top) — current/default look
    #   grid_2     — two cards per row
    #   carousel   — single row, horizontal scroll
    #   horizontal — one per row, horizontal card (image left, content right)
    card_layout = Column(String(30), default="list")

    # ── Page visibility ────────────────────────────────────────────────────
    selected_pages   = Column(JSON, default=lambda: ["home", "product", "checkout"])

    # ── Quick-action chips shown in the widget ─────────────────────────────
    quick_chips = Column(
        JSON,
        default=lambda: [
            {"label": "😴 Sleep",      "query": "What helps with sleep?"},
            {"label": "🧘 Stress",     "query": "Do you have stress relief formulas?"},
            {"label": "🛍️ Browse all", "query": "Show me all products"},
            {"label": "🌱 Spagyric?",  "query": "What are spagyric tinctures?"},
            {"label": "🍃 Digestion",  "query": "Help me with digestion issues"},
        ],
    )

    # ── Dynamic Prompts Fields ──────────────────────────────────────────────
    system_prompts = Column(JSON, default=lambda: {})
    tool_decision_prompt = Column(Text, nullable=True)
    answer_generation_prompt = Column(Text, nullable=True)
    product_description_prompt = Column(Text, nullable=True)
    embedding_prompt_template = Column(Text, nullable=True)
    comparison_prompt = Column(Text, nullable=True)
    suggestion_prompt = Column(Text, nullable=True)
    order_status_prompt = Column(Text, nullable=True)
    smalltalk_responses = Column(JSON, default=lambda: [])
    greeting_templates = Column(JSON, default=lambda: {})
    product_count_templates = Column(JSON, default=lambda: {})

    # ── Feature Flags ──────────────────────────────────────────────────────
    enable_smalltalk = Column(Boolean, default=True)
    enable_product_comparison = Column(Boolean, default=True)
    enable_price_filtering = Column(Boolean, default=True)
    enable_variant_detection = Column(Boolean, default=True)
    enable_followup_detection = Column(Boolean, default=True)
    show_evaluation_button = Column(Boolean, default=False)

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())