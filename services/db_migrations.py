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
    "card_layout": "VARCHAR(30) NULL DEFAULT 'list'",
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


# Tables that store product / user / config text which can legitimately
# contain 4-byte UTF-8 characters (emoji). Shopify product titles like
# "🎁 Star 2454 - Lueur d'Espoir (100% off)" are the concrete trigger.
UTF8MB4_TABLES = [
    "products",
    "main_database",
    "perfume_notes",
    "chatbot_configs",
    "chat_threads",
    "chat_messages",
    "engagement_events",
    "chat_intent_logs",
    "custom_data",
    "pages",
    "blogs",
    "blog_posts",
    "product_details",
    "message_evaluations",
    "stores",
    "store_configs",
]


def _table_charset(conn, table: str) -> str | None:
    row = conn.execute(
        text(
            "SELECT CCSA.character_set_name "
            "FROM information_schema.TABLES T "
            "JOIN information_schema.COLLATION_CHARACTER_SET_APPLICABILITY CCSA "
            "  ON CCSA.collation_name = T.table_collation "
            "WHERE T.table_schema = DATABASE() AND T.table_name = :t"
        ),
        {"t": table},
    ).fetchone()
    return row[0] if row else None


def migrate_utf8mb4(engine: Engine) -> list[str]:
    """Convert product/text tables to utf8mb4 so 4-byte characters (emoji such
    as 🎁 in Shopify product titles) can be stored. Without this MySQL raises
    error 1366 "Incorrect string value" and every emoji product is skipped
    from the sync.

    Each table is converted in its own transaction and any failure (e.g. a
    missing ALTER privilege, or an index-prefix limit on very old MySQL) is
    logged and swallowed — one un-convertible table must never block startup
    or the remaining conversions. Idempotent: tables already utf8mb4 are
    skipped."""
    existing = set(inspect(engine).get_table_names())
    converted: list[str] = []

    for table in UTF8MB4_TABLES:
        if table not in existing:
            continue
        try:
            with engine.begin() as conn:
                if _table_charset(conn, table) == "utf8mb4":
                    continue
                conn.execute(
                    text(
                        f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 "
                        f"COLLATE utf8mb4_unicode_ci"
                    )
                )
            converted.append(table)
            logger.info("Converted table %s to utf8mb4", table)
        except Exception as e:
            logger.error("utf8mb4 conversion failed for table %s: %s", table, e)

    return converted


def renormalize_perfume_notes(engine: Engine) -> int:
    """Recompute every stored `perfume_notes.note_name` from its preserved
    `note_raw` original, so an improvement to normalize_note_name applies to
    already-synced products instead of only to newly-synced ones.

    This exists because note_name is written ONCE, at sync time — a fix to
    the normalizer (e.g. teaching it that Shopify's "Notes aquatiques" and
    the international source's "Aquatique" are the same note, or that "Bois
    de santal" is "Santal") would otherwise have no effect on the ~20k rows
    already in the table, and every existing product would keep matching on
    the old, broken tokens until a full re-sync happened. Because note_raw
    keeps the original text verbatim, the corrected value can be re-derived
    locally — no Shopify API calls, no OpenAI note re-extraction, no
    re-embedding.

    Non-destructive by construction: UPDATEs names only, never inserts or
    deletes. Two notes on the same product can now collapse to one token
    (that IS the fix), leaving a redundant duplicate row — harmless, since
    note_matcher loads each product's notes into a set. Idempotent: a second
    run finds nothing to change."""
    if "perfume_notes" not in inspect(engine).get_table_names():
        return 0

    from app.services.note_store import normalize_note_name

    changed: list[dict] = []
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, note_name, note_raw FROM perfume_notes")
        ).fetchall()

        for row_id, note_name, note_raw in rows:
            if not note_raw:
                continue  # nothing to re-derive from; leave untouched
            new_name = normalize_note_name(note_raw)
            if not new_name or len(new_name) < 2 or new_name == note_name:
                continue
            changed.append({"i": row_id, "n": new_name})

        for start in range(0, len(changed), 500):
            conn.execute(
                text("UPDATE perfume_notes SET note_name = :n WHERE id = :i"),
                changed[start:start + 500],
            )

    if changed:
        sample = [(c["n"]) for c in changed[:8]]
        logger.info(
            "Re-normalized %s/%s perfume_notes rows to current normalization rules (e.g. %s)",
            len(changed), len(rows), sample,
        )
    return len(changed)


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

    # Charset conversion is self-guarding (per-table try/except) and must not
    # be able to abort startup, so it runs outside the raising block above.
    converted = migrate_utf8mb4(engine)
    if converted:
        logger.info("Migration complete — converted to utf8mb4: %s", ", ".join(converted))

    # Data (not schema) backfill — same rule: a failure here must never stop
    # the app from starting, since the stale note tokens it fixes only degrade
    # match quality rather than breaking the chatbot outright.
    try:
        renormalize_perfume_notes(engine)
    except Exception as e:
        logger.error("perfume_notes re-normalization failed (matching may use stale tokens): %s", e)
