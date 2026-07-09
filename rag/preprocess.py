"""Query preprocessing and normalization."""

import re
import unicodedata


def preprocess_query(query: str, max_length: int = 800) -> str:
    text = (query or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_length:
        text = text[:max_length]
    return text


def normalize_filter_value(value: str) -> str:
    if not value:
        return ""
    v = value.lower().strip()
    v = re.sub(r"[^\w\s\-]", "", v)
    return re.sub(r"\s+", " ", v)
