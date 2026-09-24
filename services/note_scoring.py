"""Fragrance-note match scoring.

THE PROBLEM WITH TREATING EVERY NOTE EQUALLY
────────────────────────────────────────────
Measured on the live catalog (1,290 products carrying notes):

    floral      on 51.6% of products
    boise       on 41.9%
    musc        on 40.7%
    vanille     on 37.0%
    ...
    osmanthus   on  0.16%

Plain set overlap gives all of these the same vote. Two perfumes that share
only {musc, vanille, ambre, floral} — a combination roughly a third of the
catalog satisfies — score a perfect 100%, while a genuinely distinctive
shared accord like {osmanthus, cade, immortelle} scores no higher. That is
precisely why reported match percentages looked arbitrary.

WHAT THIS MODULE DOES INSTEAD
─────────────────────────────
Standard information-retrieval weighting, the same principle behind TF-IDF
ranking in a search engine:

  * IDF WEIGHTING — a note contributes in proportion to how RARE it is.
    Matching "osmanthus" is strong evidence two perfumes are alike;
    matching "musc" is almost none. IDF is computed from the catalog
    itself, so it adapts as the catalog changes rather than relying on a
    hand-tuned list of "important" notes.
  * LAYER WEIGHTING — heart notes define a fragrance's character, top notes
    evaporate in minutes.
  * HIERARCHY CREDIT — "Jasmin Sambac" against "Jasmin" is a near miss, not
    a miss (see note_taxonomy.PARENTS).
  * FAMILIES AS A PENALTY ON THE GAP — olfactive families are far too
    common to sit in the same pool as ingredients and too coarse to add
    score on their own, so family disagreement only discounts the part of a
    match that is not already covered by real notes.

COVERAGE OF THE REFERENCE, NOT JACCARD
──────────────────────────────────────
The denominator is the REFERENCE's notes — how much of what the customer
asked for does this candidate actually reproduce. Extra notes on the
candidate never reduce the score, so a Shopify product that describes
itself in more detail is not punished for it. If every note the reference
is known for is present in the candidate, that is 100%.

The denominator is deliberately NOT "the smaller side": that inverts the
meaning when the candidate is thinner and flatters sparse products. It is
how a 1-note-in-common pairing (Carolina Herrera vs a 3-note coconut
perfume) once reported 48%.
"""

from __future__ import annotations

import logging
import math
import time

from app.services.note_taxonomy import expand, family_of, is_junk_note

logger = logging.getLogger("uvicorn.error")

# Relative importance of each olfactive layer. Heart notes carry a
# fragrance's identity; top notes are gone within minutes of application.
LAYER_WEIGHTS: dict[str, float] = {"heart": 1.0, "base": 0.9, "top": 0.7}

# Family agreement can only PENALIZE the uncovered part of a match — it can
# neither create a match nor dent a complete one.
#
#   score = ingredient * (1 - FAMILY_PENALTY * (1 - family) * (1 - ingredient))
#
# Two constraints forced this shape:
#   1. Family must not manufacture a match. As an additive term it lifted
#      Carolina Herrera vs "Star n°2510 - Coconut" (one shared note in
#      seventeen) to 25% purely because both are "floral" — a family on 51.6%
#      of the catalog.
#   2. Complete note coverage must read 100%, which is the explicit rule for
#      this engine. A plain multiplier broke it: "Star.030 - Agua de Rosas"
#      reproduces all 9 notes of Agua Fresca de Rosas, but the two sources
#      labelled its families differently (an extraction artefact, not a real
#      difference) and it was docked to 92%.
#
#   ingredient 1.00, any family     -> 1.00   (complete coverage is complete)
#   ingredient 0.07, family 1.00    -> 0.07   (family cannot rescue a miss)
#   ingredient 0.50, family 0.00    -> 0.425  (disagreeing families: mild penalty)
FAMILY_PENALTY = 0.30

# Credit for a varietal/base match ("jasmin_sambac" vs "jasmin") — clearly
# better than nothing, clearly weaker than an exact hit.
PARENT_CREDIT = 0.5

# IDF is clamped so one freak note cannot dominate a whole comparison, and
# so a ubiquitous note still carries a little weight rather than zero.
IDF_MIN, IDF_MAX = 1.0, 6.0

# Below this many usable notes on the smaller side, full coverage is not yet
# trustworthy — a reference listing only "Musc, Ambre" would otherwise hit
# 100% against anything containing those two very common notes.
MIN_RELIABLE_NOTES = 3

_IDF_CACHE: dict[str, tuple[float, dict[str, float], float]] = {}
_IDF_TTL = 1800.0


def _idf(df: int, total: int) -> float:
    """Smoothed inverse document frequency, clamped to [IDF_MIN, IDF_MAX]."""
    raw = math.log((total + 1) / (df + 1)) + 1.0
    return max(IDF_MIN, min(IDF_MAX, raw))


