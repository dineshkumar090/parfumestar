from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database.db import Base 

class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), unique=True, nullable=False)
    access_token = Column(String(255), nullable=False)

    chatbot_enabled = Column(String(50), default="off")
    created_at = Column(DateTime, server_default=func.now())
    openai_api_key = Column(String(255))
    openai_model = Column(String(100), default='gpt-4.1')
    assistant_tone = Column(String(50), default='professional')
    system_prompt = Column(Text)
    pinecone_api_key = Column(String(255))
    pinecone_index_name = Column(String(100))
    pinecone_environment = Column(String(100))