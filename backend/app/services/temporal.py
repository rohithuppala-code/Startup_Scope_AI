# temporal.py
# ---------------------------------------------------------------------------
# FEATURE 4: Temporal Trend Tracking
#
# Pure internal logic — no external APIs needed.
#
# PIPELINE:
#   1. DIFF: Uses `deepdiff` to produce a structured diff between the
#      old report and the new report.
#   2. NARRATE: Gemini generates a natural-language change summary
#      explaining what changed and why it matters.
#   3. SCORE: Computes a significance score (0.0–1.0) based on the
#      magnitude of changes.
#   4. STORE: Writes versioned snapshots to the `report_versions` table.
#
# SCHEDULING: Celery Beat (RedBeat) handles the weekly re-run schedule.
# See worker/celery_beat.py for the Beat configuration.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from deepdiff import DeepDiff

from app.core.config import settings
from app.services.ai_pipeline import _get_gemini
from app.schemas.ai_reports import FieldChange, TemporalDiff
from google.genai import types as genai_types


# =====================================================================
# STEP 1: STRUCTURAL DIFF
#
# Uses deepdiff to produce a comprehensive diff between two JSON reports.
# Converts the deepdiff output into our FieldChange schema for storage.
# =====================================================================

def diff_reports(
    old_report: Dict[str, Any],
    new_report: Dict[str, Any],
) -> Tuple[List[FieldChange], Dict[str, Any]]:
    """
    Produces a structured diff between two report JSON objects.

    Args:
        old_report: The previous version's report_json.
        new_report: The current version's report_json.

    Returns:
        Tuple of (list_of_field_changes, raw_deepdiff_dict).
        The raw deepdiff dict is stored as-is for debugging.
    """
    # DeepDiff with text comparison threshold for fuzzy string matching
    diff = DeepDiff(
        old_report,
        new_report,
        ignore_order=True,           # List order doesn't matter for gaps
        verbose_level=2,             # Include old+new values
        exclude_regex_paths=[r".*timestamp.*", r".*updated_at.*"],  # Skip metadata
    )

    # Convert to serializable dict
    raw_diff = json.loads(diff.to_json()) if diff else {}

    # Parse into FieldChange objects
    changes: List[FieldChange] = []

    # Handle value changes
    for path, detail in raw_diff.get("values_changed", {}).items():
        changes.append(FieldChange(
            field_path=_clean_path(path),
            old_value=str(detail.get("old_value", "")),
            new_value=str(detail.get("new_value", "")),
            change_type="value_changed",
        ))

    # Handle items added to lists
    for path, value in raw_diff.get("iterable_item_added", {}).items():
        changes.append(FieldChange(
            field_path=_clean_path(path),
            old_value="",
            new_value=str(value),
            change_type="item_added",
        ))

    # Handle items removed from lists
    for path, value in raw_diff.get("iterable_item_removed", {}).items():
        changes.append(FieldChange(
            field_path=_clean_path(path),
            old_value=str(value),
            new_value="",
            change_type="item_removed",
        ))

    # Handle new keys added
    for path, value in raw_diff.get("dictionary_item_added", {}).items():
        changes.append(FieldChange(
            field_path=_clean_path(path),
            old_value="",
            new_value=str(value)[:200],
            change_type="item_added",
        ))

    # Handle keys removed
    for path, value in raw_diff.get("dictionary_item_removed", {}).items():
        changes.append(FieldChange(
            field_path=_clean_path(path),
            old_value=str(value)[:200],
            new_value="",
            change_type="item_removed",
        ))

    print(f"[Temporal] Found {len(changes)} changes between report versions.", flush=True)
    return changes, raw_diff


def _clean_path(deepdiff_path: str) -> str:
    """
    Converts a deepdiff path like "root['report']['feasibility_score']"
    into a dot-notation path like "report.feasibility_score".
    """
    return (
        deepdiff_path
        .replace("root", "")
        .replace("['", ".")
        .replace("']", "")
        .replace("[", ".")
        .replace("]", "")
        .lstrip(".")
    )


# =====================================================================
# STEP 2: SIGNIFICANCE SCORING
#
# Computes how significant the changes are on a 0.0–1.0 scale.
# Higher scores indicate fundamental shifts in the analysis.
# =====================================================================

