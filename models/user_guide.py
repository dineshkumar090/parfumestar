# app/models/user_guide.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.database.db import Base

class UserGuideProgress(Base):
    """
    Track user guide completion status per shop
    """
    __tablename__ = "user_guide_progress"

    id = Column(Integer, primary_key=True, index=True)
    shop = Column(String(255), unique=True, index=True, nullable=False)  # Shopify shop domain
    
    # Guide completion status
    has_completed_guide = Column(Boolean, default=False, nullable=False)
    completed_steps = Column(JSON, default=list)  # List of step IDs completed
    
    # Timestamps
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())