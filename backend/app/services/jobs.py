# jobs.py
# ---------------------------------------------------------------------------
# FEATURE 9: Job Posting Signal
#
# Scrapes public job listings to infer competitor growth trajectory.
# Uses our existing Firecrawl client — NO Apify needed.
#
# SOURCES (all publicly accessible without login):
#   1. Indeed.com/cmp/{company}/jobs — fully public company job pages.
#   2. LinkedIn public company pages — job count visible without login
#      for public companies.
#
# PIPELINE:
#   1. BUILD URLS: Construct Indeed/LinkedIn job page URLs from competitor names.
#   2. SCRAPE: Firecrawl scrapes the public job pages.
#   3. EXTRACT: Gemini extracts role counts by department.
#   4. ANALYZE: Gemini synthesizes headcount velocity insights.
#
# DESIGN: This runs inside the Celery worker's ThreadPoolExecutor (Step 10).
# Results are stored in the enriched validation payload, not a separate table
# (keeping the schema simple until Feature 16 adds monitoring/alerts).
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import quote_plus

from app.services.ai_pipeline import _get_firecrawl, _get_gemini
from app.schemas.ai_reports import CompetitorJobs, JobDepartment, JobsReport
from google.genai import types as genai_types


# =====================================================================
# STEP 1: BUILD SCRAPE URLS
#
# Constructs the public job listing URLs for each competitor.
# Indeed's /cmp/ pages are the most reliable free source.
# =====================================================================

def _build_job_urls(competitor_names: List[str]) -> List[Dict[str, str]]:
    """
    Builds Indeed and LinkedIn job page URLs for each competitor.

    Args:
        competitor_names: List of competitor domain names (e.g., 'notion.so').

    Returns:
        List of dicts: {competitor_name, indeed_url, search_query}.
    """
    targets: List[Dict[str, str]] = []

    for name in competitor_names[:5]:  # Cap at 5
        # Clean the domain into a company name
        clean_name = name.replace("www.", "").split(".")[0]

        targets.append({
            "competitor_name": clean_name,
            # Indeed company page — most reliable public source
            "indeed_url": f"https://www.indeed.com/cmp/{quote_plus(clean_name)}/jobs",
            # Fallback: search Indeed for the company
            "search_query": f"{clean_name} jobs hiring open positions",
        })

    return targets


# =====================================================================
# STEP 2: SCRAPE JOB PAGES VIA FIRECRAWL
#
# Uses our existing Firecrawl singleton. Falls back to a Firecrawl
# search if direct URL scraping fails (company name might not match
# the Indeed slug exactly).
# =====================================================================

