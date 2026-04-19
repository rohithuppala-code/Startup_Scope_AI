# patents.py
# ---------------------------------------------------------------------------
# FEATURE 8: Patent & IP Moat Scan
#
# Queries two FREE public patent APIs to discover existing IP in the
# startup's domain:
#
#   1. USPTO PatentsView API (api.patentsview.org/patents/query)
#      - Free forever by law (US government public API).
#      - No key, no signup. Pure POST with JSON query body.
#      - Returns patents matching keyword queries.
#
#   2. EPO Open Patent Services (ops.epo.org)
#      - 3,000 free calls/month with a free registered account.
#      - NOT implemented yet (requires registration). Placeholder included.
#
# PIPELINE:
#   1. EXTRACT: Gemini extracts core technical keywords from the idea.
#   2. QUERY: POST to USPTO PatentsView with those keywords.
#   3. STRUCTURE: Parse results into PatentResult schema.
#   4. ANALYZE: Gemini summarizes the IP landscape.
#   5. STORE: Persist to Supabase (via the enriched validation payload).
#
# ZERO COST: USPTO is a US government API — free by law, forever.
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List

import requests

from app.services.ai_pipeline import _get_gemini
from app.schemas.ai_reports import PatentResult, PatentReport
from google.genai import types as genai_types


# =====================================================================
# STEP 1: EXTRACT KEYWORDS FROM IDEA VIA GEMINI
#
# We ask Gemini to extract the 3–5 most relevant technical/patent
# keywords from the idea description. This is cheaper and more
# accurate than searching for the raw idea text.
# =====================================================================

_KEYWORD_EXTRACTION_PROMPT = (
    "Extract 3–5 concise technical keywords suitable for a patent search "
    "from the following startup idea. Focus on the CORE technology, not "
    "the business model.\n\n"
    "Output ONLY a JSON array of strings, e.g.:\n"
    '["machine learning", "natural language processing", "recommendation engine"]\n\n'
    "No explanation, no markdown fencing."
)


