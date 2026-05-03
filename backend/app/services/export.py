# export.py
# ---------------------------------------------------------------------------
# FEATURE 13: Professional PDF Export
#
# Generates publication-quality PDF reports from completed validations.
#
# PIPELINE:
#   1. FETCH: Load the completed report from Supabase.
#   2. RENDER: Jinja2 template → HTML with embedded CSS (dark mode, gradients).
#   3. CONVERT: WeasyPrint renders the HTML → PDF.
#   4. UPLOAD: Upload the PDF to Supabase Storage bucket `exports`.
#   5. SIGN: Generate a signed download URL (1-hour expiry).
#
# DESIGN DECISIONS:
#   - WeasyPrint over ReportLab: WeasyPrint renders CSS → PDF. This means
#     we write the report as styled HTML (which we already have as markdown)
#     and get a beautiful PDF without fighting ReportLab's coordinate system.
#   - Jinja2 template is embedded as a string constant in this module.
#     This avoids filesystem path issues inside Docker containers.
#   - The PDF uses a dark premium theme with gradients to match the
#     platform's visual identity.
#   - Supabase Storage handles hosting — no S3 bucket needed.
# ---------------------------------------------------------------------------

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from jinja2 import Template
from weasyprint import HTML
from supabase import create_client, Client

from app.core.config import settings


# ---------------------------------------------------------------------------
# Supabase client singleton
# ---------------------------------------------------------------------------
_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


# ---------------------------------------------------------------------------
# Jinja2 HTML Template (embedded — no filesystem dependency)
#
# This template produces a self-contained HTML page with all styles inlined.
# WeasyPrint renders it pixel-perfect to PDF.
# ---------------------------------------------------------------------------