def _scrape_job_data(targets: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Scrapes job listing pages for each competitor.

    Strategy:
      1. Try Firecrawl search for "{company} jobs hiring" (most reliable).
      2. The search results contain snippets with job counts and titles.

    Returns:
        List of dicts: {competitor_name, content, source}.
    """
    firecrawl = _get_firecrawl()
    results: List[Dict[str, Any]] = []

    for target in targets:
        name = target["competitor_name"]
        query = target["search_query"]

        try:
            print(f"[Jobs] Searching job data for: {name}", flush=True)
            response = firecrawl.search(query=query, limit=3)

            search_text_parts: List[str] = []
            results_list = None
            if hasattr(response, "data") and response.data:
                results_list = response.data
            elif hasattr(response, "web") and response.web:
                results_list = response.web

            if results_list:
                for result in results_list:
                    res_dict = (
                        result.model_dump()
                        if hasattr(result, "model_dump")
                        else dict(result)
                    )
                    title = res_dict.get("title", "")
                    desc = res_dict.get("description", "") or res_dict.get("snippet", "")
                    url = res_dict.get("url", "")
                    if title or desc:
                        search_text_parts.append(
                            f"Title: {title}\nSnippet: {desc}\nURL: {url}"
                        )

            if search_text_parts:
                results.append({
                    "competitor_name": name,
                    "content": "\n\n".join(search_text_parts),
                    "source": "firecrawl_search",
                })
                print(f"[Jobs] Got {len(search_text_parts)} results for {name}", flush=True)

        except Exception as e:
            print(f"[Jobs] Scrape failed for {name}: {e}", flush=True)
            continue

    return results


# =====================================================================
# STEP 3: GEMINI EXTRACTION — Role counts by department
# =====================================================================

_JOB_EXTRACTION_PROMPT = (
    "From the following job listing search results, extract information about "
    "the company's hiring activity.\n\n"
    "Output valid JSON:\n"
    "{\n"
    '  "total_open_roles": <integer or 0 if unknown>,\n'
    '  "departments": [\n'
    '    {"department": "Engineering", "role_count": 5, "sample_titles": ["Senior Backend Engineer"]},\n'
    '    {"department": "Sales", "role_count": 3, "sample_titles": ["Account Executive"]}\n'
    "  ],\n"
    '  "hiring_velocity": "aggressive|moderate|minimal|unknown",\n'
    '  "notable_roles": ["VP of Engineering", "Head of AI"]\n'
    "}\n\n"
    "If no job data is found, return total_open_roles=0 and empty arrays."
)


def _extract_job_data(
    content: str,
    competitor_name: str,
) -> CompetitorJobs:
    """
    Extracts structured job data from scraped content via Gemini.
    """
    client = _get_gemini()

    current_prompt = (
        f"Company: {competitor_name}\n\n"
        f"--- JOB SEARCH RESULTS ---\n{content[:4000]}"
    )

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=current_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_JOB_EXTRACTION_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )

            raw = response.text
            data = json.loads(raw)

            departments = []
            for dept in data.get("departments", []):
                try:
                    departments.append(JobDepartment(
                        department=dept.get("department", "Other"),
                        role_count=dept.get("role_count", 0),
                        sample_titles=dept.get("sample_titles", []),
                    ))
                except Exception:
                    continue

            return CompetitorJobs(
                competitor_name=competitor_name,
                total_open_roles=data.get("total_open_roles", 0),
                departments=departments,
                hiring_velocity=data.get("hiring_velocity", "unknown"),
                notable_roles=data.get("notable_roles", []),
            )

        except Exception as e:
            if attempt == 0:
                print(f"[Jobs] Self-heal attempt for {competitor_name}: {e}", flush=True)
                current_prompt = (
                    f"Previous extraction failed: {str(e)[:200]}\n\n"
                    f"Re-extract job data for {competitor_name}:\n{content[:3000]}"
                )
                continue
            print(f"[Jobs] Extraction failed for {competitor_name}: {e}", flush=True)
            return CompetitorJobs(competitor_name=competitor_name)

    return CompetitorJobs(competitor_name=competitor_name)


# =====================================================================
# STEP 4: SYNTHESIS — Headcount velocity analysis
# =====================================================================

def _synthesize_hiring_landscape(
    all_jobs: List[CompetitorJobs],
    idea_description: str,
) -> str:
    """Gemini synthesis of the hiring landscape across competitors."""
    if not all_jobs:
        return "No job posting data available for analysis."

    client = _get_gemini()

    summary_parts = []
    for cj in all_jobs:
        dept_str = ", ".join(
            f"{d.department}: {d.role_count}" for d in cj.departments
        ) or "No department breakdown"
        summary_parts.append(
            f"**{cj.competitor_name}**: {cj.total_open_roles} open roles "
            f"(velocity: {cj.hiring_velocity}). Departments: {dept_str}"
        )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f"Startup Idea: {idea_description}\n\n"
                f"Competitor Hiring Data:\n" + "\n".join(summary_parts)
            ),
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "You are a competitive intelligence analyst. Analyze the hiring "
                    "data and provide a markdown report on:\n"
                    "1. Which competitors are scaling fastest (headcount velocity)\n"
                    "2. Which departments are getting the most investment\n"
                    "3. What this signals about market direction\n"
                    "4. Talent competition risks for a new entrant"
                ),
                temperature=0.5,
            ),
        )
        return response.text or "Hiring analysis generation failed."
    except Exception as e:
        print(f"[Jobs] Synthesis failed: {e}", flush=True)
        return f"Hiring landscape analysis unavailable: {e}"


# =====================================================================
# ORCHESTRATOR
# =====================================================================

def run_jobs_pipeline(
    competitor_names: List[str],
    idea_description: str,
    validation_id: str,
) -> JobsReport:
    """
    Full job posting signal pipeline:
      1. Build scrape URLs for Indeed/LinkedIn.
      2. Scrape via Firecrawl.
      3. Extract role counts via Gemini.
      4. Synthesize hiring landscape.

    Returns:
        JobsReport with per-competitor hiring data and landscape analysis.
    """
    print(f"[Jobs] Starting pipeline for {len(competitor_names)} competitors.", flush=True)

    # Step 1: Build URLs
    targets = _build_job_urls(competitor_names)

    # Step 2: Scrape
    scraped = _scrape_job_data(targets)

    # Step 3: Extract
    all_jobs: List[CompetitorJobs] = []
    for s in scraped:
        jobs = _extract_job_data(
            content=s["content"],
            competitor_name=s["competitor_name"],
        )
        if jobs.total_open_roles > 0 or jobs.departments:
            all_jobs.append(jobs)

    # Step 4: Synthesize
    analysis = _synthesize_hiring_landscape(all_jobs, idea_description) if all_jobs else ""

    report = JobsReport(
        competitors=all_jobs,
        landscape_analysis=analysis,
    )

    print(f"[Jobs] Pipeline complete: {len(all_jobs)} competitors with job data.", flush=True)
    return report
