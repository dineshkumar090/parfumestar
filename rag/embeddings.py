"""LangChain OpenAI embeddings wrapper."""

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.rag.constants import EMBEDDING_MODEL


@lru_cache(maxsize=32)
def get_embeddings(api_key: str) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=api_key,
        dimensions=512,
        
    )


async def embed_query_async(embeddings: OpenAIEmbeddings, text: str) -> list[float]:
    return await embeddings.aembed_query(text)


def embed_query(embeddings: OpenAIEmbeddings, text: str) -> list[float]:
    return embeddings.embed_query(text)
