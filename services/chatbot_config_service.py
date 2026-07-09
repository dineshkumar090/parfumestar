"""Shared chatbot config serialization for admin + widget APIs."""

from __future__ import annotations

from typing import Any

from app.models.chatbot_config import ChatbotConfig


def get_default_config(shop: str) -> dict[str, Any]:
    return {
        "shop": shop,
        "enabled": True,
        "greeting_message": (
            "Hi! I'm your AI assistant. Feel free to ask me anything — I'm ready to help!"
        ),
        "tone": "professional",
        "window_color": "#008060",
        "brand_name": "AI Assistant",
        "header_icon": "🤖",
        "button_text": "Ask me anything!",
        "cart_icon": "mdi:cart",
        "cart_enabled": True,
        "icon_style": ["iconLabel"],
        "icon_size": ["standard"],
        "icon_shape": ["rounded"],
        "desktop_position": "bottomRight",
        "transparent_bg": False,
        "selected_pages": ["home", "product", "checkout"],
        "quick_chips": [
            {"icon": "mdi:shopping", "label": "Browse Products", "query": "Show me all products"},
            {"icon": "mdi:star", "label": "Best Sellers", "query": "What are your best selling products?"},
            {"icon": "mdi:phone", "label": "Contact Support", "query": "How can I contact support?"},
        ],
        "system_prompts": {},
        "tool_decision_prompt": None,
        "answer_generation_prompt": None,
        "product_description_prompt": None,
        "embedding_prompt_template": None,
        "comparison_prompt": None,
        "suggestion_prompt": None,
        "order_status_prompt": None,
        "smalltalk_responses": [],
        "greeting_templates": {},
        "product_count_templates": {},
        "enable_smalltalk": True,
        "enable_product_comparison": True,
        "enable_price_filtering": True,
        "enable_variant_detection": True,
        "enable_followup_detection": True,
        "show_evaluation_button": False,
    }


def config_to_admin_dict(config: ChatbotConfig, shop: str) -> dict[str, Any]:
    """Full config for ChatbotControl admin panel."""
    defaults = get_default_config(shop)

    def _get(attr: str, default=None):
        val = getattr(config, attr, None)
        return default if val is None else val

    return {
        "shop": config.shop,
        "enabled": config.enabled,
        "greeting_message": _get("greeting_message", defaults["greeting_message"]),
        "tone": _get("tone", defaults["tone"]),
        "window_color": _get("window_color", defaults["window_color"]),
        "brand_name": _get("brand_name", defaults["brand_name"]),
        "button_text": _get("button_text", defaults["button_text"]),
        "cart_icon": _get("cart_icon", defaults["cart_icon"]),
        "cart_enabled": config.cart_enabled if config.cart_enabled is not None else defaults["cart_enabled"],
        "header_icon": _get("header_icon", defaults["header_icon"]),
        "icon_style": _get("icon_style", defaults["icon_style"]),
        "icon_size": _get("icon_size", defaults["icon_size"]),
        "icon_shape": _get("icon_shape", defaults["icon_shape"]),
        "desktop_position": _get("desktop_position", defaults["desktop_position"]),
        "transparent_bg": config.transparent_bg if config.transparent_bg is not None else defaults["transparent_bg"],
        "selected_pages": _get("selected_pages", defaults["selected_pages"]),
        "quick_chips": _get("quick_chips", defaults["quick_chips"]),
        "system_prompts": _get("system_prompts", defaults["system_prompts"]),
        "tool_decision_prompt": _get("tool_decision_prompt"),
        "answer_generation_prompt": _get("answer_generation_prompt"),
        "product_description_prompt": _get("product_description_prompt"),
        "embedding_prompt_template": _get("embedding_prompt_template"),
        "comparison_prompt": _get("comparison_prompt"),
        "suggestion_prompt": _get("suggestion_prompt"),
        "order_status_prompt": _get("order_status_prompt"),
        "smalltalk_responses": _get("smalltalk_responses", defaults["smalltalk_responses"]),
        "greeting_templates": _get("greeting_templates", defaults["greeting_templates"]),
        "product_count_templates": _get("product_count_templates", defaults["product_count_templates"]),
        "enable_smalltalk": config.enable_smalltalk if config.enable_smalltalk is not None else True,
        "enable_product_comparison": config.enable_product_comparison if config.enable_product_comparison is not None else True,
        "enable_price_filtering": config.enable_price_filtering if config.enable_price_filtering is not None else True,
        "enable_variant_detection": config.enable_variant_detection if config.enable_variant_detection is not None else True,
        "enable_followup_detection": config.enable_followup_detection if config.enable_followup_detection is not None else True,
        "show_evaluation_button": config.show_evaluation_button if config.show_evaluation_button is not None else False,
    }


def config_to_widget_dict(config: ChatbotConfig | None, shop: str) -> dict[str, Any]:
    """Public widget config — matches GET /api/chat/config response."""
    defaults = get_default_config(shop)
    if not config:
        return {
            "enabled": defaults["enabled"],
            "greeting_message": defaults["greeting_message"],
            "window_color": defaults["window_color"],
            "brand_name": defaults["brand_name"],
            "header_icon": defaults["header_icon"],
            "icon_style": defaults["icon_style"],
            "icon_size": defaults["icon_size"],
            "icon_shape": defaults["icon_shape"],
            "desktop_position": defaults["desktop_position"],
            "transparent_bg": defaults["transparent_bg"],
            "quick_chips": defaults["quick_chips"],
            "selected_pages": defaults["selected_pages"],
            "button_text": defaults["button_text"],
            "cart_icon": defaults["cart_icon"],
            "cart_enabled": defaults["cart_enabled"],
            "assistant_tone": defaults["tone"],
            "icon_label": f"Ask {defaults['brand_name']}",
        }

    return {
        "enabled": config.enabled,
        "greeting_message": config.greeting_message or defaults["greeting_message"],
        "window_color": config.window_color or defaults["window_color"],
        "brand_name": config.brand_name or defaults["brand_name"],
        "header_icon": getattr(config, "header_icon", None) or defaults["header_icon"],
        "icon_style": config.icon_style or defaults["icon_style"],
        "icon_size": config.icon_size or defaults["icon_size"],
        "icon_shape": config.icon_shape or defaults["icon_shape"],
        "desktop_position": config.desktop_position or defaults["desktop_position"],
        "transparent_bg": config.transparent_bg if config.transparent_bg is not None else defaults["transparent_bg"],
        "quick_chips": config.quick_chips or defaults["quick_chips"],
        "selected_pages": config.selected_pages or defaults["selected_pages"],
        "button_text": getattr(config, "button_text", None) or defaults["button_text"],
        "cart_icon": getattr(config, "cart_icon", None) or defaults["cart_icon"],
        "cart_enabled": config.cart_enabled if config.cart_enabled is not None else defaults["cart_enabled"],
        "assistant_tone": config.tone or defaults["tone"],
        "icon_label": f"Ask {config.brand_name or defaults['brand_name']}",
    }
