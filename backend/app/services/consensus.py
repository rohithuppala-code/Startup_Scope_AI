# consensus.py
# ---------------------------------------------------------------------------
# FEATURE 1: Multi-Model Consensus Engine
#
# Takes independently-generated reports from Gemini and Groq and merges
# them field-by-field into a single ConsensusReport with per-field
# confidence scores.
#
# MERGE RULES:
#   - Numeric fields (feasibility_score): average both values. Confidence =
#     1.0 - (abs(delta) / 100). If both say 75, confidence = 1.0.
#     If one says 30 and the other says 90, confidence = 0.4.
#
#   - String fields (market_viability, recommended_approach): keep Gemini's
#     version as primary (deeper analysis). Confidence = 1.0 if both models
#     agree in sentiment/direction, 0.5 if they diverge.
#     We use a simple heuristic: if >40% of Groq's key nouns appear in
#     Gemini's text, they agree.
#
#   - List fields (gaps_identified): union of both lists, deduplicated by
#     semantic similarity (simple substring containment check). Confidence =
#     intersection_size / union_size (Jaccard index).
#
#   - Markdown: Gemini's version is used (typically more detailed).
#     Groq's unique insights are appended as a "Second Opinion" section.
# ---------------------------------------------------------------------------

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.schemas.ai_reports import (
    AIReportResponse,
    ConsensusReport,
    FieldConfidence,
    ReportDetails,
)


def _extract_key_nouns(text: str) -> set[str]:
    """
    Extracts a rough set of 'key nouns' from a text for semantic comparison.

    This is intentionally simple — we don't need NLP here. We just want to
    know if two model outputs are talking about roughly the same things.
    Strips common stopwords and keeps words > 3 chars.
    """
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "will", "can", "has", "have", "been", "would", "could", "should",
        "into", "also", "more", "most", "very", "than", "they", "their",
        "there", "some", "what", "when", "which", "about", "each", "make",
        "like", "just", "over", "such", "take", "only", "come", "made",
        "well", "back", "much", "then", "them", "these", "other",
    }
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    return words - stopwords


def _string_similarity(text_a: str, text_b: str) -> float:
    """
    Computes a rough similarity score between two strings using key-noun
    overlap (Jaccard index on extracted nouns).

    Returns a float between 0.0 (no overlap) and 1.0 (identical nouns).
    """
    nouns_a = _extract_key_nouns(text_a)
    nouns_b = _extract_key_nouns(text_b)

    if not nouns_a and not nouns_b:
        return 1.0  # Both empty = agreement
    if not nouns_a or not nouns_b:
        return 0.0

    intersection = nouns_a & nouns_b
    union = nouns_a | nouns_b
    return len(intersection) / len(union) if union else 0.0


def _dedup_gaps(gaps_a: List[str], gaps_b: List[str]) -> List[str]:
    """
    Merges two lists of gap strings, removing near-duplicates.

    A gap from list B is considered a duplicate if >60% of its key nouns
    are contained in any gap from list A (fuzzy dedup).
    """
    merged = list(gaps_a)  # Start with all of A

    for gap_b in gaps_b:
        nouns_b = _extract_key_nouns(gap_b)
        is_duplicate = False

        for gap_a in merged:
            nouns_a = _extract_key_nouns(gap_a)
            if nouns_b and nouns_a:
                overlap = len(nouns_b & nouns_a) / len(nouns_b)
                if overlap > 0.6:
                    is_duplicate = True
                    break

        if not is_duplicate:
            merged.append(gap_b)

    return merged


