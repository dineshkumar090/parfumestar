
from pydantic import BaseModel
from typing import Optional

class ConfigUpdate(BaseModel):
    shop_url: str
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = "gpt-4"
    openai_temperature: Optional[float] = 0.7
    pinecone_api_key: Optional[str] = None
    pinecone_env: Optional[str] = None
    pinecone_index_name: Optional[str] = None