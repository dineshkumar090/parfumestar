"""Unified product database — international + Shopify sources."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
    Index,
)
from sqlalchemy.sql import func

from app.database.db import Base


class UnifiedProduct(Base):
    """
    main_database — single table for both international reference perfumes
    and Shopify store products used for sync, embeddings, and recommendations.
    """

    __tablename__ = "main_database"

    id = Column(Integer, primary_key=True, index=True)

    # Source identification
    source_type = Column(String(32), nullable=False, index=True)  # international | shopify
    source_id = Column(String(64), nullable=False, index=True)     # mysql id or shopify_id
    shop_url = Column(String(255), nullable=True, index=True)    # shopify only

    # Product metadata
    title = Column(String(500))
    description = Column(Text)
    handle = Column(String(255))
    featured_image = Column(Text)
    brand = Column(String(255))           # international brand name
    product_type = Column(String(100))  # parfum, body splash, etc.
    gender = Column(String(50))
    year = Column(Integer)
    status = Column(String(50), default="active")
    price = Column(Float)
    vendor = Column(String(255))

    # Fragrance notes
    olfactive = Column(String(500))
    top_note = Column(String(500))
    heart_note = Column(String(500))
    base_note = Column(String(500))
    ingredients = Column(Text)            # raw INCI or note list

    # STANDARDIZED notes — the same values as the raw columns above, run
    # through services/note_standardizer, stored comma-separated. The
    # authoritative per-token data lives in `perfume_notes` (one row per
    # token, which is what matching queries join against); these columns
    # exist so both sides can be eyeballed and diffed directly in SQL,
    # which is how note-matching bugs actually get diagnosed.
    top_note_std = Column(String(1000))
    heart_note_std = Column(String(1000))
    base_note_std = Column(String(1000))
    olfactive_std = Column(String(1000))

    # Shopify-specific
    shopify_gid = Column(String(100))
    metafields = Column(JSON)
    variants = Column(JSON)
    tags = Column(String(500))
    collections = Column(JSON)

    # Pre-linked recommendations from MySQL product_recoms
    linked_shopify_products = Column(JSON)

    # Admin custom data merged at embed time
    custom_data = Column(JSON)

    # Vector sync tracking
    pinecone_id = Column(String(100), index=True)
    embedding_synced_at = Column(DateTime)
    is_enabled = Column(Integer, default=1)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_main_db_source", "source_type", "source_id", unique=True),
    )