def compute_significance(
    changes: List[FieldChange],
    old_report: Dict[str, Any],
    new_report: Dict[str, Any],
) -> float:
    """
    Scores the significance of changes between two report versions.

    Weights:
      - feasibility_score change: high weight (delta / 100)
      - market_viability change: medium weight
      - gaps_identified changes: medium weight
      - recommended_approach change: medium weight
      - Other changes: low weight

    Returns:
        Float between 0.0 (trivial) and 1.0 (fundamental shift).
    """
    if not changes:
        return 0.0

    score = 0.0

    for change in changes:
        path = change.field_path.lower()

        if "feasibility_score" in path:
            # Feasibility score change: proportional to delta magnitude
            try:
                old_val = int(change.old_value)
                new_val = int(change.new_value)
                score += abs(new_val - old_val) / 100.0 * 0.4  # Up to 0.4
            except (ValueError, TypeError):
                score += 0.1

        elif "market_viability" in path:
            score += 0.2  # Any change in viability assessment is notable

        elif "gaps_identified" in path:
            score += 0.1  # Each gap change contributes 0.1

        elif "recommended_approach" in path:
            score += 0.2  # Strategy change is significant

        else:
            score += 0.05  # Minor fields

    return round(min(1.0, score), 3)


# =====================================================================
# STEP 3: NATURAL-LANGUAGE CHANGE NARRATIVE
#
# Gemini generates a human-readable summary of what changed and why.
# =====================================================================

def generate_change_narrative(
    changes: List[FieldChange],
    idea_description: str,
    old_report: Dict[str, Any],
    new_report: Dict[str, Any],
) -> str:
    """
    Uses Gemini to generate a natural-language narrative of changes.

    Args:
        changes: List of FieldChange objects from diff_reports().
        idea_description: The original startup idea.
        old_report: Previous version's report_json.
        new_report: Current version's report_json.

    Returns:
        Markdown narrative summarizing the changes.
    """
    if not changes:
        return "No significant changes detected between report versions."

    client = _get_gemini(task="temporal")

    # Build a concise change summary for the prompt
    changes_text = "\n".join(
        f"- {c.field_path}: '{c.old_value[:100]}' → '{c.new_value[:100]}' ({c.change_type})"
        for c in changes[:20]  # Cap at 20 to save tokens
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"Startup Idea: {idea_description}\n\n"
                f"Changes detected between report v{len(changes)} and previous version:\n"
                f"{changes_text}\n\n"
                f"Old feasibility score: {old_report.get('feasibility_score', 'N/A')}\n"
                f"New feasibility score: {new_report.get('feasibility_score', 'N/A')}\n"
            ),
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "You are a market analyst tracking changes in a startup validation report "
                    "over time. Write a concise 2-3 paragraph narrative explaining:\n"
                    "1. What changed and in what direction\n"
                    "2. Why these changes might have occurred (market shifts, new competitors, etc.)\n"
                    "3. What the founder should pay attention to\n\n"
                    "Be specific and actionable. Use markdown formatting."
                ),
                temperature=0.5,
            ),
        )
        return response.text or "Change narrative generation failed."
    except Exception as e:
        print(f"[Temporal] Narrative generation failed: {e}", flush=True)
        return f"Change narrative unavailable: {e}"


# =====================================================================
# STEP 4: STORE VERSIONED SNAPSHOT
#
# Writes the new report version to the report_versions table along
# with the diff, narrative, and significance score.
# =====================================================================