def _extract_patent_keywords(idea_description: str) -> List[str]:
    """
    Uses Gemini to extract 3–5 technical keywords from the idea.

    Returns a list of keyword strings suitable for USPTO search.
    Falls back to splitting the idea into 3-word chunks on failure.
    """
    try:
        client = _get_gemini()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=idea_description,
            config=genai_types.GenerateContentConfig(
                system_instruction=_KEYWORD_EXTRACTION_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        raw = response.text
        keywords = json.loads(raw)

        if isinstance(keywords, list) and keywords:
            print(f"[Patents] Extracted keywords: {keywords}", flush=True)
            return keywords[:5]

    except Exception as e:
        print(f"[Patents] Keyword extraction failed: {e}", flush=True)

    # Fallback: use first 5 meaningful words from the idea
    words = [w for w in idea_description.split() if len(w) > 3][:5]
    return words if words else ["startup", "technology"]


# =====================================================================
# STEP 2: QUERY USPTO PATENTSVIEW API
#
# Free, no key, no signup. POST JSON query to:
#   https://api.patentsview.org/patents/query
#
# Query format uses their custom JSON query language.
# We search patent abstracts for the extracted keywords.
# =====================================================================

_USPTO_API_URL = "https://api.patentsview.org/patents/query"
_USPTO_TIMEOUT = 15  # seconds


def _query_uspto(keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Queries the USPTO PatentsView API for patents matching the keywords.

    Args:
        keywords: List of technical keywords from Gemini extraction.

    Returns:
        List of raw patent dicts from the API response.
        Empty list on failure or no results.
    """
    # Build the query: OR across all keywords in the abstract field
    if len(keywords) == 1:
        query = {"_text_any": {"patent_abstract": keywords[0]}}
    else:
        query = {
            "_or": [
                {"_text_any": {"patent_abstract": kw}}
                for kw in keywords
            ]
        }

    payload = {
        "q": query,
        "f": [
            "patent_number",
            "patent_title",
            "patent_abstract",
            "patent_date",
            "assignee_organization",
            "inventor_first_name",
            "inventor_last_name",
        ],
        "o": {
            "page": 1,
            "per_page": 15,  # Cap at 15 patents to avoid overwhelming the analysis
        },
        "s": [{"patent_date": "desc"}],  # Most recent first
    }

    try:
        print(f"[Patents] Querying USPTO with {len(keywords)} keywords...", flush=True)
        response = requests.post(
            _USPTO_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=_USPTO_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        patents = data.get("patents", [])
        total_found = data.get("total_patent_count", 0)

        print(f"[Patents] USPTO returned {len(patents)} patents (total: {total_found}).", flush=True)
        return patents

    except requests.exceptions.Timeout:
        print("[Patents] USPTO API timed out.", flush=True)
        return []
    except requests.exceptions.HTTPError as e:
        print(f"[Patents] USPTO API HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"[Patents] USPTO API error: {e}", flush=True)
        return []


# =====================================================================
# STEP 3: PARSE INTO STRUCTURED SCHEMA
# =====================================================================

def _parse_patents(raw_patents: List[Dict[str, Any]]) -> List[PatentResult]:
    """
    Converts raw USPTO API responses into PatentResult schema objects.

    Handles the nested response format from PatentsView:
      - assignees is a list of {assignee_organization: str}
      - inventors is a list of {inventor_first_name, inventor_last_name}
    """
    results: List[PatentResult] = []

    for patent in raw_patents:
        try:
            patent_number = patent.get("patent_number", "")
            title = patent.get("patent_title", "")
            abstract = patent.get("patent_abstract", "")
            date = patent.get("patent_date", "")

            # Extract assignee (company name)
            assignees = patent.get("assignees", [])
            assignee = ""
            if assignees and isinstance(assignees, list):
                first_assignee = assignees[0] if assignees else {}
                if isinstance(first_assignee, dict):
                    assignee = first_assignee.get("assignee_organization", "") or ""

            # Extract inventors
            inventors_raw = patent.get("inventors", [])
            inventors: List[str] = []
            if inventors_raw and isinstance(inventors_raw, list):
                for inv in inventors_raw[:3]:  # Cap at 3 inventors
                    if isinstance(inv, dict):
                        first = inv.get("inventor_first_name", "")
                        last = inv.get("inventor_last_name", "")
                        name = f"{first} {last}".strip()
                        if name:
                            inventors.append(name)

            results.append(PatentResult(
                patent_number=patent_number,
                title=title,
                abstract=abstract[:500],  # Cap abstract length
                filing_date=date,
                assignee=assignee,
                inventors=inventors,
                source="USPTO PatentsView",
                url=f"https://patents.google.com/patent/US{patent_number}" if patent_number else "",
            ))

        except Exception as e:
            print(f"[Patents] Failed to parse patent: {e}", flush=True)
            continue

    return results


# =====================================================================
# STEP 4: GEMINI IP LANDSCAPE ANALYSIS
# =====================================================================

def _analyze_ip_landscape(
    patents: List[PatentResult],
    idea_description: str,
) -> str:
    """
    Uses Gemini to analyze the patent landscape and identify IP risks.

    Returns markdown analysis covering:
      - Key patent holders in the space
      - Potential IP conflicts for the startup idea
      - White space opportunities (areas NOT covered by existing patents)
      - Freedom-to-operate assessment
    """
    if not patents:
        return "No relevant patents found. The IP landscape appears clear for this idea."

    client = _get_gemini()

    patents_summary = "\n".join(
        f"- **{p.title}** (US{p.patent_number}, {p.filing_date})\n"
        f"  Assignee: {p.assignee or 'Unknown'}\n"
        f"  Abstract: {p.abstract[:200]}"
        for p in patents[:10]  # Cap to save tokens
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"Startup Idea: {idea_description}\n\n"
                f"Relevant Patents Found ({len(patents)} total):\n{patents_summary}"
            ),
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "You are a patent and IP analyst. Analyze the patent landscape "
                    "for the given startup idea. Provide a concise markdown report:\n"
                    "1. **Key Patent Holders**: Who owns the most relevant IP?\n"
                    "2. **IP Risk Assessment**: Could any patents block this startup?\n"
                    "3. **White Space**: Areas NOT covered by existing patents.\n"
                    "4. **Freedom-to-Operate**: Overall assessment (Low/Medium/High risk).\n\n"
                    "Be specific about patent numbers when referencing them."
                ),
                temperature=0.4,
            ),
        )
        return response.text or "IP analysis generation failed."
    except Exception as e:
        print(f"[Patents] IP analysis failed: {e}", flush=True)
        return f"IP landscape analysis unavailable: {e}"


# =====================================================================
# ORCHESTRATOR
# =====================================================================

def run_patent_pipeline(
    idea_description: str,
    competitor_names: List[str],
    validation_id: str,
) -> PatentReport:
    """
    Full patent & IP scan pipeline:
      1. Extract technical keywords from idea via Gemini.
      2. Query USPTO PatentsView API.
      3. Parse into structured schema.
      4. Gemini IP landscape analysis.

    Args:
        idea_description: The startup idea.
        competitor_names: Competitor names for targeted searches.
        validation_id: The validation this pipeline is part of.

    Returns:
        PatentReport with patent data and IP analysis.
    """
    print(f"[Patents] Starting pipeline for validation {validation_id}.", flush=True)

    # Step 1: Extract keywords
    keywords = _extract_patent_keywords(idea_description)

    # Step 2: Query USPTO
    raw_patents = _query_uspto(keywords)

    # Step 3: Parse
    patents = _parse_patents(raw_patents)

    # Step 4: Analyze
    ip_analysis = _analyze_ip_landscape(patents, idea_description)

    report = PatentReport(
        patents=patents,
        keywords_searched=keywords,
        total_found=len(patents),
        ip_analysis=ip_analysis,
    )

    print(
        f"[Patents] Pipeline complete: {len(patents)} patents found, "
        f"keywords={keywords}",
        flush=True,
    )
    return report