def merge_reports(
    gemini_report: Dict[str, Any],
    gemini_markdown: str,
    gemini_model: str,
    groq_report: Dict[str, Any],
    groq_markdown: str,
    groq_model: str,
) -> ConsensusReport:
    """
    Merges Gemini and Groq reports into a single ConsensusReport.

    This is the core of the multi-model consensus engine. Each field
    is compared and merged according to its type, and a confidence
    score is computed for each field.

    Args:
        gemini_report: Gemini's report_json (dict from ReportDetails).
        gemini_markdown: Gemini's long-form markdown analysis.
        gemini_model: Gemini model version string.
        groq_report: Groq's report_json (dict from ReportDetails).
        groq_markdown: Groq's long-form markdown analysis.
        groq_model: Groq model version string.

    Returns:
        ConsensusReport with merged fields, per-field confidence, and
        overall confidence score.
    """
    field_agreements: List[FieldConfidence] = []

    # ── 1. FEASIBILITY SCORE (numeric merge: average + confidence) ────────
    gemini_score = gemini_report.get("feasibility_score", 50)
    groq_score = groq_report.get("feasibility_score", 50)
    merged_score = round((gemini_score + groq_score) / 2)
    score_confidence = 1.0 - (abs(gemini_score - groq_score) / 100.0)

    field_agreements.append(FieldConfidence(
        field_name="feasibility_score",
        gemini_value=str(gemini_score),
        groq_value=str(groq_score),
        confidence=round(score_confidence, 3),
        status="agreed" if score_confidence >= 0.8 else "averaged",
    ))

    # ── 2. MARKET VIABILITY (string merge: Gemini primary + similarity) ───
    gemini_viability = gemini_report.get("market_viability", "")
    groq_viability = groq_report.get("market_viability", "")
    viability_sim = _string_similarity(gemini_viability, groq_viability)
    # Use Gemini's version as primary (deeper analysis model)
    merged_viability = gemini_viability

    field_agreements.append(FieldConfidence(
        field_name="market_viability",
        gemini_value=gemini_viability[:100],
        groq_value=groq_viability[:100],
        confidence=round(viability_sim, 3),
        status="agreed" if viability_sim >= 0.5 else "divergent",
    ))

    # ── 3. GAPS IDENTIFIED (list merge: union + dedup) ────────────────────
    gemini_gaps = gemini_report.get("gaps_identified", [])
    groq_gaps = groq_report.get("gaps_identified", [])
    merged_gaps = _dedup_gaps(gemini_gaps, groq_gaps)

    # Jaccard-like confidence: how much did the models agree?
    if gemini_gaps and groq_gaps:
        # Count how many Groq gaps were duplicates of Gemini gaps
        unique_groq = len(merged_gaps) - len(gemini_gaps)
        total_unique = len(merged_gaps)
        gaps_confidence = 1.0 - (unique_groq / total_unique) if total_unique > 0 else 1.0
    else:
        gaps_confidence = 0.5  # One model returned no gaps

    field_agreements.append(FieldConfidence(
        field_name="gaps_identified",
        gemini_value=f"{len(gemini_gaps)} gaps",
        groq_value=f"{len(groq_gaps)} gaps",
        confidence=round(max(0.0, min(1.0, gaps_confidence)), 3),
        status="agreed" if gaps_confidence >= 0.6 else "divergent",
    ))

    # ── 4. RECOMMENDED APPROACH (string merge: Gemini primary) ────────────
    gemini_approach = gemini_report.get("recommended_approach", "")
    groq_approach = groq_report.get("recommended_approach", "")
    approach_sim = _string_similarity(gemini_approach, groq_approach)

    field_agreements.append(FieldConfidence(
        field_name="recommended_approach",
        gemini_value=gemini_approach[:100],
        groq_value=groq_approach[:100],
        confidence=round(approach_sim, 3),
        status="agreed" if approach_sim >= 0.5 else "divergent",
    ))

    # ── 5. MARKDOWN (Gemini primary + Groq "Second Opinion" appendix) ────
    merged_markdown = gemini_markdown
    if groq_markdown:
        merged_markdown += (
            "\n\n---\n\n"
            "## 🤖 Second Opinion (Groq / Llama 3.1 70B)\n\n"
            f"{groq_markdown}"
        )

    # ── 6. COMPUTE OVERALL CONFIDENCE ────────────────────────────────────
    # Weighted average: feasibility_score gets 2x weight (most impactful)
    weights = {
        "feasibility_score": 2.0,
        "market_viability": 1.5,
        "gaps_identified": 1.0,
        "recommended_approach": 1.5,
    }
    total_weight = sum(weights.values())
    weighted_sum = sum(
        fa.confidence * weights.get(fa.field_name, 1.0)
        for fa in field_agreements
    )
    overall_confidence = round(weighted_sum / total_weight, 3) if total_weight > 0 else 0.5

    # ── BUILD CONSENSUS REPORT ───────────────────────────────────────────
    consensus = ConsensusReport(
        report=ReportDetails(
            feasibility_score=merged_score,
            market_viability=merged_viability,
            gaps_identified=merged_gaps,
            recommended_approach=gemini_approach,  # Gemini primary
        ),
        markdown=merged_markdown,
        overall_confidence=overall_confidence,
        field_agreement=field_agreements,
        gemini_model=gemini_model,
        groq_model=groq_model,
    )

    print(
        f"[Consensus] Merged: score={merged_score}, "
        f"confidence={overall_confidence}, "
        f"gaps={len(merged_gaps)}, "
        f"agreement={'strong' if overall_confidence >= 0.7 else 'weak'}",
        flush=True,
    )

    return consensus
