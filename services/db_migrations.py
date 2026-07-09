"""
Safe MySQL column migrations — adds missing columns without dropping data.
Run on app startup and/or manually via migrations/*.sql
"""

import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("uvicorn.error")

# Columns added after initial chatbot_configs release
CHATBOT_CONFIGS_COLUMNS: dict[str, str] = {
    "button_text": "VARCHAR(200) NULL DEFAULT 'Ask me anything!'",
    "cart_icon": "VARCHAR(50) NULL DEFAULT 'mdi:cart'",
    "cart_enabled": "TINYINT(1) NULL DEFAULT 1",
    "header_icon": "VARCHAR(50) NULL DEFAULT '🤖'",
    "system_prompts": "JSON NULL",
    "tool_decision_prompt": "TEXT NULL",
    "answer_generation_prompt": "TEXT NULL",
    "product_description_prompt": "TEXT NULL",
    "embedding_prompt_template": "TEXT NULL",
    "comparison_prompt": "TEXT NULL",
    "suggestion_prompt": "TEXT NULL",
    "order_status_prompt": "TEXT NULL",
    "smalltalk_responses": "JSON NULL",
    "greeting_templates": "JSON NULL",
    "product_count_templates": "JSON NULL",
    "enable_smalltalk": "TINYINT(1) NULL DEFAULT 1",
    "enable_product_comparison": "TINYINT(1) NULL DEFAULT 1",
    "enable_price_filtering": "TINYINT(1) NULL DEFAULT 1",
    "enable_variant_detection": "TINYINT(1) NULL DEFAULT 1",
    "enable_followup_detection": "TINYINT(1) NULL DEFAULT 1",
    "show_evaluation_button": "TINYINT(1) NULL DEFAULT 0",
}


def _existing_columns(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def migrate_chatbot_configs(engine: Engine) -> list[str]:
    """Add any missing chatbot_configs columns. Returns list of columns added."""
    if "chatbot_configs" not in inspect(engine).get_table_names():
        logger.info("chatbot_configs table does not exist yet — create_all will create it.")
        return []

    existing = _existing_columns(engine, "chatbot_configs")
    added: list[str] = []

    with engine.begin() as conn:
        for col, ddl in CHATBOT_CONFIGS_COLUMNS.items():
            if col in existing:
                continue
            sql = f"ALTER TABLE chatbot_configs ADD COLUMN `{col}` {ddl}"
            conn.execute(text(sql))
            added.append(col)
            logger.info("Added column chatbot_configs.%s", col)

    return added


def migrate_products(engine: Engine) -> list[str]:
    """Fix products.tags length and add products.updated_at for incremental sync."""
    if "products" not in inspect(engine).get_table_names():
        logger.info("products table does not exist yet — create_all will create it.")
        return []

    changed: list[str] = []
    existing_cols = {c["name"]: c for c in inspect(engine).get_columns("products")}

    with engine.begin() as conn:
        tags_col = existing_cols.get("tags")
        if tags_col is not None and str(tags_col["type"]).upper().startswith("VARCHAR"):
            conn.execute(text("ALTER TABLE products MODIFY COLUMN tags TEXT NULL"))
            changed.append("tags->TEXT")
            logger.info("Widened products.tags to TEXT")

        if "updated_at" not in existing_cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN updated_at DATETIME NULL"))
            changed.append("updated_at")
            logger.info("Added column products.updated_at")

    return changed


def run_startup_migrations(engine: Engine) -> None:
    """Run all pending schema migrations."""
    try:
        added = migrate_chatbot_configs(engine)
        if added:
            logger.info("Migration complete — added columns: %s", ", ".join(added))

        products_changed = migrate_products(engine)
        if products_changed:
            logger.info("Migration complete — products: %s", ", ".join(products_changed))
    except Exception as e:
        logger.error("Schema migration failed: %s", e)
        raise
