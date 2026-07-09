from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base
import re

class CustomData(Base):
    __tablename__ = "custom_data"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    value = Column(Text, nullable=False)
    shop = Column(String(255), nullable=False, index=True)
    is_enabled = Column(Integer, default=1)  # 1 = enabled/active, 0 = disabled/inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "value": self.value,
            "shop": self.shop,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def to_document_text(self) -> str:
        """Convert custom data to searchable text for embedding"""
        # Clean HTML from value
        clean_value = re.sub(r'<[^>]+>', ' ', self.value)
        clean_value = re.sub(r'\s+', ' ', clean_value).strip()
        
        return f"Title: {self.title}\nContent: {clean_value}"