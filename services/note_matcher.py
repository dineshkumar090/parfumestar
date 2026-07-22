"""SQL-based fragrance note matching — international reference → Shopify products."""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import NOTES_MATCH_CANDIDATE_POOL, NOTES_MATCH_MIN_SIMILARITY
from app.models.main_database import UnifiedProduct
from app.models.perfume_notes import PerfumeNote
from app.models.products import Product
from app.rag.constants import SOURCE_INTERNATIONAL, SOURCE_SHOPIFY
from app.rag.vector_store import format_product_hit

logger = logging.getLogger("uvicorn.error")

# How much each note category contributes to the overall similarity score.
# Heart notes define a fragrance's core character and are weighted highest;
# top notes fade within minutes so they matter less; olfactive family
# (Floral/Oriental/...) is a coarse but reliable category-level signal.
_NOTE_TYPE_WEIGHTS: dict[str, float] = {
    "heart": 0.35,
    "top": 0.25,
    "base": 0.25,
    "olfactive": 0.15,
}


def find_unified_by_pinecone_id(db: Session, pinecone_id: str) -> UnifiedProduct | None:
    logger.info("[NOTES] find_unified_by_pinecone_id(%r)", pinecone_id)
    if pinecone_id.startswith("intl_"):
        source_id = pinecone_id.replace("intl_", "")
        row = db.query(UnifiedProduct).filter_by(
            source_type=SOURCE_INTERNATIONAL,
            source_id=source_id,
        ).first()
    else:
        row = db.query(UnifiedProduct).filter(
            (UnifiedProduct.pinecone_id == pinecone_id)
            | (UnifiedProduct.id == pinecone_id)
        ).first()
    logger.info(
        "[NOTES] -> unified row %s (%s)",
        row.id if row else None, (row.title[:40] if row and row.title else None),
    )
    return row


def _shopify_id_from_gid(gid: str | None) -> str | None:
    """'gid://shopify/Product/9991582089562' -> '9991582089562'."""
    if not gid:
        return None
    tail = gid.rsplit("/", 1)[-1]
    return tail if tail.isdigit() else None


def _notes_by_type(db: Session, unified_product_id: int) -> dict[str, set[str]]:
    """A single product's notes grouped by note_type, as sets (for Jaccard)."""
    grouped: dict[str, set[str]] = {}
    for note_type, note_name in db.query(
        PerfumeNote.note_type, PerfumeNote.note_name
    ).filter(PerfumeNote.unified_product_id == unified_product_id).all():
        grouped.setdefault(note_type, set()).add(note_name)
    return grouped


def _notes_by_type_bulk(db: Session, unified_product_ids: list[int]) -> dict[int, dict[str, set[str]]]:
    """Same as _notes_by_type but for many products in one query — avoids an
    N+1 query pattern when scoring a whole candidate pool."""
    if not unified_product_ids:
        return {}
    grouped: dict[int, dict[str, set[str]]] = {}
    rows = db.query(
        PerfumeNote.unified_product_id, PerfumeNote.note_type, PerfumeNote.note_name
    ).filter(PerfumeNote.unified_product_id.in_(unified_product_ids)).all()
    for pid, note_type, note_name in rows:
        grouped.setdefault(pid, {}).setdefault(note_type, set()).add(note_name)
    return grouped


def weighted_note_similarity(
    ref_by_type: dict[str, set[str]], cand_by_type: dict[str, set[str]],
) -> tuple[float, dict[str, tuple[int, int, float]]]:
    """Category-weighted Jaccard similarity between two products' notes.

    Matches COMPLETE normalized notes only (set membership — never substring
    or character-level comparison), so "abricot" can never accidentally
    match "abri". Each category (top/heart/base/olfactive) contributes
    intersection/union scaled by its weight; categories absent from both
    sides are excluded from the denominator so a product with no
    olfactive-family data isn't unfairly penalized relative to one that has
    it. Returns (overall 0-1 score, {category: (intersection, union, cat_score)})
    for transparent logging/debugging of exactly why a score came out the
    way it did."""
    total_weight = 0.0
    weighted_sum = 0.0
    breakdown: dict[str, tuple[int, int, float]] = {}
    for note_type, weight in _NOTE_TYPE_WEIGHTS.items():
        ref_set = ref_by_type.get(note_type, set())
        cand_set = cand_by_type.get(note_type, set())
        if not ref_set and not cand_set:
            continue
        inter = len(ref_set & cand_set)
        union = len(ref_set | cand_set)
        cat_score = (inter / union) if union else 0.0
        breakdown[note_type] = (inter, union, cat_score)
        total_weight += weight
        weighted_sum += weight * cat_score
    overall = (weighted_sum / total_weight) if total_weight else 0.0
    return overall, breakdown