def store_version(
    validation_id: str,
    report_json: Dict[str, Any],
    markdown_report: str,
    diff_summary: Dict[str, Any],
    change_narrative: str,
    significance_score: float,
    version_number: int,
    tokens_used: int = 0,
    estimated_cost: float = 0.0,
    model_version: str = "",
) -> bool:
    """
    Stores a versioned report snapshot in the report_versions table.

    Args:
        validation_id: The validation this version belongs to.
        report_json: The complete report JSON for this version.
        markdown_report: The markdown analysis for this version.
        diff_summary: Raw deepdiff output (JSONB).
        change_narrative: Gemini-generated narrative.
        significance_score: 0.0–1.0 significance.
        version_number: Sequential version number.
        tokens_used: Tokens consumed for this re-run.
        estimated_cost: Cost estimate for this re-run.
        model_version: Model(s) used for this re-run.

    Returns:
        True if stored successfully, False otherwise.
    """
    from app.services.rag import _get_supabase
    supabase = _get_supabase()

    try:
        supabase.table("report_versions").insert({
            "validation_id": validation_id,
            "version_number": version_number,
            "report_json": report_json,
            "markdown_report": markdown_report,
            "diff_summary": diff_summary,
            "change_narrative": change_narrative,
            "tokens_used": tokens_used,
            "estimated_cost": estimated_cost,
            "model_version": model_version,
        }).execute()

        print(
            f"[Temporal] Stored version {version_number} for {validation_id} "
            f"(significance: {significance_score}).",
            flush=True,
        )
        return True

    except Exception as e:
        error_str = str(e).lower()
        if "23505" in error_str or "unique" in error_str:
            print(
                f"[Temporal] Version {version_number} already exists for {validation_id}. Skipping.",
                flush=True,
            )
        else:
            print(f"[Temporal] Failed to store version: {e}", flush=True)
        return False


def get_latest_version(validation_id: str) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Retrieves the latest report version for a validation.

    Returns:
        Tuple of (report_json, version_number).
        (None, 0) if no versions exist.
    """
    from app.services.rag import _get_supabase
    supabase = _get_supabase()

    try:
        result = (
            supabase.table("report_versions")
            .select("report_json, version_number")
            .eq("validation_id", validation_id)
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            row = result.data[0]
            return row.get("report_json"), row.get("version_number", 0)

    except Exception as e:
        print(f"[Temporal] Failed to fetch latest version: {e}", flush=True)

    return None, 0


# =====================================================================
# ORCHESTRATOR: Run temporal comparison for a re-run
# =====================================================================

def run_temporal_comparison(
    validation_id: str,
    new_report_json: Dict[str, Any],
    new_markdown: str,
    idea_description: str,
    tokens_used: int = 0,
    estimated_cost: float = 0.0,
    model_version: str = "",
) -> Optional[TemporalDiff]:
    """
    Compares a new report against the latest stored version.

    If this is the first run (no previous versions), stores version 1
    without a diff.

    Args:
        validation_id: The validation ID.
        new_report_json: The newly generated report JSON.
        new_markdown: The newly generated markdown.
        idea_description: Original idea for narrative context.
        tokens_used: Tokens consumed.
        estimated_cost: Cost estimate.
        model_version: Model(s) used.

    Returns:
        TemporalDiff if there was a previous version to compare against,
        None if this is the first version (no diff to compute).
    """
    # Get the latest stored version
    old_report, old_version = get_latest_version(validation_id)
    new_version = old_version + 1

    if old_report is None:
        # First version — store it without a diff
        print(f"[Temporal] First version for {validation_id}. Storing as v1.", flush=True)
        store_version(
            validation_id=validation_id,
            report_json=new_report_json,
            markdown_report=new_markdown,
            diff_summary={},
            change_narrative="Initial version — no previous data to compare.",
            significance_score=0.0,
            version_number=1,
            tokens_used=tokens_used,
            estimated_cost=estimated_cost,
            model_version=model_version,
        )
        return None

    # Compute diff
    changes, raw_diff = diff_reports(old_report, new_report_json)
    significance = compute_significance(changes, old_report, new_report_json)

    # Generate narrative (only if changes are significant enough)
    narrative = "No significant changes."
    if significance > 0.1:
        narrative = generate_change_narrative(
            changes, idea_description, old_report, new_report_json
        )

    # Store the new version
    store_version(
        validation_id=validation_id,
        report_json=new_report_json,
        markdown_report=new_markdown,
        diff_summary=raw_diff,
        change_narrative=narrative,
        significance_score=significance,
        version_number=new_version,
        tokens_used=tokens_used,
        estimated_cost=estimated_cost,
        model_version=model_version,
    )

    temporal_diff = TemporalDiff(
        validation_id=validation_id,
        old_version=old_version,
        new_version=new_version,
        changes=changes,
        change_narrative=narrative,
        significance_score=significance,
    )

    print(
        f"[Temporal] v{old_version} → v{new_version}: "
        f"significance={significance}, changes={len(changes)}",
        flush=True,
    )
    return temporal_diff