def get_note_idf(db) -> tuple[dict[str, float], float]:
    """(idf_by_note, default_idf) computed from the whole catalog.

    One cheap GROUP BY, cached for 30 minutes — note frequencies shift only
    when products are synced. `default_idf` is used for a note absent from
    the table (e.g. one side has a token nothing else in the catalog has),
    and is deliberately HIGH: an unseen note is by definition rare."""
    from app.models.perfume_notes import PerfumeNote
    from sqlalchemy import func

    cached = _IDF_CACHE.get("idf")
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1], cached[2]

    rows = (
        db.query(PerfumeNote.note_name, func.count(func.distinct(PerfumeNote.unified_product_id)))
        .group_by(PerfumeNote.note_name)
        .all()
    )
    total = db.query(func.count(func.distinct(PerfumeNote.unified_product_id))).scalar() or 0
    if not rows or not total:
        logger.info("[SCORING] no note statistics available — falling back to uniform weights")
        return {}, 1.0

    idf = {name: _idf(int(df), total) for name, df in rows if name}
    default = IDF_MAX
    _IDF_CACHE["idf"] = (now + _IDF_TTL, idf, default)
    logger.info(
        "[SCORING] note IDF built from %s products / %s distinct notes "
        "(e.g. floral=%.2f musc=%.2f)",
        total, len(idf), idf.get("floral", 0), idf.get("musc", 0),
    )
    return idf, default


def _usable(by_type: dict[str, set[str]]) -> tuple[dict[str, str], set[str]]:
    """Split a product's notes into (ingredient -> best layer, families).

    Junk extraction artefacts are dropped here so they never inflate a
    coverage denominator. A note appearing in several layers keeps the
    heaviest one."""
    ingredients: dict[str, str] = {}
    families: set[str] = set()
    for note_type, tokens in (by_type or {}).items():
        for token in tokens or ():
            if not token or is_junk_note(token):
                continue
            if note_type == "olfactive":
                fam = family_of(token)
                families.add(fam or token)
                continue
            fam = family_of(token)
            if fam and note_type not in LAYER_WEIGHTS:
                families.add(fam)
                continue
            prev = ingredients.get(token)
            if prev is None or LAYER_WEIGHTS.get(note_type, 0.5) > LAYER_WEIGHTS.get(prev, 0.5):
                ingredients[token] = note_type
    return ingredients, families


def _coverage(
    small: dict[str, str], large: dict[str, str], idf: dict[str, float], default_idf: float,
) -> tuple[float, int, int]:
    """IDF- and layer-weighted coverage of `small` by `large`.

    Returns (score 0-1, exact hits, partial hits)."""
    if not small or not large:
        return 0.0, 0, 0

    large_expanded: set[str] = set()
    for token in large:
        large_expanded |= expand(token)

    total_w = 0.0
    hit_w = 0.0
    exact = partial = 0
    for token, layer in small.items():
        w = idf.get(token, default_idf) * LAYER_WEIGHTS.get(layer, 0.7)
        total_w += w
        if token in large:
            hit_w += w
            exact += 1
        elif expand(token) & large_expanded:
            # One side named a varietal, the other the base note.
            hit_w += w * PARENT_CREDIT
            partial += 1
    return (hit_w / total_w if total_w else 0.0), exact, partial


def score_notes(
    ref_by_type: dict[str, set[str]],
    cand_by_type: dict[str, set[str]],
    idf: dict[str, float] | None = None,
    default_idf: float = 1.0,
) -> tuple[float, dict]:
    """Overall 0-1 similarity plus a breakdown explaining the number.

    `idf` omitted means uniform weights — the scorer still works, it just
    loses the rarity signal, so callers that can reach the DB should pass
    the table from get_note_idf."""
    idf = idf or {}
    ref_ing, ref_fam = _usable(ref_by_type)
    cand_ing, cand_fam = _usable(cand_by_type)

    # Coverage is measured over the REFERENCE — how much of what the customer
    # actually asked for does this candidate reproduce.
    #
    # It must NOT be the smaller side. That inverts the meaning whenever the
    # candidate is the thinner of the two, and rewards sparse products for
    # having little to disagree with: Carolina Herrera (17 notes) against
    # "Star n°2510 - Coconut" (coco, muguet, vanille) shares exactly ONE
    # note, yet scoring over the candidate's 3 notes reported 1/3 -> 48%.
    # Against the reference it is 1/17, which is the honest answer.
    #
    # Extra notes on the CANDIDATE still never reduce the score, which is the
    # property that matters: a Shopify product describing itself in more
    # detail than the reference is not a worse match for it.
    ing_score, exact, partial = _coverage(ref_ing, cand_ing, idf, default_idf)

    if ref_fam and cand_fam:
        fam_score = len(ref_fam & cand_fam) / min(len(ref_fam), len(cand_fam))
    else:
        # A family missing on one side is a data gap, not evidence of
        # difference — fall back to the ingredient score rather than
        # punishing the pair for it.
        fam_score = ing_score

    overall = ing_score * (1.0 - FAMILY_PENALTY * (1.0 - fam_score) * (1.0 - ing_score))

    # Damping now keys off whichever side is thinner: a 3-note candidate
    # judged against a 17-note reference is too little information to report
    # a confident number in EITHER direction.
    n_thin = min(len(ref_ing), len(cand_ing))
    damped = False
    if 0 < n_thin < MIN_RELIABLE_NOTES:
        overall *= 0.5 + 0.5 * (n_thin / MIN_RELIABLE_NOTES)
        damped = True

    breakdown = {
        "ingredient": round(ing_score, 4),
        "family": round(fam_score, 4),
        "exact_hits": exact,
        "partial_hits": partial,
        "ref_notes": len(ref_ing),
        "cand_notes": len(cand_ing),
        "scored_over": len(ref_ing),
        "thinner_side": n_thin,
        "damped": damped,
        "overall": round(overall, 4),
    }
    return overall, breakdown