def shopify_products_from_curated_links(
    db: Session, intl_row: UnifiedProduct, shop: str, store_base_url: str,
) -> list[dict]:
    """The international source DB (product_recoms) ships a hand-curated
    `is_recommended` field naming the exact Shopify dupe(s) for each
    international perfume — real ground truth, not a heuristic. It's synced
    into UnifiedProduct.linked_shopify_products. This looks it up and returns
    those exact products (still scoped to this shop and still requiring them
    to be active + AI-enabled), each annotated with its ACTUAL note
    similarity against the reference — computed, not assumed — so the
    curated pick is shown with an honest confidence percentage rather than
    silently implying a perfect match it may not have."""
    links = intl_row.linked_shopify_products
    if not isinstance(links, list) or not links:
        logger.info("[NOTES] curated links | unified %s has none", intl_row.id)
        return []

    shopify_ids = [sid for sid in (_shopify_id_from_gid(l.get("productId")) for l in links) if sid]
    logger.info(
        "[NOTES] curated links | unified %s -> %s candidate shopify_id(s): %s",
        intl_row.id, len(shopify_ids), shopify_ids,
    )
    if not shopify_ids:
        return []

    rows = db.query(UnifiedProduct).filter(
        UnifiedProduct.source_type == SOURCE_SHOPIFY,
        UnifiedProduct.shop_url == shop,
        UnifiedProduct.source_id.in_(shopify_ids),
        UnifiedProduct.is_enabled == 1,
    ).all()
    # Preserve the curator's original ranking (recomProduct1 first, etc.)
    # rather than whatever order the SQL IN() clause happens to return.
    order = {sid: i for i, sid in enumerate(shopify_ids)}
    rows.sort(key=lambda r: order.get(r.source_id, len(shopify_ids)))
    logger.info(
        "[NOTES] curated links | %s/%s candidates are active+enabled in this shop's catalog: %s",
        len(rows), len(shopify_ids), [(r.source_id, (r.title or "")[:28]) for r in rows],
    )
    if not rows:
        return []

    ref_by_type = _notes_by_type(db, intl_row.id)
    cand_notes = _notes_by_type_bulk(db, [r.id for r in rows])
    scores = []
    for row in rows:
        score, breakdown = weighted_note_similarity(ref_by_type, cand_notes.get(row.id, {}))
        scores.append(score)
        logger.info(
            "[NOTES]   curated #%s %r | notes similarity=%.0f%% breakdown=%s",
            row.id, (row.title or "")[:40], score * 100,
            {k: f"{i}/{u}={c:.2f}" for k, (i, u, c) in breakdown.items()},
        )
    return unified_to_widget_products(db, rows, store_base_url, scores)