_PDF_TEMPLATE = Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: #0f0f1a;
    color: #e0e0ef;
    padding: 40px;
    font-size: 11pt;
    line-height: 1.6;
  }

  .header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border-radius: 12px;
    padding: 32px 40px;
    margin-bottom: 32px;
    border: 1px solid rgba(100, 149, 237, 0.2);
  }

  .header h1 {
    color: #7b93db;
    font-size: 22pt;
    font-weight: 700;
    margin-bottom: 8px;
  }

  .header .subtitle {
    color: #8a8aaa;
    font-size: 10pt;
  }

  .score-badge {
    display: inline-block;
    background: linear-gradient(135deg, #2d5016 0%, #1a7a3a 100%);
    color: #4ade80;
    padding: 8px 20px;
    border-radius: 20px;
    font-size: 14pt;
    font-weight: 700;
    margin-top: 12px;
  }

  .score-badge.low { background: linear-gradient(135deg, #7a1a1a 0%, #a02020 100%); color: #f87171; }
  .score-badge.medium { background: linear-gradient(135deg, #7a5a1a 0%, #a07020 100%); color: #fbbf24; }

  .section {
    background: #1a1a2e;
    border-radius: 10px;
    padding: 24px 32px;
    margin-bottom: 20px;
    border: 1px solid rgba(100, 149, 237, 0.1);
    page-break-inside: avoid;
  }

  .section h2 {
    color: #7b93db;
    font-size: 13pt;
    font-weight: 700;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(100, 149, 237, 0.15);
  }

  .section p, .section li {
    color: #c0c0d8;
    margin-bottom: 6px;
  }

  .section ul { padding-left: 20px; }
  .section li { margin-bottom: 4px; }

  .meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }

  .meta-card {
    background: #16163a;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
    border: 1px solid rgba(100, 149, 237, 0.1);
  }

  .meta-card .label { color: #6a6a8a; font-size: 8pt; text-transform: uppercase; }
  .meta-card .value { color: #7b93db; font-size: 14pt; font-weight: 700; margin-top: 4px; }

  .confidence-bar {
    background: #16163a;
    border-radius: 6px;
    height: 10px;
    overflow: hidden;
    margin-top: 8px;
  }

  .confidence-fill {
    height: 100%;
    border-radius: 6px;
    background: linear-gradient(90deg, #4ade80, #7b93db);
  }

  .footer {
    text-align: center;
    color: #4a4a6a;
    font-size: 8pt;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid rgba(100, 149, 237, 0.1);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
  }

  th, td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid rgba(100, 149, 237, 0.1);
  }

  th { color: #7b93db; font-weight: 600; font-size: 9pt; text-transform: uppercase; }
  td { color: #c0c0d8; font-size: 10pt; }
</style>
</head>
<body>

<!-- ===== HEADER ===== -->
<div class="header">
  <h1>🚀 StartupScope AI — Validation Report</h1>
  <div class="subtitle">
    Generated {{ generated_at }} | Model: {{ model_version }}
    {% if consensus_confidence %} | Consensus Confidence: {{ (consensus_confidence * 100) | round(1) }}%{% endif %}
  </div>
  {% set score = report.get('feasibility_score', 0) %}
  <div class="score-badge {% if score < 40 %}low{% elif score < 70 %}medium{% endif %}">
    Feasibility Score: {{ score }}/100
  </div>
</div>

<!-- ===== META CARDS ===== -->
<div class="meta-grid">
  <div class="meta-card">
    <div class="label">Tokens Used</div>
    <div class="value">{{ tokens_used | default('N/A') }}</div>
  </div>
  <div class="meta-card">
    <div class="label">Estimated Cost</div>
    <div class="value">${{ '%.4f' | format(estimated_cost | default(0)) }}</div>
  </div>
  <div class="meta-card">
    <div class="label">Validation ID</div>
    <div class="value" style="font-size: 8pt;">{{ validation_id[:8] }}…</div>
  </div>
</div>

{% if consensus_confidence %}
<div class="section">
  <h2>🤝 Model Consensus</h2>
  <p>Two AI models independently analyzed your idea. Agreement level:</p>
  <div class="confidence-bar">
    <div class="confidence-fill" style="width: {{ (consensus_confidence * 100) | round(1) }}%;"></div>
  </div>
  <p style="margin-top: 8px; font-size: 9pt;">
    {{ (consensus_confidence * 100) | round(1) }}% agreement across all fields.
  </p>
</div>
{% endif %}

<!-- ===== MARKET VIABILITY ===== -->
<div class="section">
  <h2>📊 Market Viability</h2>
  <p>{{ report.get('market_viability', 'N/A') }}</p>
</div>

<!-- ===== GAPS IDENTIFIED ===== -->
<div class="section">
  <h2>🔍 Gaps Identified</h2>
  <ul>
    {% for gap in report.get('gaps_identified', []) %}
    <li>{{ gap }}</li>
    {% endfor %}
  </ul>
</div>

<!-- ===== RECOMMENDED APPROACH ===== -->
<div class="section">
  <h2>🎯 Recommended Approach</h2>
  <p>{{ report.get('recommended_approach', 'N/A') }}</p>
</div>

<!-- ===== PRICING DATA ===== -->
{% if pricing_data and pricing_data.get('competitors') %}
<div class="section">
  <h2>💰 Competitor Pricing</h2>
  <table>
    <thead>
      <tr><th>Competitor</th><th>Free Tier</th><th>Enterprise</th><th>Tiers</th></tr>
    </thead>
    <tbody>
      {% for c in pricing_data.get('competitors', []) %}
      <tr>
        <td>{{ c.get('competitor_name', 'Unknown') }}</td>
        <td>{{ '✅' if c.get('has_free_tier') else '❌' }}</td>
        <td>{{ '✅' if c.get('has_enterprise_tier') else '❌' }}</td>
        <td>{{ c.get('pricing_tiers', []) | length }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if pricing_data.get('gap_analysis') %}
  <p style="margin-top: 12px;">{{ pricing_data.get('gap_analysis', '')[:500] }}</p>
  {% endif %}
</div>
{% endif %}

<!-- ===== PATENT DATA ===== -->
{% if patent_data and patent_data.get('patents') %}
<div class="section">
  <h2>🔬 Patent & IP Landscape</h2>
  <p>Found {{ patent_data.get('total_found', 0) }} relevant patents
     (keywords: {{ patent_data.get('keywords_searched', []) | join(', ') }}).</p>
  <table>
    <thead>
      <tr><th>Patent #</th><th>Title</th><th>Assignee</th><th>Date</th></tr>
    </thead>
    <tbody>
      {% for p in patent_data.get('patents', [])[:5] %}
      <tr>
        <td>{{ p.get('patent_number', '') }}</td>
        <td>{{ p.get('title', '')[:60] }}</td>
        <td>{{ p.get('assignee', 'Unknown') }}</td>
        <td>{{ p.get('filing_date', '') }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<!-- ===== TRAFFIC DATA ===== -->
{% if traffic_data and traffic_data.get('competitors') %}
<div class="section">
  <h2>📈 Web Traffic Intelligence</h2>
  <table>
    <thead>
      <tr><th>Domain</th><th>Traffic Tier</th><th>Trend</th><th>Snapshots</th></tr>
    </thead>
    <tbody>
      {% for t in traffic_data.get('competitors', []) %}
      <tr>
        <td>{{ t.get('domain', '') }}</td>
        <td>{{ t.get('traffic_tier', 'Unknown') }}</td>
        <td>{{ t.get('growth_trend', 'unknown') }}</td>
        <td>{{ t.get('total_snapshots', 0) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<!-- ===== FOOTER ===== -->
<div class="footer">
  StartupScope AI — Powered by Gemini + Groq Multi-Model Consensus Engine<br>
  This report is AI-generated and should be used as guidance, not financial advice.
</div>

</body>
</html>""")


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

def generate_pdf(
    validation_id: str,
    report_json: Dict[str, Any],
    markdown_report: str = "",
    tokens_used: int = 0,
    estimated_cost: float = 0.0,
    model_version: str = "",
    consensus_confidence: Optional[float] = None,
    pricing_data: Optional[Dict] = None,
    funding_data: Optional[Dict] = None,
    patent_data: Optional[Dict] = None,
    traffic_data: Optional[Dict] = None,
) -> bytes:
    """
    Generates a professional PDF from a validation report.

    Args:
        validation_id: The validation ID.
        report_json: The report JSON (feasibility_score, market_viability, etc.).
        markdown_report: The long-form markdown report.
        tokens_used: Total tokens consumed.
        estimated_cost: Total estimated cost.
        model_version: Model(s) used.
        consensus_confidence: Overall consensus confidence (0–1).
        pricing_data: Pricing intelligence dict.
        funding_data: Funding intelligence dict.
        patent_data: Patent intelligence dict.
        traffic_data: Traffic intelligence dict.

    Returns:
        PDF file content as bytes.
    """
    # Render the Jinja2 template with report data
    html_content = _PDF_TEMPLATE.render(
        validation_id=validation_id,
        report=report_json or {},
        markdown_report=markdown_report,
        tokens_used=tokens_used,
        estimated_cost=estimated_cost,
        model_version=model_version,
        consensus_confidence=consensus_confidence,
        pricing_data=pricing_data,
        funding_data=funding_data,
        patent_data=patent_data,
        traffic_data=traffic_data,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    # Convert HTML → PDF via WeasyPrint
    pdf_bytes = HTML(string=html_content).write_pdf()

    print(
        f"[Export] Generated PDF for {validation_id}: "
        f"{len(pdf_bytes):,} bytes.",
        flush=True,
    )
    return pdf_bytes


# ---------------------------------------------------------------------------
# Upload to Supabase Storage + generate signed URL
# ---------------------------------------------------------------------------

def upload_and_sign(
    validation_id: str,
    pdf_bytes: bytes,
    expiry_seconds: int = 3600,
) -> str:
    """
    Uploads a PDF to Supabase Storage bucket 'exports' and returns
    a signed download URL.

    Args:
        validation_id: Used to construct the file path.
        pdf_bytes: The raw PDF content.
        expiry_seconds: How long the signed URL is valid (default: 1 hour).

    Returns:
        Signed download URL string.
    """
    supabase = _get_supabase()
    file_path = f"reports/{validation_id}.pdf"

    try:
        # Upload to 'exports' bucket (must exist in Supabase Storage)
        supabase.storage.from_("exports").upload(
            path=file_path,
            file=pdf_bytes,
            file_options={
                "content-type": "application/pdf",
                "upsert": True,  # BUG FIX: Must be boolean, not string "true"
            },
        )
        print(f"[Export] Uploaded to exports/{file_path}.", flush=True)

        # Generate signed URL
        signed = supabase.storage.from_("exports").create_signed_url(
            path=file_path,
            expires_in=expiry_seconds,
        )

        url = signed.get("signedURL", "") if isinstance(signed, dict) else ""

        # Fallback: some Supabase SDK versions return the URL differently
        if not url and hasattr(signed, "signed_url"):
            url = signed.signed_url

        print(f"[Export] Signed URL generated (expires in {expiry_seconds}s).", flush=True)
        return url

    except Exception as e:
        print(f"[Export] Upload/signing failed: {e}", flush=True)
        raise


# ---------------------------------------------------------------------------
# ORCHESTRATOR: Fetch → Generate → Upload → Return URL
# ---------------------------------------------------------------------------

def export_validation_pdf(validation_id: str) -> str:
    """
    Complete PDF export pipeline:
      1. Fetch the completed validation from Supabase.
      2. Generate a professional PDF via WeasyPrint.
      3. Upload to Supabase Storage.
      4. Return a signed download URL.

    Args:
        validation_id: The validation to export.

    Returns:
        Signed download URL for the PDF.

    Raises:
        ValueError: If the validation is not found or not completed.
    """
    supabase = _get_supabase()

    # BUG FIX: .single() raises Supabase APIError if 0 or multiple rows are found.
    # Wrap in try/except and convert to ValueError so the caller returns a 404.
    try:
        result = (
            supabase.table("validations")
            .select(
                "report_json, markdown_report, tokens_used, estimated_cost, "
                "model_version, consensus_confidence, pricing_data, funding_data, "
                "patent_data, traffic_data, status"
            )
            .eq("id", validation_id)
            .single()
            .execute()
        )
    except Exception:
        raise ValueError(f"Validation {validation_id} not found or inaccessible.")

    if not result.data:
        raise ValueError(f"Validation {validation_id} not found.")

    row = result.data
    if row.get("status") != "completed":
        raise ValueError(
            f"Validation {validation_id} is not completed "
            f"(status: {row.get('status')})."
        )

    # Step 2: Generate
    pdf_bytes = generate_pdf(
        validation_id=validation_id,
        report_json=row.get("report_json", {}),
        markdown_report=row.get("markdown_report", ""),
        tokens_used=row.get("tokens_used", 0),
        estimated_cost=row.get("estimated_cost", 0.0),
        model_version=row.get("model_version", ""),
        consensus_confidence=row.get("consensus_confidence"),
        pricing_data=row.get("pricing_data"),
        funding_data=row.get("funding_data"),
        patent_data=row.get("patent_data"),
        traffic_data=row.get("traffic_data"),
    )

    # Step 3 + 4: Upload and sign
    url = upload_and_sign(validation_id, pdf_bytes)

    return url
