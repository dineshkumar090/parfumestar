from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.db import Base
import json

class ProductDetail(Base):
    __tablename__ = "product_details"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    shop_url = Column(String(255), nullable=False, index=True)
    
    # Custom fields for additional product information
    field_name = Column(String(255), nullable=False)  # e.g., "contraindications", "benefits", "serving_tips", "storage"
    field_value = Column(Text, nullable=True)
    field_type = Column(String(50), default="text")  # text, html, json
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String(100), nullable=True)  # admin email or user ID
    
    # Status
    is_active = Column(Integer, default=1)  # 1 = active, 0 = inactive
    
    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "field_name": self.field_name,
            "field_value": self.field_value,
            "field_type": self.field_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
        }