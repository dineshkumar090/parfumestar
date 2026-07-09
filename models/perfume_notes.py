"""Normalized fragrance notes for fast SQL matching between international and Shopify products."""

from sqlalchemy import Column, ForeignKey, Index, Integer, String
from app.database.db import Base


class PerfumeNote(Base):
    """
    One row per note token. Enables SQL like:
      SELECT unified_product_id, COUNT(*) FROM perfume_notes
      WHERE note_name IN (...) AND source_type='shopify' GROUP BY unified_product_id
    """

    __tablename__ = "perfume_notes"

    id = Column(Integer, primary_key=True, index=True)
    unified_product_id = Column(
        Integer,
        ForeignKey("main_database.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = Column(String(32), nullable=False, index=True)  # international | shopify
    note_type = Column(String(32), nullable=False, index=True)    # olfactive | top | heart | base
    note_name = Column(String(255), nullable=False, index=True)   # normalized (lowercase, no accents)
    note_raw = Column(String(255))                                # display form

    __table_args__ = (
        Index("ix_perfume_notes_match", "source_type", "note_name"),
        Index("ix_perfume_notes_product_type", "unified_product_id", "note_type"),
    )