def match_shopify_by_sql_notes(
    db: Session,
    international_unified_id: int,
    shop: str,
    top_k: int = 5,
    gender: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_similarity: float = NOTES_MATCH_MIN_SIMILARITY,
) -> list[tuple[UnifiedProduct, float]]:
    """Find the Shopify products whose fragrance notes are most similar to an
    international reference product's.

    Two-phase: (1) SQL generates a broad CANDIDATE pool — any Shopify product
    sharing at least one normalized note with the reference, respecting
    shop/gender/price/enabled filters — capped at NOTES_MATCH_CANDIDATE_POOL
    for query performance; (2) full note sets (not just the overlapping
    ones) are fetched in bulk and scored in Python with a proper
    category-weighted Jaccard similarity (see weighted_note_similarity),
    which is what actually determines ranking. The previous version ranked
    candidates purely by raw overlap COUNT, ignoring note_type entirely and
    with no floor — a product sharing 1 note out of 15 could still "win" if
    it was the only candidate found. Results below min_similarity are
    dropped rather than confidently presented as a match.

    Returns (UnifiedProduct, similarity 0-1) sorted by similarity desc.
    """
    logger.info(
        "[NOTES] match_shopify_by_sql_notes | intl_unified_id=%s shop=%s top_k=%s gender=%s "
        "price=[%s,%s] min_similarity=%s",
        international_unified_id, shop, top_k, gender, min_price, max_price, min_similarity,
    )
    ref_by_type = _notes_by_type(db, international_unified_id)
    ref_note_names = set().union(*ref_by_type.values()) if ref_by_type else set()
    logger.info("[NOTES] reference (international) notes by type=%s", ref_by_type)
    if not ref_note_names:
        logger.info("[NOTES] international product has NO notes stored — cannot note-match")
        return []

    # ── Phase 1: candidate generation (SQL) ────────────────────────────
    candidate_q = (
        db.query(
            PerfumeNote.unified_product_id,
            func.count(PerfumeNote.id).label("raw_overlap"),
        )
        .join(UnifiedProduct, UnifiedProduct.id == PerfumeNote.unified_product_id)
        .filter(
            UnifiedProduct.source_type == SOURCE_SHOPIFY,
            UnifiedProduct.shop_url == shop,
            UnifiedProduct.is_enabled == 1,
            PerfumeNote.note_name.in_(ref_note_names),
        )
    )
    if gender and gender != "mixte":
        candidate_q = candidate_q.filter(
            (UnifiedProduct.gender == gender)
            | (UnifiedProduct.gender == "mixte")
            | (UnifiedProduct.gender.is_(None))
            | (UnifiedProduct.gender == "")
        )
    if min_price is not None:
        candidate_q = candidate_q.filter(UnifiedProduct.price >= min_price)
    if max_price is not None:
        candidate_q = candidate_q.filter(UnifiedProduct.price <= max_price)

    candidate_rows = (
        candidate_q
        .group_by(PerfumeNote.unified_product_id)
        .order_by(func.count(PerfumeNote.id).desc())
        .limit(NOTES_MATCH_CANDIDATE_POOL)
        .all()
    )
    candidate_ids = [pid for pid, _ in candidate_rows]
    logger.info("[NOTES] candidate pool (>=1 shared note): %s", len(candidate_ids))
    if not candidate_ids:
        logger.info("[NOTES] match_shopify_by_sql_notes -> 0 results (no candidates)")
        return []

    # ── Phase 2: full-note weighted scoring (Python) ───────────────────
    cand_notes = _notes_by_type_bulk(db, candidate_ids)
    scored: list[tuple[int, float, dict]] = []
    for pid in candidate_ids:
        score, breakdown = weighted_note_similarity(ref_by_type, cand_notes.get(pid, {}))
        scored.append((pid, score, breakdown))
    scored.sort(key=lambda x: x[1], reverse=True)

    kept = [s for s in scored if s[1] >= min_similarity][:top_k]
    dropped = len(scored) - len(kept)
    logger.info(
        "[NOTES] weighted scoring | %s candidates scored, %s below %.0f%% threshold dropped, %s kept",
        len(scored), dropped, min_similarity * 100, len(kept),
    )

    if not kept:
        # Nothing cleared the bar — show the best miss anyway, for debugging.
        if scored:
            pid, score, breakdown = scored[0]
            logger.info(
                "[NOTES] best candidate #%s still only %.0f%% similar (breakdown=%s) — below floor, no note match returned",
                pid, score * 100, {k: f"{i}/{u}={c:.2f}" for k, (i, u, c) in breakdown.items()},
            )
        return []

    rows_by_id = {
        r.id: r for r in db.query(UnifiedProduct).filter(UnifiedProduct.id.in_([pid for pid, _, _ in kept])).all()
    }
    results: list[tuple[UnifiedProduct, float]] = []
    for pid, score, breakdown in kept:
        row = rows_by_id.get(pid)
        if not row:
            continue
        logger.info(
            "[NOTES]   shopify #%s %r | similarity=%.0f%% breakdown=%s",
            pid, (row.title or "")[:40], score * 100,
            {k: f"{i}/{u}={c:.2f}" for k, (i, u, c) in breakdown.items()},
        )
        results.append((row, score))
    logger.info("[NOTES] match_shopify_by_sql_notes -> %s results", len(results))
    return results


def unified_to_widget_products(
    db: Session,
    unified_rows: list[UnifiedProduct],
    store_base_url: str,
    scores: list[float] | None = None,
) -> list[dict]:
    """Convert main_database Shopify rows to widget product card format."""
    products = []
    skipped = 0
    for i, row in enumerate(unified_rows):
        product = db.query(Product).filter_by(shopify_id=int(row.source_id)).first()
        if not product:
            skipped += 1
            logger.info(
                "[NOTES] unified_to_widget: no Product row for shopify_id=%s (unified %s) — skipped",
                row.source_id, row.id,
            )
            continue
        meta = {
            "id": str(product.id),
            "shopify_id": str(product.shopify_id),
            "title": product.title or "",
            "handle": product.handle or "",
            "description": product.description or "",
            "price": float(product.price or 0),
            "category": product.product_type or "",
            "image_url": product.image_url or "",
            "top_note": row.top_note or "",
            "heart_note": row.heart_note or "",
            "base_note": row.base_note or "",
            "olfactive": row.olfactive or "",
            "gender": row.gender or "",
            "source_type": SOURCE_SHOPIFY,
        }
        score = scores[i] if scores else 0.0
        if scores:
            meta["notes_similarity_pct"] = round(score * 100)
        if product.variants and isinstance(product.variants, list) and product.variants:
            v0 = product.variants[0]
            if isinstance(v0, dict):
                meta["compare_at_price"] = float(v0.get("compare_at_price") or 0)
                meta["variant_id"] = v0.get("id")
        hit = format_product_hit(meta, store_base_url, score=score)
        products.append(hit)
    logger.info(
        "[NOTES] unified_to_widget_products | %s converted, %s skipped",
        len(products), skipped,
    )
    return products
