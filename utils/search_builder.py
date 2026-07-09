def build_search_text(title: str, description: str) -> str:
    parts = [
        title or "",
        description or ""
    ]
    return " | ".join(p for p in parts if p)
